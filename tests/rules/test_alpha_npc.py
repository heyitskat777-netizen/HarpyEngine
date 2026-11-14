"""Actual Alpha NPC mid Broken and high source-owned death."""

from uuid import uuid4

import pytest
from test_alpha_brutalize import ready
from test_cast_service import change as cast_change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, pass_tags, state, tick

from girlframe.engine import m3_alpha_sex as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_alpha import conditions
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_alpha_sex import SexService, prove
from girlframe.services.m3_body_facts import BodyFactsService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_mid_broken_tracking_and_high_death(ledger, tmp_path, monkeypatch):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (4, 4))
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    service = SexService(game)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="original-alpha-counterpart")
    WorldService(missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("guard",),
            controller=1,
            detail="PRIVATE_ALPHA_NPC_DETAIL",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(missions)), ADMIN, "join", npc)
    BodyFactsService(game).record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "I witness this actual original ordinary civilian's human body and brain",
    )
    assert any(
        x["ref"] == npc.model_dump(mode="json") for x in service.menu(PLAYER, 900)["targets"]
    )
    identity = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "PRIVATE_ALPHA_NPC_SOURCE Actual voluntary original encounter",
    )["id"]
    before = state(game)
    with pytest.raises(WorkflowError):
        service.respond(OTHER, str(uuid4()), identity, before.revision, True, "Not my NPC")
    assert state(game) == before
    with pytest.raises(WorkflowError, match="Attest actual physical contact"):
        service.respond(
            ADMIN,
            str(uuid4()),
            identity,
            before.revision,
            True,
            "Consent alone is not spatial evidence",
        )
    assert state(game) == before
    service.respond(
        ADMIN,
        str(uuid4()),
        identity,
        before.revision,
        True,
        "Actual original NPC controller confirms voluntary interaction",
        npc_contact_account="Actual original body contact here, outside all enclosures and rides",
    )

    def perform(identity, faces):
        game.dice = Dice(faces)
        action = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play=rules.PLAY,
                source_work=identity,
                target_actor=npc,
                heat=0,
                context="Actual confirmed original NPC interaction",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        pass_tags(game)
        return action

    original_bond = depth(state(game), current_ref(state(game), 2), npc)
    action = perform(identity, (4, 4))
    final = state(game)
    value = rules.get(final, identity)
    assert value.phase == "complete"
    assert depth(final, value.actor, npc) == original_bond + 1
    assert any(
        x.id == value.condition and x.source_action == action
        for x in conditions(final, npc, value.actor)
    )
    assert rules.tracking(final, value)
    assert service.track(PLAYER, identity)["cell"] == (0, 0)
    with ledger.engine.connect() as c:
        assert prove(game, c, final, identity) == value
    tick(worker, gateway, 8)
    high = service.invite(
        PLAYER,
        str(uuid4()),
        900,
        npc,
        state(game).revision,
        "Actual new voluntary source with disclosed high death",
    )["id"]
    service.respond(
        ADMIN,
        str(uuid4()),
        high,
        state(game).revision,
        True,
        "Actual original NPC controller confirms this interaction",
        npc_contact_account="Actual original body contact outside enclosures here",
    )
    high_action = perform(high, (6, 6))
    final = state(game)
    value = rules.get(final, high)
    assert value.phase == "complete"
    assert not next(x for x in final.world.npcs if x.id == npc.entity).alive
    assert not rules.tracking(final, value)
    assert game.inspect(PLAYER, high_action)["state"] == "complete"
    assert not any(x["kind"] == "alpha_sex_damage" for x in game.choices(PLAYER))
    with ledger.engine.connect() as c:
        assert prove(game, c, final, high) == value
    assert "PRIVATE_ALPHA_NPC_DETAIL" not in repr(gateway.messages)
