"""The original Handler actually goes along with NPC use, not merely its validation."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import choose, ready, source, validate
from test_handler_use_cohort import row, submit
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_easy_target import EasyTargetService, prove_npc_use, prove_use_cohort
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_native_original_handler_participates_before_actual_npc_use_finishes(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch, mixed=True)
    handler = current_ref(state(game), ADMIN.user_id)
    npc = ActorRef(kind="npc", entity="bystander")
    spectator = ActorRef(kind="npc", entity="cohort")
    # Scene facilitation is not physical presence: establish an actual prior
    # location, then use the real ordinary movement service before the Play.
    with ledger.transaction() as c:
        before = state(game)
        before.facts.append(
            dict(
                kind="recorded_handler_recovery_position",
                actor=handler.model_dump_json(),
                cell=json.dumps([-1, 0]),
            )
        )
        game.event(c, ADMIN.user_id, str(uuid4()), "synthetic.original_handler_location", before)
    MovementService(game).move(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        handler,
        (0, 0),
        account="The original Handler walks to the present Newgirl and civilian",
    )
    initial = state(game)
    action = source(game, worker, gateway, faces=(5, 5), selected=npc)
    primary_id, handler_id = (rules.identity(action, ref) for ref in (npc, handler))
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [5, 5]
    submit(
        game,
        OTHER,
        row(game, OTHER, npc, "easy_target_react"),
        dict(
            urge=("use",),
            context="An ordinary non-Play filing rehearsal with no separate effect",
            account="PRIVATE_HANDLER_PARTICIPANT The civilian asks her to hold the rehearsal files",
        ),
    )
    submit(
        game,
        ADMIN,
        row(game, ADMIN, handler, "easy_target_react"),
        dict(
            urge=("cohort",),
            primary=(primary_id,),
            account="PRIVATE_HANDLER_PARTICIPANT I choose to go along with that civilian's use",
        ),
    )
    choose(game, OTHER, spectator, "pass")
    choose(game, OTHER, current_ref(state(game), OTHER.user_id), "pass")
    validate(game, npc)
    before = state(game)
    original_depth = depth(before, current_ref(before, PLAYER.user_id), npc)
    choice = row(game, ADMIN, handler)
    assert any(item.identity == choice["id"] for item in InboxService(ledger).items(ADMIN))
    assert game.decision(ADMIN, choice["id"])["detail"]["use_cohort"]
    assert not rules.records(before, rules.UseCohort)
    assert not rules.get(before, rules.Reaction, primary_id).exemption
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("participate",), text="The NPC cannot decide for the Handler"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(
                options=("participate",), text="Invented mechanical use", fields={"damage": "1"}
            ),
        )
    assert state(game) == before
    submit(
        game,
        ADMIN,
        choice,
        dict(
            outcome=("participate",),
            account="PRIVATE_HANDLER_PARTICIPANT I actually help carry the rehearsal files",
        ),
    )
    participating = state(game)
    participation = rules.records(participating, rules.UseCohort)[-1]
    assert participation.actor == handler and participation.controller == ADMIN.user_id
    assert participation.primary == primary_id and participation.reaction == handler_id
    assert participation.outcome == "participated"
    # Ordinary Handler bodies expose their real cell, not a Pilot/NPC placement
    # hash. The immutable event and source proof must retain that actual cell.
    with ledger.engine.connect() as c:
        born = _history(c, game, participation.event)
        body = resolve(
            born,
            handler,
            snapshot_profiles(c, ledger.campaign_id, born),
            require_current_profile=False,
        )
        assert body.rules == "handler" and body.cell == (0, 0)
        assert participation.position == body.position_sha256 is None
        assert participation.vessel == body.vessel_id is None
        assert prove_use_cohort(game, c, participating, participation.id) == participation
    assert not rules.records(participating, rules.HandlerUse)
    assert not rules.records(participating, rules.NpcUse)
    assert not rules.get(participating, rules.Reaction, primary_id).completed_event
    assert not rules.get(participating, rules.Reaction, handler_id).completed_event
    assert game.inspect(PLAYER, action)["state"] != "complete"
    submit(
        GameService(ledger, dice=game.dice),
        OTHER,
        row(game, OTHER, npc),
        dict(account="PRIVATE_HANDLER_PARTICIPANT The civilian now finishes the actual rehearsal"),
    )
    final = state(game)
    primary = rules.get(final, rules.Reaction, primary_id)
    follower = rules.get(final, rules.Reaction, handler_id)
    use = rules.records(final, rules.NpcUse)[-1]
    assert use.actor == npc and use.controller == OTHER.user_id
    assert primary.exemption == handler_id and follower.exemption == primary_id
    assert primary.consequence == follower.consequence == "cohort-exempt"
    assert primary.completed_event == follower.completed_event == use.event
    assert primary.performance_event == use.event != participation.event
    assert follower.performance_event == participation.event
    assert not primary.child and not follower.child
    assert not rules.records(final, rules.HandlerUse)
    assert "1" not in final.sheets and final.handler_heat == initial.handler_heat
    assert final.sheets == before.sheets and final.world == before.world
    assert final.sheets["2"].heat == initial.sheets["2"].heat - 1
    assert depth(final, current_ref(final, PLAYER.user_id), npc) == original_depth
    assert not any(x["kind"].startswith("easy_target_bond") for x in game.choices(PLAYER))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove_use_cohort(game, c, final, participation.id) == participation
        assert prove_npc_use(game, c, final, use.id) == use
        for name in ("m2_actions", "m2_receipts"):
            assert (
                c.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.m2[name])
                    .where(t.m2[name].c.campaign_id == ledger.campaign_id)
                )
                == 1
            )
    assert (
        EasyTargetService(GameService(ledger)).view(ADMIN, handler_id)["use_cohort"][0]["id"]
        == participation.id
    )
    with pytest.raises(WorkflowError):
        EasyTargetService(game).view(GuildViewer(4, 200, True, False), handler_id)
    tick(worker, gateway, 6)
    assert "PRIVATE_HANDLER_PARTICIPANT" not in json.dumps(gateway.messages)

    # Preserve the original body/cast and immutable answer after a later scene.
    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER, ADMIN):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)

    def no_live_profiles(*args, **kwargs):
        raise AssertionError("Historical participation must retain original profile bindings")

    with monkeypatch.context() as history:
        history.setattr("girlframe.services.m3_easy_target.profiles", no_live_profiles)
        history.setattr("girlframe.services.m3_dose_up.profiles", no_live_profiles)
        with ledger.engine.connect() as c:
            assert prove_use_cohort(game, c, later, participation.id) == participation
            assert prove_npc_use(game, c, later, use.id) == use
