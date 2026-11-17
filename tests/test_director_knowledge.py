"""GM acquisition proposals and real Handler prompt isolation, not a keyword oracle."""

import json
from pathlib import Path

import pytest
from test_director_adjudication import prepare
from test_director_continuity import carry, new_scene, roles
from test_director_conversation import GMProbe, HandlerProbe
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_director_session import command
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick

from girlframe.ai.gm_outcomes import OutcomeNarration, OutcomeProposal
from girlframe.ai.knowledge import Acquisition, KnowledgeProposal
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError

ENEMY = "a silver enemy drone behind the eastern relay"
PRIVATE = "PRIVATE_UNREPORTED_GRID_J7"
OTHER_SECRET = "PRIVATE_OTHER_PILOT_SEES_A_RED_SNIPER"


class FixtureGM:
    """An explicit local stand-in for a GM interpretation; no language-model claims."""

    def __init__(self, quote, basis="perception", prior=None, recipient=None, topic="general"):
        self.quote, self.basis, self.prior = quote, basis, prior
        self.recipient, self.topic = recipient, topic
        self.requests = []

    def propose(self, packet):
        self.requests.append(packet)
        recipients = (self.recipient,) if self.recipient else (packet.source.actor,)
        return KnowledgeProposal(
            request_id=packet.request_id,
            updates=(
                Acquisition(
                    basis=self.basis,
                    quote=self.quote,
                    recipients=recipients,
                    prior_reference=self.prior,
                    topic=self.topic,
                ),
            ),
            private_reasoning="PRIVATE_GM_KNOWLEDGE_REASON",
        )


def test_configured_session_acquires_before_handler_and_retries_without_relearning(routed):
    observer, context, scene, game, _ = routed
    handler, _ = roles(observer, scene)

    class PerTurnGM:
        def __init__(self):
            self.requests = []

        def propose(self, packet):
            self.requests.append(packet)
            updates = ()
            if packet.source.fictional_channel == "private":
                updates = (
                    Acquisition(basis="perception", quote=ENEMY, recipients=(packet.source.actor,)),
                )
            elif ENEMY in packet.source.text:
                prior = next(
                    x for x in packet.context.references if x.text == "Reported claim: " + ENEMY
                )
                updates = (
                    Acquisition(
                        basis="report",
                        quote=ENEMY,
                        recipients=(handler,),
                        prior_reference=prior.id,
                        topic="tactical",
                    ),
                )
            return KnowledgeProposal(request_id=packet.request_id, updates=updates)

    class RecoveringHandler(HandlerProbe):
        fail = False

        def respond(self, request):
            if self.fail:
                self.fail = False
                raise OSError("Synthetic Handler transport failure after acquisition")
            return super().respond(request)

    provider, responder = PerTurnGM(), RecoveringHandler()
    session = DirectorSessionService(
        context,
        knowledge_provider=provider,
        knowledge_gm=ADMIN,
        conversation=DirectorConversationService(context, handler=responder),
    )
    before = state(game).model_dump_json()
    private = command(observer, scene, "automatic-private", f"I see {ENEMY}. {PRIVATE}").model_copy(
        update={"fictional_channel": "private"}
    )
    first = session.submit(PLAYER, scene, private)
    assert first["conversation"]["handler"] is None and not responder.requests
    question = command(observer, scene, "automatic-question", "Handler, repeat the objective?")
    second = session.submit(PLAYER, scene, question)
    assert "inspect the relay site" in second["conversation"]["handler"]["reply"]["text"]
    assert ENEMY not in responder.requests[-1].model_dump_json()
    assert PRIVATE not in responder.requests[-1].model_dump_json()
    report = command(observer, scene, "automatic-report", f"Comms: {ENEMY}").model_copy(
        update={"fictional_channel": "comms"}
    )
    responder.fail = True
    with pytest.raises(WorkflowError, match="CONVERSATION_UNAVAILABLE"):
        session.submit(PLAYER, scene, report)
    result = session.submit(PLAYER, scene, report)
    assert ENEMY in result["conversation"]["handler"]["reply"]["text"]
    assert session.submit(PLAYER, scene, report) == result
    assert len(provider.requests) == 3
    assert state(game).model_dump_json() == before


