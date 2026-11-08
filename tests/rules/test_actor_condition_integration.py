"""Shared Play and recovery paths consume actual actor conditions and custody."""

import pytest
from test_enforcer_conditioning import accuse, rank, setup
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_world import initial

from girlframe.engine import m3_actor_bonds as bonds
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Npc
from girlframe.services.onboarding import WorkflowError


def test_actor_helpless_blocks_play_and_recovers_actual_person_without_alias_or_rng(ledger):
    game, _, _, dice = setup_game(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial().model_copy(
            update={
                "npcs": (
                    Npc(
                        id="1",
                        name="Distinct NPC",
                        jobs=("guard",),
                        detail="Actual foe",
                        cell=(0, 0),
                        controller=1,
                    ),
                )
            }
        )
        actor = bonds.current_ref(canon, 2)
        canon = bonds.make_helpless(canon, actor, ActorRef(kind="npc", entity="1"), "loss")
        for asset in canon.sheets["2"].assets:
            if asset.family == "girl":
                asset.damaged = True
        game.event(c, 1, "actual-helpless-source", "synthetic.condition", canon)
    assert game.helpless_status(PLAYER)
    assert not state(game).sheets["2"].helpless_against
    assert not bonds.is_helpless(state(game), actor, bonds.current_ref(state(game), 1))
    with pytest.raises(WorkflowError, match="Helplessness"):
        game.begin(
            PLAYER,
            "blocked-defense",
            900,
            state(game).sheets["2"].revision,
            PlayInput(play="engage", context="Actual defense", trigger_confirmed=True, heat=0),
        )
    revision = state(game).sheets["2"].revision
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl")
    with pytest.raises(WorkflowError, match="Choose one damaged"):
        game.recover_helpless(PLAYER, "missing-asset", revision, "Actual moment alone", None)
    result = game.recover_helpless(
        PLAYER, "recover-person", revision, "Actual moment alone", asset.id
    )
    assert (
        game.recover_helpless(PLAYER, "recover-person", revision, "Actual moment alone", asset.id)
        == result
    )
    assert not game.helpless_status(PLAYER)
    after = state(game)
    assert not next(x for x in after.sheets["2"].assets if x.id == asset.id).damaged
    assert after.helpless_conditions[0].recovery_event
    assert dice.calls == 0
    game.rebuild()
    assert state(game) == after


def test_actual_detention_and_unknown_release_override_old_npc_map_and_stale_hash(
    ledger, tmp_path, monkeypatch
):
    service, game = setup(ledger, tmp_path, monkeypatch)
    ref = ActorRef(kind="npc", entity="known-guard")
    before = resolve(state(game), ref, ())
    rank(service)
    case = accuse(service)["id"]
    held = resolve(state(game), ref, ())
    assert held.cell is None and held.custody == "foundation_detention:" + case
    assert held.source_sha256 != before.source_sha256
    service.release(ADMIN, "actual-release", case, service.get(ADMIN, case)["revision"], "Evidence")
    released = resolve(state(game), ref, ())
    assert released.cell is None and released.custody is None
    assert released.source_sha256 != held.source_sha256
    service.record_released_position(
        ADMIN,
        "actual-position",
        case,
        service.get(ADMIN, case)["revision"],
        (2, 0),
        "Observed here",
    )
    actual = resolve(state(game), ref, ())
    assert actual.cell == (2, 0) and actual.source_sha256 != released.source_sha256
