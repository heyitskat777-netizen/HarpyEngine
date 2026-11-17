"""Natural Handler prose is a gated private draft, never inferred canon/disclosure."""

import json

import jsonschema
import pytest
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.conversation import ConversationReply
from girlframe.ai.knowledge import Disclosure, KnowledgeProposal
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.onboarding import WorkflowError


class NaturalHandler:
    def __init__(self, text="Inspect the relay and report what you observe.", bad_citation=False):
        self.text, self.bad_citation, self.requests = text, bad_citation, []

    def respond(self, request):
        self.requests.append(request)
        refs = (
            ("private-gm-fact",)
            if self.bad_citation
            else tuple(ref.id for ref in request.context.references if ref.topic == "objective")
        )
        return ConversationReply(
            route="handler",
            disposition="answer",
            text=self.text,
            source_refs=refs,
            provider="reviewed-handler-v1",
        )


def service(context, provider):
    return DirectorConversationService(context, handler=provider, handler_mode="reviewed")


def test_unknown_information_has_explicit_clarification_schema_and_private_feedback(routed):
    observer, context, scene, game, _ = routed
    conversation = service(context, NaturalHandler())
    _, source = send(
        observer, scene, "unknown", text="Handler, where is the enemy?", fictional_channel="comms"
    )
    raw = ConversationReply(
        route="handler",
        disposition="answer",
        text="I do not know the location.",
        provider="reviewed-handler-v1",
    ).model_dump(mode="json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, ConversationReply.model_json_schema())
    before = state(game).model_dump_json()
    feedback = conversation.feedback_handler(ADMIN, scene, source.source_id, raw)
    assert not feedback["valid"] and feedback["errors"][0]["code"] == "HANDLER_CITATION_REQUIRED"
    raw["disposition"] = "clarification"
    assert conversation.feedback_handler(ADMIN, scene, source.source_id, raw)["valid"]
    with pytest.raises(WorkflowError):
        conversation.feedback_handler(PLAYER, scene, source.source_id, raw)
    assert state(game).model_dump_json() == before


def test_natural_reply_requires_private_gm_review_and_preserves_native_state(routed):
    observer, context, scene, game, dice = routed
    provider = NaturalHandler()
    conversation = service(context, provider)
    _, source = send(
        observer,
        scene,
        "question",
        text="Handler, repeat the objective?",
        fictional_channel="comms",
    )
    before = state(game).model_dump_json()
    result = conversation.process_message(PLAYER, "route", scene, source.source_id, 1)
    draft = result["handler"]
    assert draft["reply"] is None and draft["status"] == "awaiting_gm_review"
    assert len(provider.requests) == 1
    assert "SYNTHETIC_GM_SECRET_CANARY" not in provider.requests[0].model_dump_json()
    assert conversation.pending_handler(ADMIN, scene)[0]["id"] == draft["id"]
    with pytest.raises(WorkflowError):
        conversation.private_handler(PLAYER, scene, draft["id"])
    review = conversation.private_handler(ADMIN, scene, draft["id"])
    assert review["reply"]["text"] == provider.text
    assert review["semantic_grounding"] == "gm_review_required"
    with pytest.raises(WorkflowError):
        conversation.review_handler(
            PLAYER, "not-gm", scene, draft["id"], "approve", "My own review"
        )
    accepted = conversation.review_handler(
        ADMIN,
        "review",
        scene,
        draft["id"],
        "approve",
        "Grounded objective; no new facts or decisions.",
    )
    assert (
        conversation.review_handler(
            ADMIN,
            "review",
            scene,
            draft["id"],
            "approve",
            "Grounded objective; no new facts or decisions.",
        )
        == accepted
    )
    assert conversation.get(PLAYER, scene, draft["id"])["reply"]["text"] == provider.text
    assert not conversation.pending_handler(ADMIN, scene)
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_reviewed_mode_requires_engine_gate_and_rejects_unknown_citations(routed):
    observer, context, scene, _, _ = routed
    provider = NaturalHandler(bad_citation=True)
    conversation = service(context, provider)
    _, source = send(
        observer,
        scene,
        "question",
        text="Handler, repeat the objective?",
        fictional_channel="comms",
    )
    with pytest.raises(WorkflowError, match="HANDLER_GATE_REQUIRED"):
        conversation.respond(PLAYER, "bypass", scene, source.source_id, "handler", 1)
    assert not provider.requests
    with pytest.raises(WorkflowError, match="HANDLER_CITATION_INVALID"):
        conversation.process_message(PLAYER, "route", scene, source.source_id, 1)
    assert not conversation.pending_handler(ADMIN, scene)


def test_mixed_narration_only_delivers_accepted_speech_span_to_handler(routed):
    observer, context, scene, _, _ = routed
    handler, _ = roles(observer, scene)
    private = "PRIVATE_SILVER_SCOUT_AT_GRID_M4"
    speech = "Handler, repeat the objective?"
    _, source = send(
        observer,
        scene,
        "mixed",
        text=f'I see {private}. Over comms I say "{speech}"',
        fictional_channel="mixed",
    )
    provider = NaturalHandler()
    conversation = service(context, provider)
    first = conversation.process_message(PLAYER, "before-disclosure", scene, source.source_id, 1)
    assert first["handler"] is None and not provider.requests
    knowledge = DirectorKnowledgeService(context)
    request = knowledge.open(ADMIN, "speech-open", scene, source.source_id)
    proposal = knowledge.propose(
        ADMIN,
        "speech-propose",
        scene,
        request["id"],
        KnowledgeProposal(
            request_id=request["id"], disclosures=(Disclosure(quote=speech, recipients=(handler,)),)
        ),
    )
    knowledge.confirm(ADMIN, "speech-confirm", scene, proposal["id"])
    result = conversation.process_message(PLAYER, "after-disclosure", scene, source.source_id, 1)
    assert result["handler"]["reply"] is None
    assert provider.requests[-1].question == speech
    assert private not in provider.requests[-1].model_dump_json()
    assert private not in json.dumps(result)


def test_valid_citation_does_not_certify_prose_and_stale_approval_is_blocked(routed):
    observer, context, scene, _, _ = routed
    provider = NaturalHandler("The west gantry is clear of hostiles.")
    conversation = service(context, provider)
    _, source = send(
        observer,
        scene,
        "question",
        text="Handler, repeat the objective?",
        fictional_channel="comms",
    )
    result = conversation.process_message(PLAYER, "route", scene, source.source_id, 1)
    draft = result["handler"]
    assert draft["reply"] is None
    review = conversation.private_handler(ADMIN, scene, draft["id"])
    assert review["semantic_grounding"] == "gm_review_required"
    send(observer, scene, "next", text="I am checking my harness.", fictional_channel="private")
    with pytest.raises(WorkflowError, match="STALE_HANDLER_DRAFT"):
        conversation.review_handler(
            ADMIN, "stale-approve", scene, draft["id"], "approve", "Old draft"
        )
    conversation.review_handler(
        ADMIN,
        "reject",
        scene,
        draft["id"],
        "reject",
        "Its citations do not establish any hostile positions.",
    )
    assert conversation.get(PLAYER, scene, draft["id"])["reply"] is None
    assert conversation.get(PLAYER, scene, draft["id"])["status"] == "rejected"
