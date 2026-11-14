"""The original Handler actually joins NPC hurt before its real injury source."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import _npc_protection_native, choose, ready, source, validate
from test_handler_use_cohort import row, submit
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_easy_target import EasyTargetService, prove_npc_hurt
from girlframe.services.m3_easy_target_hurt_cohort import prove
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_native_original_handler_joins_npc_hurt_before_owned_actual_injury(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    handler = current_ref(state(game), ADMIN.user_id)
    npc = ActorRef(kind="npc", entity="bystander")
    spectator = ActorRef(kind="npc", entity="cohort")
    # Facilitating is not bodily presence. Ordinary movement establishes the
    # original Handler's real body in the same cell as the Newgirl and NPC.
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
        account="The actual Handler walks to the Newgirl and the corridor guard",
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
            urge=("hurt",),
            context="I strike her actual exposed body with my fists",
            account="PRIVATE_HANDLER_HURT The civilian chooses actual bodily hurt",
        ),
    )
    submit(
        game,
        ADMIN,
        row(game, ADMIN, handler, "easy_target_react"),
        dict(
            urge=("cohort",),
            primary=(primary_id,),
            account="PRIVATE_HANDLER_HURT I choose to go along with that person's action",
        ),
    )
    choose(game, OTHER, spectator, "pass")
    choose(game, OTHER, current_ref(state(game), OTHER.user_id), "pass")
    validate(game, npc)
    choice = row(game, ADMIN, handler)
    before = state(game)
    assert not rules.records(before, rules.NpcHurt)
    assert not rules.records(before, rules.HurtCohort)
    assert not rules.get(before, rules.Reaction, primary_id).exemption
    assert not rules.get(before, rules.Reaction, handler_id).exemption
    assert any(item.identity == choice["id"] for item in InboxService(ledger).items(ADMIN))
    assert game.decision(ADMIN, choice["id"])["detail"]["hurt_cohort"]
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("participate",), text="The NPC cannot answer for the Handler"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(
                options=("participate",), text="Invent extra damage", fields={"damage": "1"}
            ),
        )
    assert state(game) == before
    # The original Handler's real owned participation precedes the NPC's first
    # bodily attempt. Neither nomination nor this answer can invent the injury.
    submit(
        GameService(ledger, dice=game.dice),
        ADMIN,
        choice,
        dict(
            outcome=("participate",),
            account="PRIVATE_HANDLER_HURT I actually go along with the original bodily action",
        ),
    )
    participating = state(game)
    participation = rules.records(participating, rules.HurtCohort)[-1]
    follower = rules.get(participating, rules.Reaction, handler_id)
    primary = rules.get(participating, rules.Reaction, primary_id)
    assert participation.actor == handler and participation.controller == ADMIN.user_id
    assert participation.primary == primary_id and participation.reaction == handler_id
    assert participation.hurt is None and participation.outcome == "participated"
    assert follower.performance_event == participation.event and not follower.completed_event
    assert follower.exemption == primary_id and primary.exemption == handler_id
    assert follower.consequence == "cohort-exempt"
    assert not primary.performance_event and not primary.completed_event
    assert not rules.records(participating, rules.NpcHurt)
    assert not rules.records(participating, rules.Harm)
    assert participating.sheets == before.sheets and participating.world == before.world
    assert game.inspect(PLAYER, action)["state"] != "complete"
    submit(
        game,
        OTHER,
        row(game, OTHER, npc),
        dict(account="PRIVATE_HANDLER_HURT The civilian actually performs the original strike"),
    )
    performed = state(game)
    hurt = rules.records(performed, rules.NpcHurt)[-1]
    assert hurt.actor == npc and hurt.controller == OTHER.user_id
    assert not hurt.damage_event
    assert not rules.get(performed, rules.Reaction, primary_id).performance_event
    assert not rules.get(performed, rules.Reaction, handler_id).completed_event
    assert not any(x.source_work == primary_id for x in performed.role_punishments)
    assert performed.sheets == before.sheets
    injury = next(x for x in game.choices(PLAYER) if x["kind"] == "battle_target_damage")
    with pytest.raises(WorkflowError):
        game.decision(ADMIN, injury["id"])
    asset = game.decision(PLAYER, injury["id"])["battle"]["assets"][0]["id"]
    asyncio.run(_npc_protection_native(game, PLAYER.user_id, injury, dict(asset=(asset,)), 98950))
    actual = state(game)
    primary = rules.get(actual, rules.Reaction, primary_id)
    follower = rules.get(actual, rules.Reaction, handler_id)
    actual_hurt = rules.records(actual, rules.NpcHurt)[-1]
    assert next(x for x in actual.sheets["2"].assets if x.id == asset).damaged
    assert actual_hurt.damage_event and primary.harm and primary.performance_event
    assert primary.exemption == handler_id and follower.exemption == primary_id
    assert primary.consequence == follower.consequence == "cohort-exempt"
    assert primary.completed_event == follower.completed_event
    assert follower.performance_event != follower.completed_event
    assert not any(x.source_work == primary_id for x in actual.role_punishments)
    assert not primary.child and not follower.child
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert "1" not in actual.sheets and actual.handler_heat == initial.handler_heat
    assert actual.sheets["3"] == before.sheets["3"] and actual.world == before.world
    assert actual.sheets["2"].heat == initial.sheets["2"].heat - 1
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        born = _history(c, game, participation.event)
        body = resolve(
            born,
            handler,
            snapshot_profiles(c, ledger.campaign_id, born),
            require_current_profile=False,
        )
        assert body.rules == "handler" and body.cell == (0, 0)
        # Handler body proof lives in the immutable event, without a fabricated
        # Pilot/NPC position hash or vessel.
        assert participation.position == body.position_sha256 is None
        assert participation.vessel == body.vessel_id is None
        assert prove(game, c, actual, participation.id) == participation
        assert prove_npc_hurt(game, c, actual, hurt.id) == actual_hurt
        for name in ("m2_actions", "m2_receipts"):
            assert (
                c.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.m2[name])
                    .where(t.m2[name].c.campaign_id == ledger.campaign_id)
                )
                == 1
            )
        assert "PRIVATE_HANDLER_HURT" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    assert (
        EasyTargetService(GameService(ledger)).view(ADMIN, handler_id)["hurt_cohort"][0]["id"]
        == participation.id
    )
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(4, 200, True, False), handler_id)
    tick(worker, gateway, 6)
    assert "PRIVATE_HANDLER_HURT" not in json.dumps(gateway.messages)

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
            assert prove(game, c, later, participation.id) == participation
            assert prove_npc_hurt(game, c, later, hurt.id) == actual_hurt
