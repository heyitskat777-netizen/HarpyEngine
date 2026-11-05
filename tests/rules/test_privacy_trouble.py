"""A private-room death creates actual owned trouble without disclosing its transcript."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_scene_requisition_service import agree_and_enter, pay, propose, setup, sync

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_privacy_trouble import open_trouble
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_privacy_trouble import PrivacyTroubleService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_scene_requisitions import audience, privacy
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def incident(store, *, both=False):
    scenes, cycle, game, period = setup(store)
    pay(scenes)
    activate(cycle, game, period)
    sync(scenes, period)
    identity = scenes.scene_tasks(PLAYER)[0]["id"]
    propose(scenes, identity)
    agree_and_enter(scenes, identity)
    data = scenes.scene_get(PLAYER, identity)
    ref = ActorRef.model_validate(data["benefit"]["actor"])
    with store.transaction() as c:
        canon, source = state(game), str(uuid4())
        ended = end_in_transaction(
            c,
            game,
            canon,
            ref,
            reason="death",
            source_event=source,
            account="Actual original character died",
            archive_id=str(uuid4()),
        )
        archives = [ended.career_archives[-1]]
        if both:
            other = ActorRef.model_validate(data["benefit"]["companion"])
            ended = end_in_transaction(
                c,
                game,
                ended,
                other,
                reason="death",
                source_event=source,
                account="The other original character died",
                archive_id=str(uuid4()),
            )
            archives.append(ended.career_archives[-1])
        game.event(
            c, 1, "actual-private-room-incident", "m3.synthetic_ending", ended, event_id=source
        )
        for archive in archives:
            synchronize_end(c, game, archive)
    work = t.m3["m3_required_work"]
    with store.engine.connect() as c:
        task = c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == store.campaign_id, work.c.kind == "privacy_trouble"
            )
        )
    return scenes, PrivacyTroubleService(store), game, identity, task


def test_death_closes_protection_with_actual_ending_instead_of_fake_consent_or_public_transcript(
    ledger,
):
    scenes, trouble, game, identity, task = incident(ledger)
    data = scenes.scene_get(OTHER, identity)
    room = data["benefit"]["scene"]
    assert room["career_end"] and room["closed_by"] is None
    assert not data["active"]
    with ledger.engine.connect() as c:
        assert audience(c, ledger, room["id"]) == (2, 3)
        assert privacy(c, ledger, room["id"]) is None
    inquiry = trouble.get(ADMIN, task)
    assert inquiry["own"] and inquiry["source_actor"]["entity"] == "3"
    assert "PRIVATE_ACTUAL_SCENE" not in str(inquiry)
    assert "PRIVATE_ORIGINAL_PURCHASE" not in str(inquiry)
    with pytest.raises(WorkflowError):
        trouble.get(PLAYER, task)
    assert "3" in state(game).sheets


def test_actual_inquiry_requires_survivor_owned_response_and_allows_refusal(ledger):
    _, svc, game, _, task = incident(ledger)
    data = svc.get(ADMIN, task)
    result = svc.choose(
        ADMIN,
        "actual-inquiry",
        task,
        data["revision"],
        "inquiry",
        question="What do you choose to tell me about the death?",
        method="Actual radio inquiry",
    )
    child = svc.get(OTHER, result["child"])
    assert child["question"] == "What do you choose to tell me about the death?"
    with pytest.raises(WorkflowError):
        svc.respond(
            ADMIN,
            "cannot-forge-disclosure",
            child["id"],
            child["revision"],
            disclose=True,
            account="Cannot answer for the Girl",
        )
    outcome = svc.respond(
        OTHER, "actual-refusal", child["id"], child["revision"], disclose=False, account=""
    )
    assert not outcome["disclosed"]
    assert svc.get(ADMIN, task)["state"] == "resolved"
    assert svc.get(ADMIN, task)["response"] == "" and svc.get(ADMIN, task)["disclosed"] is False
    assert any(
        x.get("kind") == "privacy_inquiry_response" and x.get("disclosed") == "False"
        for x in state(game).facts
    )


def test_both_ended_creates_actual_handler_report_without_manufacturing_witnesses(ledger):
    _, svc, game, _, task = incident(ledger, both=True)
    data = svc.get(ADMIN, task)
    assert data["source_actor"] is None
    result = svc.choose(
        ADMIN,
        "actual-no-survivor-inquiry",
        task,
        data["revision"],
        "inquiry",
        question="What physical evidence can be confirmed?",
        method="Actual inspection of the discovered room",
        report="The original occupants are dead. Cause and events remain unconfirmed.",
        evidence="unknown",
    )
    assert result["state"] == "actual_report_recorded"
    assert svc.get(ADMIN, task)["state"] == "resolved" and not state(game).sheets


def test_chosen_discipline_is_a_real_owned_punishment_and_must_apply_actual_effect(ledger):
    _, svc, game, _, task = incident(ledger)
    data = svc.get(ADMIN, task)
    result = svc.choose(ADMIN, "real-trouble-discipline", task, data["revision"], "punishment")
    discipline = PunishmentService(ledger)
    work = discipline.get(ADMIN, result["child"])
    discipline.propose_scene(
        ADMIN,
        "actual-consequence-scene",
        work["id"],
        work["revision"],
        work["game_revision"],
        "Actual post-incident discipline",
    )
    for viewer in (ADMIN, OTHER):
        work = discipline.get(viewer, work["id"])
        discipline.attest_scene(
            viewer, str(uuid4()), work["id"], work["revision"], work["game_revision"]
        )
    work = discipline.get(ADMIN, work["id"])
    old = state(game).sheets["3"].heat
    discipline.apply(
        ADMIN,
        "actual-source-punishment",
        work["id"],
        work["revision"],
        work["game_revision"],
        Details(kind="stimulant_injection"),
    )
    assert state(game).sheets["3"].heat == old + 7
    assert discipline.get(ADMIN, work["id"])["state"] == "resolved"


def test_native_inquiry_shares_only_the_owned_survivor_response(ledger):
    _, svc, _, _, task = incident(ledger)

    async def run():
        handler = current(1, 21201)
        await handler.response.defer(ephemeral=True)
        await open_trouble(handler, svc, task)
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            route=("inquiry",), question="What do you share?", method="Actual direct question"
        )
        await form.confirm.callback(current(1, 21202))
        assert form.completed
        child = svc.get(ADMIN, task)["child"]
        survivor = current(3, 21203)
        await survivor.response.defer(ephemeral=True)
        await open_trouble(survivor, svc, child)
        answer = survivor.edit_original_response.call_args.kwargs["view"]
        assert not await answer.interaction_check(current(1))
        answer.values.update(disclose=("yes",), account="This is all I choose to share.")
        await answer.confirm.callback(current(3, 21204))
        assert answer.completed

    asyncio.run(run())
    assert svc.get(ADMIN, task)["response"] == "This is all I choose to share."
