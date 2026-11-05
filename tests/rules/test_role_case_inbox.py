"""A real source-owned instruction has one private native Inbox path at each owned step."""

import asyncio

from test_enforcer_conditioning import setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_punishment_service import ended
from test_role_punishments import change, instruct, source_case

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.services.inbox import InboxService


def routed(store, viewer, item, identity):
    async def run():
        caller = current(viewer.user_id, identity)
        await caller.response.defer(ephemeral=True)
        await InboxView(InboxService(store), viewer.user_id).route(caller, item)
        return caller.edit_original_response.call_args.kwargs["view"]

    return asyncio.run(run())


def test_actual_npc_case_inbox_moves_owned_instruction_scene_and_attestation_without_leaking(
    ledger,
    tmp_path,
    monkeypatch,
):
    _, game = setup(ledger, tmp_path, monkeypatch)
    service, identity = source_case(game, ActorRef(kind="npc", entity="known-guard"))
    inbox = InboxService(ledger)
    chooser = next(x for x in inbox.items(ADMIN) if x.identity == identity)
    waiting = next(x for x in inbox.items(PLAYER) if x.identity == identity)
    assert chooser.task == waiting.task == "m3_role_punishment"
    assert chooser.incoming and not waiting.incoming
    assert not any(x.identity == identity for x in inbox.items(OTHER))
    assert isinstance(routed(ledger, ADMIN, chooser, 98101), Picker)
    instruct(service, identity, Details(kind="quality_time", tag="PRIVATE_INSTRUCTION_TAG"))
    executor = next(x for x in inbox.items(PLAYER) if x.identity == identity)
    assert executor.incoming and isinstance(routed(ledger, PLAYER, executor, 98102), NativeForm)
    change(service, PLAYER, identity, scene="PRIVATE_ACTUAL_SCENE")
    subject = next(x for x in inbox.items(ADMIN) if x.identity == identity)
    assert subject.incoming and "PRIVATE_ACTUAL_SCENE" not in str(subject)
    assert isinstance(routed(ledger, ADMIN, subject, 98103), NativeForm)
    change(service, ADMIN, identity, attest=True)
    change(service, PLAYER, identity, execute=True, account="PRIVATE_ACTUAL_EXECUTION")
    assert next(x for x in inbox.items(ADMIN) if x.identity == identity).state == "resolved"
    assert state(game).role_punishments[-1].completion_event


def test_existing_pc_punishment_case_deduplicates_only_its_actual_parent_work(ledger):
    _, _, game, _, work = ended(ledger)
    _, identity = source_case(game, current_ref(state(game), 3), source_work=work)
    inbox = InboxService(ledger)
    for viewer in (ADMIN, PLAYER, OTHER):
        items = inbox.items(viewer)
        assert sum(x.identity == identity for x in items) == 1
        assert not any(x.identity == work for x in items)
        assert next(x for x in items if x.identity == identity).task == "m3_role_punishment"
