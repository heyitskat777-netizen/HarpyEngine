"""Reviewed response needs broaden interpretation without granting Handler omniscience."""

import json

import pytest
from test_director_activity_scene import P2Scene
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_model_adapters import Recorder
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.conversation import ConversationReply, HandlerNeedProposal
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.onboarding import WorkflowError


class NaturalHandler:
    def __init__(self, reference):
        self.reference, self.requests = reference, []

    def respond(self, request):
        self.requests.append(request)
        return ConversationReply(
            route="handler",
            disposition="answer",
            text="Review this report and hold within the authorised scope.",
            source_refs=(self.reference,),
            provider="reviewed-handler-v1",
        )


class NeedGM:
    def __init__(self, kind, reference=None):
        self.kind, self.reference, self.requests = kind, reference, []

    def propose(self, packet):
        self.requests.append(packet)
        return HandlerNeedProposal(
            request_id=packet.request_id,
            action="WAIT" if self.kind == "no_need" else "RESPOND",
            kind=self.kind,
            speech_quote=packet.request.question if self.kind == "indirect_request" else None,
            source_refs=(self.reference,) if self.reference else (),
            reason="Fixture GM interpretation of actual heard speech or known report.",
        )


def objective(context, scene):
    return next(x.id for x in context.build(ADMIN, scene).references if x.topic == "objective")


def test_indirect_request_needs_gm_review_then_actual_delivery_and_new_repeat_rearms(routed):
    observer, context, scene, game, _ = routed
    ref = objective(context, scene)
    responder = Recorder(
        {
            "disposition": "answer",
            "text": "Review this report and hold within the authorised scope.",
            "source_refs": [ref],
        }
    )
    suggestion = Recorder(
        lambda packet: {
            "request_id": packet["request_id"],
            "kind": "indirect_request",
            "action": "RESPOND",
            "speech_quote": packet["request"]["question"],
            "source_refs": [ref],
            "reason": "A pilot asked for the inspection objective over comms.",
        }
    )
    app = P2Scene.model_fixture(context, responder.client(), suggestion.client())
    service = app.session.conversation
    _, source = send(
        observer,
        scene,
        "indirect",
        text="Could someone lay out the inspection objective for me, please.",
        fictional_channel="comms",
    )
    before = state(game).model_dump_json()
    request = app.write(
        ADMIN, "need-open", scene, "handler-need-open", {"source_id": source.source_id}
    )
    packet = service.handler_need_packet(ADMIN, scene, request["id"])
    gm = NeedGM("indirect_request", ref)
    payload = {"request": request["id"]}
    saved = app.write(ADMIN, "need-generate", scene, "handler-need-generate", payload)
    assert app.write(ADMIN, "need-generate", scene, "handler-need-generate", payload) == saved
    assert len(suggestion.requests) == 1
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(suggestion.packets[0])
    assert service.pending_handler_needs(ADMIN, scene)[0]["id"] == saved["id"]
    first = service.process_message(PLAYER, "before-review", scene, source.source_id, 1)
    assert first["handler"] is None and not responder.requests
    # GM processing changed bookkeeping generation, not speech/knowledge/authority.
    assert service.private_handler_need(ADMIN, scene, saved["id"])["status"] == "awaiting_gm_review"
    service.review_handler_need(
        ADMIN,
        "need-approve",
        scene,
        saved["id"],
        "approve",
        "An indirect objective request is heard.",
    )
    response = service.process_message(PLAYER, "after-review", scene, source.source_id, 1)
    assert response["handler_decision"]["decision"]["reason"] == "reviewed_indirect_request"
    draft = response["handler"]
    assert draft["reply"] is None
    # A merely saved draft has addressed nothing.
    assert (
        service.decide_handler(PLAYER, "still-undelivered", scene, source.source_id, 1)["decision"][
            "action"
        ]
        == "RESPOND"
    )
    service.review_handler(
        ADMIN,
        "reply-approve",
        scene,
        draft["id"],
        "approve",
        "Supported by the objective reference.",
    )
    repeated = service.process_message(PLAYER, "repeat-old-source", scene, source.source_id, 1)
    assert repeated["handler"] is None
    assert repeated["handler_decision"]["decision"]["reason"] == "need_already_addressed"
    _, fresh = send(
        observer, scene, "fresh-repeat", text=packet.request.question, fictional_channel="comms"
    )
    service.acquire_handler_need(ADMIN, "new-request", scene, fresh.source_id, gm)
    assert (
        service.process_message(PLAYER, "new-response", scene, fresh.source_id, 1)["handler"]
        is not None
    )
    assert state(game).model_dump_json() == before


