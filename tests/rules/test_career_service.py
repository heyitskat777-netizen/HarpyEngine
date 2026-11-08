"""Owned career history and a real fresh creation draft preserve original receipts."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_careers import open_archive, open_replacement, open_status
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.creation import CreationService
from girlframe.services.m3_careers import CareerService, end_in_transaction, synchronize_end
from girlframe.services.onboarding import WorkflowError


def ended(store, *, owner=PLAYER, reason="death"):
    _, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )
    receipt = store.roll_basic(owner, "original-raw-receipt", store.status(owner)["revision"])
    with store.transaction() as c:
        canon = state(game)
        profile = (
            c.execute(
                sa.select(t.characters).where(
                    t.characters.c.campaign_id == store.campaign_id,
                    t.characters.c.user_id == str(owner.user_id),
                )
            )
            .mappings()
            .one()
        )
        actor = ActorRef(
            kind="pilot",
            entity=str(owner.user_id),
            incarnation=canon.sheets[str(owner.user_id)].character_id,
        )
        source = str(uuid4())
        result = end_in_transaction(
            c,
            game,
            canon,
            actor,
            reason=reason,
            source_event=source,
            account="Actual owned ending",
            archive_id="original-ended-career",
        )
        game.event(
            c,
            owner.user_id,
            "actual-synthetic-death",
            "m3.synthetic_ending",
            result,
            event_id=source,
        )
        synchronize_end(c, game, result.career_archives[-1])
    return CareerService(store), game, actor, dict(profile), receipt


def draft():
    return DraftInput(
        callsign="NEW_GIRL",
        girl_playbook="MOCKINGBIRD",
        frame_playbook="JANUS-B",
        notes="NEW_PRIVATE_CANARY",
    )


def begin(svc, *, viewer=PLAYER, key="new-girl", preview=None):
    data = preview or svc.get(viewer, "original-ended-career")
    return svc.begin_replacement(
        viewer, key, "original-ended-career", data["game_revision"], draft()
    )


def test_fresh_draft_has_new_incarnation_empty_creation_and_keeps_original_sql_receipt_identity(
    ledger,
):
    svc, game, actor, original, receipt = ended(ledger)
    preview = svc.get(PLAYER, "original-ended-career")
    result = begin(svc, preview=preview)
    assert begin(CareerService(ledger), preview=preview) == result
    assert result["character"] != actor.incarnation
    assert "2" not in state(game).sheets
    with ledger.engine.connect() as c:
        profile = (
            c.execute(
                sa.select(t.characters).where(
                    t.characters.c.campaign_id == ledger.campaign_id,
                    t.characters.c.user_id == "2",
                )
            )
            .mappings()
            .one()
        )
        assert profile["id"] == original["id"] and profile["revision"] == original["revision"] + 1
        saved_receipt = c.scalar(
            sa.select(t.rolls.c.character_id).where(t.rolls.c.id == str(receipt.id))
        )
        assert saved_receipt == original["id"]
    creation = CreationService(ledger).get(PLAYER)
    assert not creation.draft.girl_assets and not creation.draft.frame_assets
    assert not creation.draft.girl_appearance
    assert svc.get(PLAYER, "original-ended-career")["sheet"]["permissions"] == 0
    assert ledger.get_roll_receipt(PLAYER, receipt.id).id == receipt.id


def test_archive_is_original_owner_only_and_rechecks_current_campaign_membership(ledger):
    svc, _, _, _, _ = ended(ledger)
    for viewer in (OTHER, ADMIN):
        assert not svc.archives(viewer)
        with pytest.raises(WorkflowError, match="original human owner"):
            svc.get(viewer, "original-ended-career")
    with ledger.transaction() as c:
        c.execute(
            t.members.update()
            .where(t.members.c.campaign_id == ledger.campaign_id, t.members.c.user_id == "2")
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        svc.get(PLAYER, "original-ended-career")


def test_pause_and_stale_revision_cannot_start_a_replacement(ledger):
    svc, game, _, original, _ = ended(ledger)
    preview = svc.get(PLAYER, "original-ended-career")
    ledger.safety(OTHER, "pause-new-girl", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        begin(svc, preview=preview)
    ledger.safety(OTHER, "resume-new-girl", ledger.status(OTHER)["revision"], pause=False)
    with ledger.transaction() as c:
        game.event(c, 1, "later-state", "synthetic.state", state(game))
    with pytest.raises(WorkflowError, match="STALE_CAREER"):
        begin(svc, preview=preview)
    assert state(game).incarnation_bindings[-1].active is False
    assert ledger.draft(PLAYER)["revision"] == original["revision"]


def test_handler_explicitly_assigns_new_starting_status_without_restoring_old_slot(ledger):
    svc, game, actor, _, _ = ended(ledger)
    result = begin(svc)
    requests = svc.status_requests(ADMIN)
    assert len(requests) == 1 and requests[0]["position"] is None
    with pytest.raises(WorkflowError):
        svc.assign_status(PLAYER, "self-rank", 2, result["character"], state(game).revision, 0)
    current_revision = state(game).revision
    status = svc.assign_status(ADMIN, "new-rank", 2, result["character"], current_revision, 1)
    assert status["position"] == 1 and state(game).order == (3,)
    assert (
        svc.get(PLAYER, "original-ended-career")["archive"]["actor"]["incarnation"]
        == actor.incarnation
    )


def test_native_owned_new_character_and_handler_status_controls(ledger):
    svc, game, actor, _, _ = ended(ledger)

    async def run():
        owner = current(2, 20801)
        await owner.response.defer(ephemeral=True)
        await open_archive(owner, svc, "original-ended-career")
        archive = owner.edit_original_response.call_args.kwargs["view"]
        assert not await archive.interaction_check(current(3))
        await open_replacement(owner, svc, "original-ended-career")
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(callsign="NEW_GIRL", girl=("MOCKINGBIRD",), frame=("JANUS-B",), notes="")
        await form.confirm.callback(current(2, 20802))
        assert form.completed
        character = state(game).incarnation_bindings[-1].character
        handler = current(1, 20803)
        await handler.response.defer(ephemeral=True)
        await open_status(handler, svc, 2, character)
        status = handler.edit_original_response.call_args.kwargs["view"]
        assert not await status.interaction_check(current(2))
        status.values.update(position=("1",))
        await status.confirm.callback(current(1, 20804))
        assert status.completed

    asyncio.run(run())
    assert state(game).incarnation_bindings[-1].status_position == 1
    assert state(game).incarnation_bindings[-1].character != actor.incarnation
