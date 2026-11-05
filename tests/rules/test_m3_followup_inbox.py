"""Actual source follow-ups have one private inbox entry and a usable native continuation."""

import asyncio

from test_enforcer_conditioning import setup as enforcer_setup
from test_frame_swap_service import configured
from test_frame_swap_service import setup as swap_setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_lobotomy_service import begun
from test_m2_game import state
from test_mission_ui import current
from test_personal_firearm_service import activate, lose, purchase, roll_for, sync
from test_personal_firearm_service import setup as firearm_setup
from test_void_service import ready as void_ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_requisitions import open_requisitions
from girlframe.discord_adapter.m3_void import VoidMenu
from girlframe.services.inbox import InboxService
from girlframe.services.m3_requisitions import RequisitionService


def route(store, viewer, item, identity=95101):
    async def run():
        caller = current(viewer.user_id, identity)
        await caller.response.defer(ephemeral=True)
        await InboxView(InboxService(store), viewer.user_id).route(caller, item)
        return caller.edit_original_response.call_args.kwargs["view"]

    return asyncio.run(run())


def test_actual_void_source_has_one_owned_entry_and_native_questions(ledger):
    service, game, _, _, _, work = void_ready(ledger)
    inbox = InboxService(ledger)
    owned = [x for x in inbox.items(PLAYER) if x.identity == work]
    assert len(owned) == 1 and owned[0].task == "m3_void" and owned[0].incoming
    assert work not in {x.identity for x in inbox.items(OTHER)}
    form = route(ledger, PLAYER, owned[0])
    assert isinstance(form, VoidMenu) and form.owner == PLAYER.user_id
    assert state(game).sheets["2"].character_id == service.get(PLAYER, work)["actor"]["incarnation"]


def test_actual_surgery_source_deduplicates_generic_work_and_routes_current_chooser(ledger):
    _, _, _, _, _, work, identity = begun(ledger)
    inbox = InboxService(ledger)
    owned = [x for x in inbox.items(ADMIN) if x.task == "m3_lobotomy"]
    assert len(owned) == 1 and owned[0].identity == identity and owned[0].incoming
    assert not any(x.identity == work and x.source == "m3_work" for x in inbox.items(ADMIN))
    assert not any(x.task == "m3_lobotomy" for x in inbox.items(PLAYER))
    assert route(ledger, ADMIN, owned[0]).owner == 1


def test_saved_frame_swap_inbox_and_requisition_menu_remain_readable_without_registry(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, game = swap_setup(ledger, tmp_path, monkeypatch)
    identity = configured(service, game)
    before = state(game).model_dump_json()
    inbox = InboxService(ledger)
    owned = [x for x in inbox.items(PLAYER) if x.identity == identity]
    assert len(owned) == 1 and owned[0].task == "m3_frame_swap" and owned[0].incoming
    assert not any(x.identity == identity for x in inbox.items(OTHER))
    assert isinstance(route(ledger, PLAYER, owned[0]), NativeForm)
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(tmp_path / "absent-registry.json"))
    assert next(x for x in inbox.items(PLAYER) if x.identity == identity).task == "m3_frame_swap"
    assert isinstance(route(ledger, PLAYER, owned[0], 95102), NativeForm)

    async def menu():
        caller = current(2, 95103)
        await caller.response.defer(ephemeral=True)
        await open_requisitions(caller, RequisitionService(game))
        picker = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        tokens = dict(picker.options)
        assert {"frame-swap", "ability-unlock", "frame-grafting"} <= tokens.keys()
        assert "frame-swap:" + identity in tokens

    asyncio.run(menu())
    assert state(game).model_dump_json() == before


def test_earned_personal_firearm_return_has_one_private_native_entry(ledger, tmp_path, monkeypatch):
    service, cycle, game, period = firearm_setup(ledger, tmp_path, monkeypatch, period=True)
    purchase(service)
    lose(service)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    sync(service, period)
    identity = service.return_tasks(PLAYER)[0]["id"]
    owned = [x for x in InboxService(ledger).items(PLAYER) if x.identity == identity]
    assert len(owned) == 1 and owned[0].task == "m3_firearm_return"
    assert not any(x.identity == identity for x in InboxService(ledger).items(OTHER))
    assert isinstance(route(ledger, PLAYER, owned[0]), NativeForm)
    assert len(state(game).personal_firearms[0].issues) == 1


def test_enforcer_actual_rank_request_private_source_has_one_handler_control(
    ledger,
    tmp_path,
    monkeypatch,
):
    service, _ = enforcer_setup(ledger, tmp_path, monkeypatch)
    identity = service.request_rank(PLAYER, "actual-rank-request", "known-guard")["id"]
    inbox = InboxService(ledger)
    handler = [x for x in inbox.items(ADMIN) if x.identity == identity]
    assert len(handler) == 1 and handler[0].task == "m3_enforcer" and handler[0].incoming
    assert not next(x for x in inbox.items(PLAYER) if x.identity == identity).incoming
    assert isinstance(route(ledger, ADMIN, handler[0]), NativeForm)
    assert not any(x.identity == identity for x in inbox.items(OTHER))