def test_urgent_known_general_report_can_intervene_without_keyword_trigger(routed):
    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    _, source = send(
        observer,
        scene,
        "report",
        text="The emergency battery is venting beside the relay.",
        fictional_channel="comms",
    )
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    ref = context.record(
        ADMIN,
        "report-known",
        scene,
        source.source_id,
        order,
        known_by=(handler, pilot),
        topic="general",
    )["id"]
    service = DirectorConversationService(
        context, handler=NaturalHandler(ref), handler_mode="reviewed"
    )
    assert (
        service.decide_handler(PLAYER, "legacy-gate", scene, source.source_id, 1)["decision"][
            "action"
        ]
        == "WAIT"
    )
    gm = NeedGM("urgent_known_report", ref)
    accepted = service.acquire_handler_need(ADMIN, "urgent", scene, source.source_id, gm)
    assert service.acquire_handler_need(ADMIN, "urgent", scene, source.source_id, gm) == accepted
    assert len(gm.requests) == 1
    result = service.process_message(PLAYER, "urgent-route", scene, source.source_id, 1)
    assert result["handler_decision"]["decision"]["reason"] == "reviewed_urgent_report"
    service.review_handler(
        ADMIN,
        "approve-urgent-reply",
        scene,
        result["handler"]["id"],
        "approve",
        "Only the actual report is discussed.",
    )
    assert (
        service.process_message(PLAYER, "same-report", scene, source.source_id, 1)["handler"]
        is None
    )


def test_quiet_social_and_unreported_sighting_do_not_create_model_permission(routed):
    observer, context, scene, _, _ = routed
    ref = objective(context, scene)
    responder = NaturalHandler(ref)
    service = DirectorConversationService(context, handler=responder, handler_mode="reviewed")
    _, quiet = send(
        observer,
        scene,
        "quiet",
        text="The barracks tea tastes better today.",
        fictional_channel="comms",
    )
    service.acquire_handler_need(ADMIN, "quiet-need", scene, quiet.source_id, NeedGM("no_need"))
    assert (
        service.process_message(PLAYER, "quiet-turn", scene, quiet.source_id, 1)["handler"] is None
    )
    _, hidden = send(
        observer, scene, "hidden", text="PRIVATE_UNREPORTED_SENTRY_M4", fictional_channel="private"
    )
    opened = service.open_handler_need(ADMIN, "hidden-open", scene, hidden.source_id)
    packet = service.handler_need_packet(ADMIN, scene, opened["id"])
    assert "PRIVATE_UNREPORTED_SENTRY_M4" not in packet.model_dump_json()
    with pytest.raises(WorkflowError, match="HANDLER_NEED_SPEECH"):
        service.propose_handler_need(
            ADMIN,
            "hidden-speech",
            scene,
            opened["id"],
            HandlerNeedProposal(
                request_id=opened["id"],
                action="RESPOND",
                kind="indirect_request",
                speech_quote="PRIVATE_UNREPORTED_SENTRY_M4",
                reason="This was not heard.",
            ),
        )
    with pytest.raises(WorkflowError, match="HANDLER_NEED_REPORT"):
        service.propose_handler_need(
            ADMIN,
            "hidden-urgent",
            scene,
            opened["id"],
            HandlerNeedProposal(
                request_id=opened["id"],
                action="RESPOND",
                kind="urgent_known_report",
                source_refs=(ref,),
                reason="An unrelated objective cannot prove hidden urgency.",
            ),
        )
    assert (
        service.process_message(PLAYER, "hidden-turn", scene, hidden.source_id, 1)["handler"]
        is None
    )
    assert not responder.requests
    with pytest.raises(WorkflowError):
        service.open_handler_need(PLAYER, "not-gm", scene, hidden.source_id)


