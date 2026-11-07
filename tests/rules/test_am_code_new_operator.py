"""One real Code high reveals a first-time NPC and grants actual Scrutinized effects."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_physical_operations import place
from test_world import initial

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m3_am import open_am
from girlframe.discord_adapter.m3_am_code import open_code
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_code as code
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_am_code import CodeService, prove_code_discovery
from girlframe.services.m3_am_scrutinized import ScrutinyService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def high(store, tmp_path, monkeypatch, *, refuge=False):
    _, game = service(store, girl="AM", frame="THE ENFORCER")
    approved(store, game, tmp_path, monkeypatch, extra=(am.RULE, code.RULE))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(subsystems=store.policy.m3_approval.subsystems | {"world"})
            )
        )
    )
    with store.transaction() as c:
        actual = state(game)
        actual.world = initial()
        actual = place(actual, 2, mode="outside_frame")
        if refuge:
            actual.facts.append(
                dict(
                    kind="recorded_handler_recovery_position",
                    actor=active_handler(actual).model_dump_json(),
                    cell=json.dumps([0, 0]),
                )
            )
        actual.facts.append(dict(kind="synthetic_private_memory", body="PRIVATE_ORIGINAL_OOC_ONLY"))
        game.event(c, 1, str(uuid4()), "synthetic.actual_first_time_circuits_scene", actual)
    world = WorldService(MissionService(store))
    npc = ActorRef(kind="npc", entity="actual-first-time-circuit-operator")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Actual first-time operator",
            detail="Actual ordinary co-present technician",
            jobs=("guard",),
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    cast_target(game, npc)
    source = CodeService(game)
    assert not am.discoveries(state(game))
    assert source.menu(PLAYER, 900)["known"] == []

    async def actual_source():
        actor = current(2, 974001)
        actor.channel_id = 900
        await actor.response.defer(ephemeral=True)
        await open_am(actor, ScrutinyService(game))
        entry = actor.edit_original_response.call_args.kwargs["view"]
        assert "code" in dict(next(x for x in entry.fields if x.key == "action").options)
        entry.values.update(action=("code",))
        menu_interaction = current(2, 974002)
        await entry.confirm.callback(menu_interaction)
        menu = menu_interaction.edit_original_response.call_args.kwargs["view"]
        operator = source.menu(PLAYER, 900)["operators"][0]
        menu.values.update(source=("operator:" + operator["id"],))
        selected = current(2, 974003)
        await menu.confirm.callback(selected)
        actual = selected.edit_original_response.call_args.kwargs["view"]
        actual.values.update(
            records_subject=("none",), account="Actual first-time circuits with this technician"
        )
        confirmed = current(2, 974004)
        await actual.confirm.callback(confirmed)
        assert actual.completed, str(confirmed.edit_original_response.call_args)
        identity = code.sessions(state(game))[0].id
        operator = current(1, 974005)
        await operator.response.defer(ephemeral=True)
        await open_code(operator, source, channel=900)
        menu = operator.edit_original_response.call_args.kwargs["view"]
        menu.values.update(source=("confirm:" + identity,))
        selected = current(1, 974006)
        await menu.confirm.callback(selected)
        actual = selected.edit_original_response.call_args.kwargs["view"]
        actual.values.update(
            account="Actual local circuit access, no earlier adjustment knowledge",
            operator_lower=("yes",),
            operator_human=("yes",),
        )
        confirmation = current(1, 974007)
        await actual.confirm.callback(confirmation)
        assert actual.completed, str(confirmation.edit_original_response.call_args)
        return identity

    identity = asyncio.run(actual_source())
    maintenance = code.session(state(game), identity)
    from girlframe.services.m3_am_scrutinized import _history

    assert maintenance.confirmed_event is not None
    with store.engine.connect() as c:
        confirmed_revision = _history(game, c, maintenance.confirmed_event).revision
    assert (
        source.confirm(
            ADMIN,
            "974007",
            identity,
            confirmed_revision - 1,
            "Actual local circuit access, no earlier adjustment knowledge",
            operator_lower=True,
            operator_human=True,
        )["action_id"]
        == maintenance.root
    )
    assert (
        maintenance.new_operator and not maintenance.discovery and not am.discoveries(state(game))
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    before = state(game)
    game.dice.faces = (6, 6)
    selected = code.choices(before, current_ref(before, 2))[0]
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=code.PLAY,
            parent=maintenance.root,
            source_work=identity,
            target_actor=npc,
            gain=1,
            identity=selected.id,
            heat=1,
            trigger_confirmed=True,
            context="Actual first-time NPC performs circuits on this original AM",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    actual = state(game)
    updated = code.session(actual, identity)
    assert updated.new_discovery and actual.order == before.order and game.dice.calls == 1
    assert not any(x["kind"] == "am_select" for x in game.choices(PLAYER))
    assert not any(x["kind"] == "am_handler_options" for x in game.choices(ADMIN))
    with store.engine.connect() as c:
        assert game.action(c, action)["data"]["result"]["tier"] == "high"
    answer(game, ADMIN, "am_code_options", options=("backup",))
    assert any(x["kind"] == "am_select" for x in game.choices(PLAYER))
    assert not any(x["kind"] == "am_select" for x in game.choices(ADMIN))
    return game, source, updated.new_discovery, action, maintenance.root, worker, gateway


def test_new_operator_high_secret_real_bond_then_actual_npc_order(ledger, tmp_path, monkeypatch):
    game, source, identity, action, root, worker, gateway = high(ledger, tmp_path, monkeypatch)
    before = state(game)
    value = am.discovery(before, identity)
    receipt = copy.deepcopy(game.inspect(PLAYER, action)["receipt"])
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "am_select")
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("secret",), text="Wrong human"),
        )
    decision = game.decision(PLAYER, row["id"])
    assert "secret" in decision["am_scrutinized"]["options"]
    answer(
        game,
        PLAYER,
        "am_select",
        options=("secret",),
        text="Please keep my actual adjustment secret",
    )
    actual = state(game)
    assert depth(actual, value.actor, value.discoverer) == 1
    assert am.holds_secret(actual, am.discovery(actual, identity))
    assert code.session(actual, value.code_origin).phase == "complete"
    assert (
        game.inspect(PLAYER, action)["state"] == game.inspect(PLAYER, root)["state"] == "complete"
    )
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert prove_code_discovery(game, c, actual, game.action(c, action)).id == identity
        forged_contact = actual.model_copy(deep=True)
        maintenance = code.session(forged_contact, value.code_origin)
        code.put(
            forged_contact,
            maintenance.model_copy(update=dict(confirmation="Forged circuit access")),
        )
        with pytest.raises(WorkflowError, match="confirmed circuit access"):
            prove_code_discovery(game, c, forged_contact, game.action(c, action))
        missing_contact = actual.model_copy(deep=True)
        code.put(missing_contact, maintenance.model_copy(update=dict(confirmed_event=None)))
        with pytest.raises(WorkflowError):
            prove_code_discovery(game, c, missing_contact, game.action(c, action))
        fake_contact = actual.model_copy(deep=True)
        code.put(
            fake_contact,
            maintenance.model_copy(update=dict(confirmed_event="unproved-confirmation")),
        )
        with pytest.raises(WorkflowError):
            prove_code_discovery(game, c, fake_contact, game.action(c, action))
        forged = actual.model_copy(deep=True)
        am.put(forged, value.model_copy(update=dict(code_origin="forged-maintenance")))
        with pytest.raises((WorkflowError, ValueError)):
            prove_code_discovery(game, c, forged, game.action(c, action))
    tick(worker, gateway, 5)
    order = ScrutinyService(game).secret_order(
        ADMIN,
        str(uuid4()),
        identity,
        900,
        state(game).revision,
        "Actually keep quiet and remain here",
    )
    tick(worker, gateway, 3)
    answer(game, PLAYER, "order_response", options=("obedient",))
    assert game.inspect(PLAYER, order["action_id"])["state"] == "complete"
    tick(worker, gateway, 5)
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] == receipt
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert "PRIVATE_" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    final = state(game)
    assert game.rebuild() > 0 and state(game) == final


def test_new_operator_high_refuge_real_handler_endpoint_and_source_guard(
    ledger, tmp_path, monkeypatch
):
    from girlframe.engine.m3_handler_play_state import Effect
    from girlframe.services.m3_handler_plays import HandlerPlayService, request_from_play

    game, source, identity, action, root, worker, gateway = high(
        ledger, tmp_path, monkeypatch, refuge=True
    )
    answer(
        game,
        PLAYER,
        "am_select",
        options=("refuge",),
        text="I take actual refuge beside my Handler",
    )
    before = state(game)
    value = am.discovery(before, identity)
    assert value.refuge_grant and game.inspect(PLAYER, action)["state"] != "complete"
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
        forged = copy.deepcopy(actual)
        forged["data"]["am_scrutinized"].pop("code_origin")
        row = next(x for x in game.pending(c, action) if x["kind"] == "am_handler")
        with pytest.raises(WorkflowError):
            request_from_play(
                game,
                c,
                before.model_copy(deep=True),
                forged,
                row["id"],
                "am_scrutinized.refuge",
                str(uuid4()),
                targets=(value.actor,),
            )
    handler = HandlerPlayService(ledger)
    data = handler.get(ADMIN, value.refuge_grant)
    handler.submit(
        ADMIN,
        str(uuid4()),
        value.refuge_grant,
        data["game_revision"],
        "brief",
        Effect(kind="brief", account="Actual Handler explains the newly discovered circuit risk"),
    )
    assert (
        game.inspect(PLAYER, action)["state"] == game.inspect(PLAYER, root)["state"] == "complete"
    )
    assert game.dice.calls == 1 and code.session(state(game), value.code_origin).phase == "complete"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
