"""The actual native Girl protects, fails and receives the Newgirl's owned Tag."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import ready, source
from test_handler_use_cohort import row, submit
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_easy_target import open_easy_target
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_easy_target import (
    EasyTargetService,
    prove_npc_protection,
    prove_protection_failure,
)
from girlframe.services.m3_easy_target_pilot_protection import primary as validate_pilot_body
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def test_native_pilot_protection_failure_keeps_owned_tag(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initial = state(game)
    protector = current_ref(initial, OTHER.user_id)
    action = source(game, worker, gateway)
    identity = rules.identity(action, protector)
    receipt = game.inspect(PLAYER, action)["receipt"]
    submit(
        game,
        OTHER,
        row(game, OTHER, protector, "easy_target_react"),
        dict(
            urge=("protect",),
            context="My actual Girl stands watch at the Newgirl's corridor",
            account="PRIVATE_PILOT_PROTECT I choose to keep unwanted visitors away",
        ),
    )
    reaction = rules.get(state(game), rules.Reaction, identity)
    assert reaction.actor == reaction.performer == protector
    assert reaction.play is None and reaction.child is None
    validation = row(game, ADMIN, protector, "easy_target_validate")
    detail = game.decision(ADMIN, validation["id"])["detail"]
    assert detail["pilot_protect"] and not detail["handler_protect"] and not detail["npc_protect"]
    submit(
        game,
        ADMIN,
        validation,
        dict(
            yes=("yes",),
            account="Her actual exterior body can perform this ordinary non-Play watch",
        ),
    )
    choice = row(game, OTHER, protector)
    before = state(game)
    assert not rules.records(before, rules.NpcProtection)
    assert any(x.identity == choice["id"] for x in InboxService(ledger).items(OTHER))
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(text="The Handler cannot choose her performance"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(text="Invent a defense", fields={"bonus": "1"}),
        )
    # An actual native source must not invent an exterior body from a passenger overlay.
    with ledger.engine.connect() as c:
        body = resolve(
            before,
            protector,
            snapshot_profiles(c, ledger.campaign_id, before),
            require_current_profile=False,
        )
    original = rules.get(before, rules.Session, action)
    with pytest.raises(WorkflowError):
        validate_pilot_body(
            before,
            rules.get(before, rules.Reaction, identity),
            original,
            original.cast,
            body.model_copy(update=dict(inside_frame=True, subsumed=True, vitals_active=False)),
        )
    assert state(game) == before
    submit(
        GameService(ledger, dice=game.dice),
        OTHER,
        choice,
        dict(account="PRIVATE_PILOT_PROTECT I actually stand watch at her corridor"),
    )
    performed = state(game)
    protection = rules.records(performed, rules.NpcProtection)[-1]
    reaction = rules.get(performed, rules.Reaction, identity)
    # Legacy durable record names retain the actual Pilot, never a proxy NPC.
    assert protection.actor == protector and protection.controller == OTHER.user_id
    assert protection.handler == current_ref(initial, ADMIN.user_id)
    assert protection.target == current_ref(initial, PLAYER.user_id)
    assert protection.actor_position == body.position_sha256
    assert protection.actor_vessel == body.vessel_id
    assert reaction.performance_event == reaction.protection_event == protection.event
    assert not reaction.child and not reaction.failure
    assert performed.sheets == before.sheets and performed.world == initial.world
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(ADMIN, identity)["can_report_failure"]
    assert not controls.view(OTHER, identity)["can_report_failure"]
    assert not controls.view(PLAYER, identity)["can_failure_tag"]
    with pytest.raises(WorkflowError):
        controls.fail_protection(
            OTHER, str(uuid4()), identity, performed.revision, "An attempt", "An occurrence"
        )
    with pytest.raises(WorkflowError):
        controls.fail_protection(
            ADMIN, str(uuid4()), identity, performed.revision - 1, "An attempt", "An occurrence"
        )
    assert state(game) == performed

    async def report():
        opened = current(ADMIN.user_id, 99610)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_easy_target(opened, EasyTargetService(GameService(ledger)), identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"attempt", "occurred"}
        form.values.update(
            attempt="PRIVATE_PILOT_PROTECT She tried to keep the corridor clear",
            occurred="PRIVATE_PILOT_PROTECT An unwanted visitor actually passed her watch",
        )
        submitted = current(ADMIN.user_id, 99611)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(report())
    failed = state(game)
    failure = rules.records(failed, rules.NpcProtectionFailure)[-1]
    assert failure.protection == protection.id and failure.npc == protector
    assert failed.sheets == performed.sheets and failed.world == performed.world
    assert not rules.records(failed, rules.Harm)
    assert controls.view(PLAYER, identity)["can_failure_tag"]
    assert not controls.view(OTHER, identity)["can_failure_tag"]
    with pytest.raises(WorkflowError):
        controls.failure_tag(OTHER, str(uuid4()), identity, failed.revision, True, "Invent her Tag")
    assert state(game) == failed

    async def tag():
        opened = current(PLAYER.user_id, 99620)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_easy_target(opened, EasyTargetService(GameService(ledger)), identity)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(give=("yes",), account="PRIVATE_PILOT_PROTECT My unreliable guard")
        submitted = current(PLAYER.user_id, 99621)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(tag())
    actual = state(game)
    given = next(
        x for x in actual.sheets["3"].tags if x.id == "easy-target-failure-tag:" + identity
    )
    assert given.label == "PRIVATE_PILOT_PROTECT My unreliable guard"
    assert given.giver_actor == current_ref(actual, PLAYER.user_id)
    assert given.observers == (PLAYER.user_id, OTHER.user_id)
    assert not controls.view(PLAYER, identity)["can_failure_tag"]
    assert rules.get(actual, rules.Reaction, identity).consequence == "failure-tag"
    expected = before.sheets["3"].model_copy(deep=True)
    expected.tags.append(given)
    expected.revision += 1
    assert actual.sheets == {**before.sheets, "3": expected}
    assert actual.world == initial.world and actual.handler_tags == initial.handler_tags
    assert actual.handler_heat == initial.handler_heat
    assert actual.sheets["2"].heat == initial.sheets["2"].heat - 1
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        birth = _history(c, game, protection.event)
        actual_body = resolve(
            birth,
            protector,
            snapshot_profiles(c, ledger.campaign_id, birth),
            require_current_profile=False,
        )
        assert actual_body.rules == "girl_frame" and actual_body.inside_frame is False
        assert prove_npc_protection(game, c, actual, protection.id) == protection
        assert prove_protection_failure(game, c, actual, failure.id) == failure
        for name in ("m2_actions", "m2_receipts"):
            assert (
                c.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.m2[name])
                    .where(t.m2[name].c.campaign_id == ledger.campaign_id)
                )
                == 1
            )
        assert "PRIVATE_PILOT_PROTECT" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
    with pytest.raises(WorkflowError):
        controls.view(GuildViewer(4, 200, True, False), identity)
    tick(worker, gateway, 6)
    assert "PRIVATE_PILOT_PROTECT" not in json.dumps(gateway.messages)

    game.close_scene(ADMIN, str(uuid4()), 900)
    game.bind_scene(ADMIN, str(uuid4()), 900)
    for viewer in (PLAYER, OTHER):
        game.join_scene(viewer, str(uuid4()), 900)
    later = state(game)

    def no_live_profiles(*args, **kwargs):
        raise AssertionError("Historical protection must retain its original profile bindings")

    monkeypatch.setattr("girlframe.services.m3_easy_target.profiles", no_live_profiles)
    with ledger.engine.connect() as c:
        assert prove_npc_protection(game, c, later, protection.id) == protection
        assert prove_protection_failure(game, c, later, failure.id) == failure
    shown = EasyTargetService(GameService(ledger)).view(OTHER, identity)
    assert shown["npc_protection"]["actor"] == protector.model_dump(mode="json")
    assert shown["protection_failure"]["id"] == failure.id

    async def reopen():
        opened = current(OTHER.user_id, 99630)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await open_easy_target(opened, EasyTargetService(GameService(ledger)), identity)
        history = opened.edit_original_response.call_args.kwargs["view"]
        assert protection.account in "".join(x.body for x in history.pages)
        assert failure.occurred in "".join(x.body for x in history.pages)

    asyncio.run(reopen())