def test_source_edits_and_consent_renewal_invalidate_old_need_reviews(routed):
    observer, context, scene, _, _ = routed
    ref = objective(context, scene)
    service = DirectorConversationService(
        context, handler=NaturalHandler(ref), handler_mode="reviewed"
    )
    _, source = send(
        observer,
        scene,
        "request",
        text="Could someone lay out the objective for me.",
        fictional_channel="comms",
    )
    opened = service.open_handler_need(ADMIN, "open", scene, source.source_id)
    saved = service.generate_handler_need(
        ADMIN, "generate", scene, opened["id"], NeedGM("indirect_request", ref)
    )
    observer.set_consent(PLAYER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.review_handler_need(
            ADMIN, "withdrawn-review", scene, saved["id"], "approve", "Cannot approve."
        )
    observer.set_consent(PLAYER, "renew", scene, 1, consent=True)
    with pytest.raises(WorkflowError, match="STALE_HANDLER_NEED"):
        service.review_handler_need(
            ADMIN,
            "renewed-review",
            scene,
            saved["id"],
            "approve",
            "Old consent must not resurrect it.",
        )
    current = service.open_handler_need(ADMIN, "fresh-open", scene, source.source_id)
    fresh = service.generate_handler_need(
        ADMIN, "fresh-generate", scene, current["id"], NeedGM("indirect_request", ref)
    )
    send(
        observer,
        scene,
        "edit",
        text="The request is withdrawn.",
        fictional_channel="comms",
        source_id=source.source_id,
        expected_source_revision=1,
    )
    with pytest.raises(WorkflowError, match="STALE_HANDLER_NEED"):
        service.review_handler_need(
            ADMIN, "edited-review", scene, fresh["id"], "approve", "Old source no longer applies."
        )
    assert "source_revision" in json.dumps(service.private_handler_need(ADMIN, scene, fresh["id"]))


def test_known_operational_correction_announces_once_without_manual_urgency_label(routed):
    from test_knowledge_contract_revision import commit

    from girlframe.ai.director import KnowledgeRelation
    from girlframe.ai.knowledge import Acquisition
    from girlframe.services.director_knowledge import DirectorKnowledgeService

    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    knowledge = DirectorKnowledgeService(context)
    old = "The east relay is clear."
    correction = "I withdraw that clearance: I have not checked behind the relay."
    _, first = send(observer, scene, "clearance", text=old, fictional_channel="comms")
    learned = commit(
        knowledge,
        scene,
        first.source_id,
        "learn-clearance",
        (Acquisition(basis="testimony", quote=old, recipients=(handler, pilot), topic="status"),),
    )
    _, source = send(
        observer, scene, "correct-clearance", text=correction, fictional_channel="comms"
    )
    corrected = commit(
        knowledge,
        scene,
        source.source_id,
        "learn-correction",
        (
            Acquisition(
                basis="testimony",
                quote=correction,
                recipients=(handler, pilot),
                topic="status",
                relations=(
                    KnowledgeRelation(kind="corrects", reference_id=learned["references"][0]),
                ),
            ),
        ),
    )
    identity = corrected["references"][0]
    service = DirectorConversationService(
        context, handler=NaturalHandler(identity), handler_mode="reviewed"
    )
    routed = service.process_message(PLAYER, "announce-correction", scene, source.source_id, 1)
    assert routed["handler_decision"]["decision"]["reason"] == "known_update"
    assert routed["handler_decision"]["decision"]["source_refs"] == [identity]
    service.review_handler(
        ADMIN,
        "review-correction",
        scene,
        routed["handler"]["id"],
        "approve",
        "The clearance is corrected as a claim, without inventing an enemy.",
    )
    _, quiet = send(
        observer, scene, "after-correction", text="I fold the map.", fictional_channel="comms"
    )
    assert (
        service.process_message(PLAYER, "no-repeat-correction", scene, quiet.source_id, 1)[
            "handler"
        ]
        is None
    )
