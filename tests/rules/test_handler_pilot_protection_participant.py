"""The original Handler actually joins native Pilot protection before its consequence."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_easy_target import ready, source, validate
from test_handler_use_cohort import row, submit
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_easy_target import (
    EasyTargetService,
    prove_npc_protection,
    prove_protection_cohort,
)
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_native_original_handler_joins_actual_pilot_protection_before_failure(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    handler = current_ref(state(game), ADMIN.user_id)
    protector = current_ref(state(game), OTHER.user_id)
    cast_change(CastService(ActorService(MissionService(ledger))), ADMIN, "join", handler)
    # Facilitating the scene does not establish physical presence. The real
    # ordinary movement source brings this Handler's body to the other people.
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
        account="The actual Handler walks to the Newgirl and her native Girl protector",
    )
    initial = state(game)
    action = source(game, worker, gateway, faces=(5, 5), selected=protector)
    primary_id, handler_id = (rules.identity(action, ref) for ref in (protector, handler))
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [5, 5]
    submit(
        game,
        OTHER,
        row(game, OTHER, protector, "easy_target_react"),
        dict(
            urge=("protect",),
            context="Actually guard the corridor against interruptions",
            account="PRIVATE_HANDLER_PILOT_PROTECTION The native Girl chooses to guard her work",
        ),
    )
    submit(
        game,
        ADMIN,
        row(game, ADMIN, handler, "easy_target_react"),
        dict(
            urge=("cohort",),
            primary=(primary_id,),
            account="PRIVATE_HANDLER_PILOT_PROTECTION I choose to join her guard",
        ),
    )
    validate(game, protector)
    choice = row(game, ADMIN, handler)
    before = state(game)
    assert not rules.records(before, rules.NpcProtection)
    assert not rules.records(before, rules.ProtectionCohort)
    assert not rules.get(before, rules.Reaction, primary_id).exemption
    # Choosing/validating participation cannot replace the original Pilot's own
    # performance. An actual protective source must exist first.
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("participate",), text="The Pilot has not started guarding yet"),
        )
    assert state(game) == before
    submit(
        game,
        OTHER,
        row(game, OTHER, protector),
        dict(account="PRIVATE_HANDLER_PILOT_PROTECTION The native Girl actually stands guard"),
    )
    before = state(game)
    protection = rules.records(before, rules.NpcProtection)[-1]
    assert protection.actor == protector and protection.controller == OTHER.user_id
    assert controls.view(ADMIN, primary_id)["can_report_failure"]
    assert game.inspect(PLAYER, action)["state"] != "complete"
    choice = row(game, ADMIN, handler)
    assert any(item.identity == choice["id"] for item in InboxService(ledger).items(ADMIN))
    assert game.decision(ADMIN, choice["id"])["detail"]["protection_cohort"]
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("participate",), text="The Pilot cannot answer for the Handler"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(
                options=("participate",), text="Invent a protective effect", fields={"armour": "1"}
            ),
        )
    assert state(game) == before
    submit(
        GameService(ledger, dice=game.dice),
        ADMIN,
        choice,
        dict(
            outcome=("participate",),
            account="PRIVATE_HANDLER_PILOT_PROTECTION I actually join her watch",
        ),
    )
    actual = state(game)
    participation = rules.records(actual, rules.ProtectionCohort)[-1]
    primary = rules.get(actual, rules.Reaction, primary_id)
    follower = rules.get(actual, rules.Reaction, handler_id)
    assert participation.actor == handler and participation.controller == ADMIN.user_id
    assert participation.primary == primary_id and participation.reaction == handler_id
    assert participation.protection == protection.id and participation.outcome == "participated"
    assert primary.exemption == handler_id and follower.exemption == primary_id
    assert primary.consequence == follower.consequence == "cohort-exempt"
    assert primary.protection_event == primary.performance_event == protection.event
    assert follower.performance_event == follower.completed_event == participation.event
    assert participation.event != protection.event
    assert not primary.child and not follower.child
    assert not rules.records(actual, rules.NpcProtectionFailure)
    assert not controls.view(ADMIN, primary_id)["can_report_failure"]
    assert not controls.view(PLAYER, primary_id)["can_failure_tag"]
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert "1" not in actual.sheets and actual.handler_heat == initial.handler_heat
    assert actual.sheets == before.sheets and actual.world == before.world
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
        # The ordinary Handler has a real cell, not a fabricated Pilot/NPC
        # placement hash or vehicle. The immutable event retains its body proof.
        assert participation.position == body.position_sha256 is None
        assert participation.vessel == body.vessel_id is None
        assert prove_protection_cohort(game, c, actual, participation.id) == participation
        assert prove_npc_protection(game, c, actual, protection.id) == protection
        for name in ("m2_actions", "m2_receipts"):
            assert (
                c.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.m2[name])
                    .where(t.m2[name].c.campaign_id == ledger.campaign_id)
                )
                == 1
            )
        assert "PRIVATE_HANDLER_PILOT_PROTECTION" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    assert (
        EasyTargetService(GameService(ledger)).view(ADMIN, handler_id)["protection_cohort"][0]["id"]
        == participation.id
    )
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(4, 200, True, False), handler_id)
    tick(worker, gateway, 6)
    assert "PRIVATE_HANDLER_PILOT_PROTECTION" not in json.dumps(gateway.messages)

    # Original source proof survives a new scene bound to the same channel;
    # it must not reinterpret the saved performance through a live profile.
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
            assert prove_protection_cohort(game, c, later, participation.id) == participation
            assert prove_npc_protection(game, c, later, protection.id) == protection