def explicit(service, scene, source, update, key):
    request = service.open(ADMIN, key + ":open", scene, source)
    return service.propose(
        ADMIN,
        key + ":propose",
        scene,
        request["id"],
        KnowledgeProposal(request_id=request["id"], updates=(update,)),
    )


def test_unreported_enemy_never_enters_handler_prompt_then_actual_comms_teaches_only_recipient(
    routed,
):
    observer, context, scene, game, dice = routed
    handler, pilot = roles(observer, scene)
    before = state(game).model_dump_json()
    gm, handler_provider = GMProbe(), HandlerProbe()
    conversation = DirectorConversationService(context, gm=gm, handler=handler_provider)
    session = DirectorSessionService(context, conversation=conversation)
    _, private_source = send(
        observer,
        scene,
        "sighting",
        text=f"I see {ENEMY}. I do not report it. {PRIVATE}",
        fictional_channel="private",
    )
    first = conversation.process_message(PLAYER, "private-turn", scene, private_source.source_id, 1)
    assert first["handler"] is None and not handler_provider.requests
    assert PRIVATE in gm.requests[-1].model_dump_json()
    provider = FixtureGM(ENEMY)
    acquired = session.knowledge.acquire(
        ADMIN, "learn-sighting", scene, private_source.source_id, provider
    )
    assert len(provider.requests) == 1 and not acquired["effects_applied"]
    review = session.knowledge.private(ADMIN, scene, acquired["id"])
    assert review["status"] == "confirmed" and "PRIVATE_GM_KNOWLEDGE_REASON" in json.dumps(review)
    with pytest.raises(WorkflowError):
        session.knowledge.private(PLAYER, scene, acquired["id"])
    assert ENEMY in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    assert ENEMY not in context.build(ADMIN, scene, actor=handler).model_dump_json()
    assert PRIVATE not in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    observer.store.engine.dispose()
    knowledge = DirectorKnowledgeService(DirectorContextService(observer))
    assert (
        knowledge.acquire(ADMIN, "learn-sighting", scene, private_source.source_id, provider)
        == acquired
    )
    assert len(provider.requests) == 1
    assert private_source.source_id not in {x["source_id"] for x in knowledge.pending(ADMIN, scene)}

    _, question = send(
        observer,
        scene,
        "instruction",
        text="Handler, repeat the objective?",
        fictional_channel="comms",
    )
    instructions = conversation.process_message(
        PLAYER, "instruction-route", scene, question.source_id, 1
    )
    assert "inspect the relay site" in instructions["handler"]["reply"]["text"]
    assert ENEMY not in handler_provider.requests[-1].model_dump_json()
    assert ENEMY not in json.dumps(instructions["handler"]) and PRIVATE not in json.dumps(
        instructions
    )
    # Even an explicit route call cannot smuggle private narration through the question field.
    hidden_reply = conversation.respond(
        PLAYER, "private-explicit-route", scene, private_source.source_id, "handler", 1
    )
    assert ENEMY not in handler_provider.requests[-1].model_dump_json()
    assert ENEMY not in json.dumps(hidden_reply)

    _, report = send(
        observer, scene, "report", text=f"Comms report: {ENEMY}.", fictional_channel="comms"
    )
    report_provider = FixtureGM(ENEMY, "report", acquired["references"][0], handler, "tactical")
    shared = knowledge.acquire(ADMIN, "learn-report", scene, report.source_id, report_provider)
    handler_context = context.build(ADMIN, scene, actor=handler)
    learned = next(x for x in handler_context.references if x.id == shared["references"][0])
    assert learned.text == "Reported claim: " + ENEMY and learned.classification == "reported_claim"
    assert not learned.dependencies  # The Pilot's private source is not exposed to the Handler.
    with observer.store.engine.connect() as c:
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    assert ENEMY not in context.build(OTHER, scene, actor=other).model_dump_json()
    response = conversation.process_message(PLAYER, "reported-route", scene, report.source_id, 1)
    assert response["handler_decision"]["decision"]["reason"] == "known_update"
    assert ENEMY in response["handler"]["reply"]["text"]
    assert PRIVATE not in handler_provider.requests[-1].model_dump_json()
    assert "PRIVATE_GM_KNOWLEDGE_REASON" not in handler_provider.requests[-1].model_dump_json()
    _, other_source = send(
        observer,
        scene,
        "other-private",
        text=OTHER_SECRET,
        viewer=OTHER,
        fictional_channel="private",
    )
    other_acquired = knowledge.acquire(
        ADMIN, "other-perception", scene, other_source.source_id, FixtureGM(OTHER_SECRET)
    )
    assert OTHER_SECRET not in context.build(PLAYER, scene, actor=pilot).model_dump_json()
    assert OTHER_SECRET not in context.build(ADMIN, scene, actor=handler).model_dump_json()
    assert OTHER_SECRET in context.build(OTHER, scene, actor=other).model_dump_json()
    assert state(game).model_dump_json() == before and dice.calls == 0
    target = new_scene(observer)
    carry(
        context,
        scene,
        target,
        tuple(acquired["references"] + shared["references"] + other_acquired["references"]),
    )
    final = context.build(ADMIN, target, actor=handler).model_dump_json()
    assert ENEMY in final and OTHER_SECRET not in final and PRIVATE not in final
    Path("var/p2-knowledge-acquisition.json").write_text(
        json.dumps(
            {
                "synthetic_only": True,
                "external_tokens": 0,
                "external_cost": 0,
                "unreported_handler_decision": first["handler_decision"]["decision"],
                "instructions_before_report": instructions["handler"]["reply"],
                "handler_after_report": response["handler"]["reply"],
                "pilot_only_and_other_private_prompts_isolated": True,
                "native_state_unchanged_before_handoff": True,
                "survives_restart_and_scene_handoff": True,
            },
            indent=2,
        )
        + "\n"
    )


