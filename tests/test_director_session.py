"""One resumable session over native consumers; manual GM judgment, no paid inference."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_director_adjudication import prepare
from test_director_conversation import GMProbe, HandlerProbe
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeNarration, OutcomeProposal
from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
from girlframe.ai.observation import AppendSceneInput
from girlframe.database import tables as t
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError


def command(observer, scene, key, text):
    return AppendSceneInput(
        command_key=key,
        expected_scene_revision=observer.status(PLAYER, scene).scene_revision,
        speaker="pilot",
        text=text,
    )


def test_reviewed_session_classifies_speech_before_need_and_retries_without_regeneration(routed):
    from test_director_handler_needs import NaturalHandler, NeedGM, objective

    from girlframe.ai.knowledge import Disclosure, KnowledgeProposal

    observer, context, scene, game, dice = routed
    speech = "Could someone lay out the inspection objective for me, please."

    class SpeechGM:
        calls = 0

        def propose(self, packet):
            self.calls += 1
            handler = next(x for x in packet.recipients if x.kind == "handler")
            return KnowledgeProposal(
                request_id=packet.request_id,
                disclosures=(Disclosure(quote=speech, recipients=(handler,)),),
            )

    ref = objective(context, scene)
    handler, knowledge, need = NaturalHandler(ref), SpeechGM(), NeedGM("indirect_request", ref)
    conversation = DirectorConversationService(context, handler=handler, handler_mode="reviewed")
    service = DirectorSessionService(
        context,
        conversation=conversation,
        knowledge_provider=knowledge,
        knowledge_gm=ADMIN,
        need_provider=need,
        need_gm=ADMIN,
    )
    before = state(game).model_dump_json()
    cmd = command(
        observer, scene, "reviewed-pipeline", f'PRIVATE_PIPELINE_OBSERVATION. I say "{speech}"'
    )
    cmd = cmd.model_copy(update={"fictional_channel": "mixed"})
    result = service.submit(PLAYER, scene, cmd)
    draft = result["conversation"]["handler"]
    assert draft["reply"] is None
    assert handler.requests[0].question == speech
    assert need.requests[0].request.question == speech
    assert "PRIVATE_PIPELINE_OBSERVATION" not in handler.requests[0].model_dump_json()
    assert "PRIVATE_PIPELINE_OBSERVATION" not in need.requests[0].model_dump_json()
    conversation.review_handler(
        ADMIN,
        "approve-pipeline",
        scene,
        draft["id"],
        "approve",
        "The reply uses only the available objective.",
    )
    retried = service.submit(PLAYER, scene, cmd)
    assert retried["conversation"]["handler"]["reply"]["text"]
    assert knowledge.calls == 1 and len(need.requests) == 1 and len(handler.requests) == 1
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_input_and_gm_success_resume_after_handler_failure_without_duplicate_work(routed):
    observer, context, scene, game, _ = routed
    gm = GMProbe()

    class Recovering(HandlerProbe):
        attempts = 0

        def respond(self, request):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("SYNTHETIC_PROVIDER_ERROR_PRIVATE")
            return super().respond(request)

    handler = Recovering()
    service = DirectorSessionService(
        context, conversation=DirectorConversationService(context, gm=gm, handler=handler)
    )
    request = command(observer, scene, "retry", "Handler, what is the objective?")
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="CONVERSATION_UNAVAILABLE"):
        service.submit(PLAYER, scene, request)
    result = service.submit(PLAYER, scene, request)
    assert service.submit(PLAYER, scene, request) == result
    assert len(gm.requests) == 1 and handler.attempts == 2
    assert "SYNTHETIC_GM_SECRET_CANARY" in gm.requests[0].model_dump_json()
    assert "SYNTHETIC_GM_SECRET_CANARY" not in handler.requests[0].model_dump_json()
    assert "SYNTHETIC_PC_ONLY_REFERENCE" not in handler.requests[0].model_dump_json()
    assert state(game).model_dump_json() == before
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(service.work(PLAYER, scene))
    with pytest.raises(WorkflowError):
        service.work(PLAYER, scene, gm=True)
    with observer.store.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.director["inputs"])
                .where(t.director["inputs"].c.source_id == result["input"]["source_id"])
            )
            == 1
        )


def test_repeated_scope_warning_is_silent_after_real_reply_but_new_scope_rearms(routed):
    observer, context, scene, game, _ = routed
    service = DirectorSessionService(context)
    before = state(game).model_dump_json()
    text = "I will force the sealed relay open."
    first = service.submit(PLAYER, scene, command(observer, scene, "first", text))
    assert first["conversation"]["handler"] is not None
    service = DirectorSessionService(DirectorContextService(observer))
    second = service.submit(PLAYER, scene, command(observer, scene, "again", text))
    assert second["conversation"]["handler"] is None
    assert (
        second["conversation"]["handler_decision"]["decision"]["reason"]
        == "scope_already_addressed"
    )
    direct = service.submit(
        PLAYER, scene, command(observer, scene, "direct", "Handler, repeat the scope?")
    )
    assert direct["conversation"]["handler"] is not None
    with observer.store.engine.connect() as c:
        _, _, handler = observer._authorize_input(c, ADMIN, scene, "handler")
        _, _, pilot = observer._authorize_input(c, PLAYER, scene, "pilot")
        order = len(context._references(c, scene))
    _, source = send(
        observer,
        scene,
        "scope-update",
        viewer=ADMIN,
        text="Updated exercise: forced entry is not authorised while personnel evacuate.",
    )
    context.record(
        ADMIN, "new-brief", scene, source.source_id, order, known_by=(handler, pilot), topic="scope"
    )
    third = service.submit(PLAYER, scene, command(observer, scene, "new-scope", text))
    assert third["conversation"]["handler"] is not None
    assert state(game).model_dump_json() == before


def test_session_work_discovers_actual_keep_and_completion_and_orders_safe_readback(routed):
    observer, context, scene, game, dice = routed
    _, _, native, worker, gateway = prepare(routed, "I keep my hands steady.", "prepare")
    service = DirectorSessionService(context)
    work = service.work(ADMIN, scene, gm=True)
    source = next(x for x in work["outcome_sources"] if x["operation"] == "keep")
    assert source["owner_id"] == "1" and source["frame_required"]
    route = next(x for x in work["decision_routes"] if x["choice_id"] == source["source_id"])
    assert route["route"] == "typed_outcome" and route["owner_id"] == "1"
    packet_review = service.decision_context(ADMIN, scene, source["source_id"])
    assert packet_review["action"]["id"] == native and packet_review["operation"] == "keep"
    assert not service.work(PLAYER, scene)["outcome_sources"]
    frame = TaskFrame(
        stakes="Keep the needle on its mark",
        demands=(Demand(id="steady", question="Can the pilot maintain control?"),),
    )
    request = service.outcomes.open(ADMIN, "open", scene, "choice", source["source_id"], frame)
    packet = service.outcomes.packet(ADMIN, scene, request["id"])
    proposal = OutcomeProposal(
        request_id=packet.request_id,
        decision=KeepOutcome(
            verdict="enough",
            narration="The pilot holds the needle steady.",
            assessments=(
                Assessment(
                    demand_id="steady",
                    sufficient=True,
                    evidence_ids=("source", "native", "traits"),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="Fixture-authored control assessment",
                ),
            ),
        ),
        cited_evidence=("source", "native"),
        private_reasoning="SYNTHETIC_SESSION_PRIVATE_REASON",
    )
    saved = service.outcomes.propose(ADMIN, "propose", scene, request["id"], proposal)
    assert service.work(ADMIN, scene)["proposals"][0]["status"] == "awaiting_confirmation"
    service.outcomes.confirm(ADMIN, "confirm", scene, saved["id"])
    tick(worker, gateway, 5)
    service = DirectorSessionService(DirectorContextService(observer))
    work = service.work(ADMIN, scene, gm=True)
    assert work["proposals"][0]["status"] == "confirmed"
    assert any(
        x["source_kind"] == "completed" and x["source_id"] == native
        for x in work["outcome_sources"]
    )
    before = state(game).model_dump_json()
    for text in ("First readback of the committed outcome.", "Second explicit readback."):
        request = service.outcomes.open(ADMIN, str(uuid4()), scene, "completed", native)
        packet = service.outcomes.packet(ADMIN, scene, request["id"])
        saved = service.outcomes.propose(
            ADMIN,
            str(uuid4()),
            scene,
            request["id"],
            OutcomeProposal(
                request_id=packet.request_id,
                decision=OutcomeNarration(text=text, effect_refs=("tier",)),
                cited_evidence=("source", "native"),
                private_reasoning="SYNTHETIC_SESSION_PRIVATE_REASON",
            ),
        )
        service.outcomes.confirm(ADMIN, str(uuid4()), scene, saved["id"])
    readback = service.contributions(OTHER, scene)
    assert [x["ordinal"] for x in readback] == [1, 2]
    assert "First readback" in readback[0]["text"]
    assert "SYNTHETIC_SESSION_PRIVATE_REASON" not in json.dumps(readback)
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(readback)
    with observer.store.engine.connect() as c:
        _, _, handler = observer._authorize_input(c, ADMIN, scene, "handler")
        _, _, pilot = observer._authorize_input(c, PLAYER, scene, "pilot")
        order = len(context._references(c, scene))
    context.record(
        ADMIN,
        "approved-memory",
        scene,
        readback[-1]["id"],
        order,
        known_by=(handler,),
        topic="status",
    )
    assert (
        "Second explicit readback" in context.build(ADMIN, scene, actor=handler).model_dump_json()
    )
    assert (
        "Second explicit readback"
        not in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    )
    assert state(game).model_dump_json() == before and dice.calls == 1
    assert not any(
        x["source_kind"] == "completed"
        for x in service.work(ADMIN, scene, gm=True)["outcome_sources"]
    )
    observer.set_consent(PLAYER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.contributions(OTHER, scene)