def test_bad_acquisition_cannot_invent_hearing_truth_or_another_pilots_disclosure(routed):
    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    _, source = send(observer, scene, "private", text=ENEMY, fictional_channel="private")
    with pytest.raises(WorkflowError, match="UNPROVEN_PERCEPTION"):
        explicit(
            service,
            scene,
            source.source_id,
            Acquisition(basis="perception", quote=ENEMY, recipients=(handler,)),
            "leak",
        )
    with pytest.raises(WorkflowError, match="UNPROVEN_DISCLOSURE"):
        context.record(ADMIN, "legacy-leak", scene, source.source_id, 4, known_by=(handler,))
    with pytest.raises(WorkflowError, match="UNPROVEN_OUTCOME"):
        explicit(
            service,
            scene,
            source.source_id,
            Acquisition(basis="outcome", quote=ENEMY, recipients=(pilot,)),
            "truth",
        )
    with pytest.raises(WorkflowError, match="UNGROUNDED_KNOWLEDGE"):
        explicit(
            service,
            scene,
            source.source_id,
            Acquisition(basis="perception", quote="invented location", recipients=(pilot,)),
            "invent",
        )
    acquired = service.acquire(ADMIN, "proper", scene, source.source_id, FixtureGM(ENEMY))
    with pytest.raises(WorkflowError, match="DUPLICATE_KNOWLEDGE"):
        service.acquire(ADMIN, "duplicate-fact", scene, source.source_id, FixtureGM(ENEMY))
    report = Acquisition(
        basis="report",
        quote=ENEMY,
        recipients=(handler,),
        prior_reference=acquired["references"][0],
    )
    with pytest.raises(WorkflowError, match="UNPROVEN_REPORT"):
        explicit(service, scene, source.source_id, report, "not-comms")
    _, spoof = send(observer, scene, "spoof", text=ENEMY, viewer=OTHER, fictional_channel="comms")
    with pytest.raises(WorkflowError, match="UNPROVEN_REPORT"):
        explicit(service, scene, spoof.source_id, report, "not-speaker-known")
    with pytest.raises(WorkflowError):
        service.open(PLAYER, "not-gm", scene, source.source_id)
    unavailable = pilot.model_copy(update={"entity": "999"})
    with pytest.raises(WorkflowError, match="INVALID_RECIPIENT"):
        explicit(
            service,
            scene,
            source.source_id,
            Acquisition(basis="perception", quote=ENEMY, recipients=(unavailable,)),
            "unknown-actor",
        )


def test_stale_proposal_rejects_and_source_correction_preserves_append_only_history(routed):
    observer, context, scene, _, _ = routed
    _, pilot = roles(observer, scene)
    service = DirectorKnowledgeService(context)
    _, source = send(observer, scene, "source", text=ENEMY, fictional_channel="private")
    proposal = explicit(
        service,
        scene,
        source.source_id,
        Acquisition(basis="perception", quote=ENEMY, recipients=(pilot,)),
        "pending",
    )
    assert service.private(ADMIN, scene, proposal["id"])["status"] == "awaiting_confirmation"
    send(
        observer,
        scene,
        "edit",
        text="The shape is an abandoned shell.",
        source_id=source.source_id,
        expected_source_revision=1,
        fictional_channel="private",
    )
    with pytest.raises(WorkflowError, match="STALE_KNOWLEDGE_PROPOSAL"):
        service.confirm(ADMIN, "reject-stale", scene, proposal["id"])
    assert service.private(ADMIN, scene, proposal["id"])["status"] == "stale_reopen_source"
    acquired = service.acquire(
        ADMIN, "corrected", scene, source.source_id, FixtureGM("an abandoned shell")
    )
    send(
        observer,
        scene,
        "edit-again",
        text="I cannot identify the shape.",
        source_id=source.source_id,
        expected_source_revision=2,
        fictional_channel="private",
    )
    with pytest.raises(WorkflowError, match="STALE_KNOWLEDGE"):
        context.build(ADMIN, scene)
    metadata = context.archive_review(ADMIN, scene)
    context.archive(
        ADMIN,
        "retire-source",
        scene,
        metadata["revision"],
        tuple(acquired["references"]),
        "Source correction; retain history.",
    )
    with observer.store.engine.connect() as c:
        assert any("an abandoned shell" in x.text for x in context._references(c, scene))
    assert "abandoned shell" not in context.build(PLAYER, scene, actor=pilot).model_dump_json()


def test_provider_failure_and_consent_withdrawal_apply_no_partial_knowledge(routed):
    observer, context, scene, _, _ = routed
    service = DirectorKnowledgeService(context)
    _, source = send(observer, scene, "source", text=ENEMY, fictional_channel="private")

    class Failing(FixtureGM):
        def propose(self, packet):
            raise OSError("PRIVATE_PROVIDER_ERROR")

    with pytest.raises(WorkflowError, match="KNOWLEDGE_PROVIDER_UNAVAILABLE"):
        service.acquire(ADMIN, "retry", scene, source.source_id, Failing(ENEMY))
    provider = FixtureGM(ENEMY)
    result = service.acquire(ADMIN, "retry", scene, source.source_id, provider)
    assert service.acquire(ADMIN, "retry", scene, source.source_id, provider) == result
    assert len(provider.requests) == 1
    request = service.open(ADMIN, "late-source", scene, source.source_id)
    saved = service.generate(ADMIN, "late-proposal", scene, request["id"], provider)
    observer.set_consent(PLAYER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.confirm(ADMIN, "blocked-consent", scene, saved["id"])


def test_native_approved_outcome_can_teach_only_selected_actual_recipients(routed):
    observer, context, scene, game, _ = routed
    _, _, native, worker, gateway = prepare(routed, "Hold the calibration needle steady.", "native")
    answer(game, ADMIN, "handler_keep", flag=True, text="The needle is held steady.")
    tick(worker, gateway, 5)
    session = DirectorSessionService(context)
    request = session.outcomes.open(ADMIN, "narrate-open", scene, "completed", native)
    packet = session.outcomes.packet(ADMIN, scene, request["id"])
    text = "The calibration needle remains steady."
    saved = session.outcomes.propose(
        ADMIN,
        "narrate-propose",
        scene,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=OutcomeNarration(text=text, effect_refs=("tier",)),
            cited_evidence=("source", "native"),
            private_reasoning="PRIVATE_NATIVE_REASON",
        ),
    )
    session.outcomes.confirm(ADMIN, "narrate-confirm", scene, saved["id"])
    narration = session.contributions(PLAYER, scene)[-1]
    handler, _ = roles(observer, scene)
    before = state(game).model_dump_json()
    learned = session.knowledge.acquire(
        ADMIN, "learn-native", scene, narration["id"], FixtureGM(text, "outcome", recipient=handler)
    )
    reference = next(
        x
        for x in context.build(ADMIN, scene, actor=handler).references
        if x.id == learned["references"][0]
    )
    assert reference.classification == "approved_outcome" and text in reference.text
    with observer.store.engine.connect() as c:
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    assert text not in context.build(OTHER, scene, actor=other).model_dump_json()
    assert state(game).model_dump_json() == before
