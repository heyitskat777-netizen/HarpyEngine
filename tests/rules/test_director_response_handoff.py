"""A real controller answers before the original native owner adjudicates a social goal."""

import pytest
from test_director_adjudication import prepare
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeProposal
from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
from girlframe.services.gm_outcomes import GMOutcomeService
from girlframe.services.onboarding import WorkflowError


def pending(routed):
    observer, context, scene, game, dice = routed
    goal = "Ask the other Pilot to agree to lower the training channel volume."
    _, _, action, _, _ = prepare(routed, goal, "request-social-play")
    with observer.store.engine.connect() as c:
        target = observer._authorize_input(c, OTHER, scene, "pilot")[2]
        choice = next(x for x in game.pending_choices(c, ADMIN) if x["kind"] == "handler_keep")
    service = GMOutcomeService(context, require_response_scope=True)
    opened = service.open(
        ADMIN,
        "open-social",
        scene,
        "choice",
        choice["id"],
        TaskFrame(
            stakes=goal,
            demands=(Demand(id="agreement", question=goal),),
            response_scope="other",
            response_target=target,
        ),
    )
    return service, scene, game, dice, action, opened


def proposal(service, scene, opened, verdict):
    packet = service.packet(ADMIN, scene, opened["id"])
    return OutcomeProposal(
        request_id=packet.request_id,
        decision=KeepOutcome(
            verdict=verdict,
            narration="The other Pilot agrees." if verdict == "enough" else "The Pilot declines.",
            assessments=(
                Assessment(
                    demand_id="agreement",
                    sufficient=verdict == "enough",
                    evidence_ids=("native", "traits", "target_response"),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="Assess controlled delivery and the actual controller's answer.",
                ),
            ),
        ),
        cited_evidence=("source", "native", "target_response"),
        private_reasoning="PRIVATE_GM_SOCIAL_ASSESSMENT",
    )


@pytest.mark.parametrize("decision,verdict", [("accept", "enough"), ("decline", "not_enough")])
def test_actual_target_answer_resumes_without_overriding_controller_or_native_owner(
    routed, decision, verdict
):
    service, scene, game, dice, action, opened = pending(routed)
    before = state(game).model_dump_json()
    requested = service.responses.request(
        ADMIN,
        "request-response",
        scene,
        opened["id"],
        "Does your Pilot agree to lower the training channel volume?",
    )
    identity = requested["id"]
    assert service.responses.pending(OTHER, scene)[0]["id"] == identity
    assert not service.responses.pending(PLAYER, scene)
    assert "PRIVATE_GM" not in str(service.responses.get(OTHER, scene, identity))
    with pytest.raises(WorkflowError, match="RESPONSE_NOT_OWNED"):
        service.responses.answer(PLAYER, "wrong-answer", scene, identity, "accept", "I agree.")
    with pytest.raises(WorkflowError, match="TARGET_RESPONSE_REQUIRED"):
        service.responses.resume(ADMIN, "premature-resume", scene, identity)
    reply = "I agree to lower it." if decision == "accept" else "I decline; keep it at this level."
    answer = service.responses.answer(OTHER, "owned-answer", scene, identity, decision, reply)
    assert (
        service.responses.answer(OTHER, "owned-answer", scene, identity, decision, reply) == answer
    )
    assert not service.responses.pending(OTHER, scene)
    assert (
        service.responses.pending(ADMIN, scene, gm=True)[0]["status"] == "answered_resume_required"
    )
    assert state(game).model_dump_json() == before and dice.calls == 1
    resumed = service.responses.resume(ADMIN, "resume-social", scene, identity)
    if decision == "accept":
        bound = service.packet(ADMIN, scene, resumed["id"])
        with pytest.raises(WorkflowError, match="STALE_TARGET_RESPONSE"):
            service.open(
                ADMIN,
                "cannot-reuse-answer",
                scene,
                bound.source_kind,
                bound.source_id,
                bound.frame.model_copy(update={"stakes": "A different personal request."}),
            )
    if decision == "decline":
        with pytest.raises(WorkflowError, match="INVALID_GM_OUTCOME"):
            service.propose(
                ADMIN,
                "cannot-ignore-refusal",
                scene,
                resumed["id"],
                proposal(service, scene, resumed, "enough"),
            )
    saved = service.propose(
        ADMIN, "propose-social", scene, resumed["id"], proposal(service, scene, resumed, verdict)
    )
    with pytest.raises(WorkflowError, match="GM_OUTCOME_NOT_OWNED"):
        service.confirm(OTHER, "target-is-not-ruling-owner", scene, saved["id"])
    service.confirm(ADMIN, "native-social-confirm", scene, saved["id"])
    assert game.inspect(PLAYER, action)["state"] == "complete" and dice.calls == 1
    assert service.responses.get(OTHER, scene, identity)["answer"]["text"] == reply


def test_clarification_and_withdrawn_consent_do_not_establish_voluntary_response(routed):
    service, scene, game, dice, action, opened = pending(routed)
    requested = service.responses.request(ADMIN, "question", scene, opened["id"], "Do you agree?")
    service.responses.answer(OTHER, "clarify", scene, requested["id"], "clarify", "Agree to what?")
    resumed = service.responses.resume(ADMIN, "reopen", scene, requested["id"])
    packet = service.packet(ADMIN, scene, resumed["id"])
    assert not packet.native["response_authorized"]
    with pytest.raises(WorkflowError, match="INVALID_GM_OUTCOME"):
        service.propose(
            ADMIN,
            "no-assumption",
            scene,
            resumed["id"],
            proposal(service, scene, resumed, "enough"),
        )
    second = service.responses.request(
        ADMIN, "second-question", scene, opened["id"], "Do you agree to lower the training volume?"
    )
    observer = service.observer
    observer.set_consent(OTHER, "withdraw-response", scene, 1, consent=False)
    observer.set_consent(OTHER, "renew-response", scene, 1, consent=True)
    with pytest.raises(WorkflowError, match="STALE_TARGET_RESPONSE"):
        service.responses.answer(OTHER, "cannot-revive", scene, second["id"], "accept", "I agree.")
    assert game.inspect(PLAYER, action)["state"] != "complete" and dice.calls == 1


def test_explicit_cast_director_can_supply_their_npc_response_under_actual_native_authority(ledger):
    from test_actor_play_service import begin, pass_tags, ready
    from test_director_observation import Clock
    from test_m2_game import Gateway, answer, tick

    from girlframe.ai.observation import ObservationPolicy
    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.services.director_context import DirectorContextService
    from girlframe.services.director_observation import DirectorObservationService

    plays, game, _, actor, director = ready(ledger)
    observer = DirectorObservationService(ledger, synthetic=True)
    observer.game = game
    ledger.clock = Clock()
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "npc-observer", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, "npc-consent:" + str(viewer.user_id), scene, 1, consent=True)
    action = begin(plays, actor, context="Ask the actual Director to acknowledge the explanation.")
    tick(GameWorker(game), Gateway())
    pass_tags(game)
    answer(game, ADMIN, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    with ledger.engine.connect() as c:
        choice = next(x for x in game.pending_choices(c, OTHER) if x["kind"] == "handler_keep")
    service = GMOutcomeService(DirectorContextService(observer), require_response_scope=True)
    opened = service.open(
        ADMIN,
        "npc-frame",
        scene,
        "choice",
        choice["id"],
        TaskFrame(
            stakes="The Director acknowledges the explanation.",
            demands=(Demand(id="agreement", question="Does the Director acknowledge it?"),),
            response_scope="other",
            response_target=director,
        ),
    )
    packet = service.packet(ADMIN, scene, opened["id"])
    assert packet.native["response_authorized"] and packet.owner_id == "3"
    p = proposal(service, scene, opened, "enough")
    assessment = p.decision.assessments[0].model_copy(update={"evidence_ids": ("native", "traits")})
    p = p.model_copy(
        update={
            "decision": p.decision.model_copy(
                update={"assessments": (assessment,), "narration": "The Director acknowledges it."}
            ),
            "cited_evidence": ("source", "native"),
        }
    )
    saved = service.propose(ADMIN, "npc-proposal", scene, opened["id"], p)
    service.confirm(OTHER, "actual-director-confirm", scene, saved["id"])
    assert game.inspect(ADMIN, action)["state"] == "complete" and game.dice.calls == 1


def test_acting_pilot_clarifies_locked_keep_without_publishing_or_rerolling(routed):
    observer, context, scene, game, dice = routed
    _, _, action, _, _ = prepare(routed, "GM, I Keep Your Head to help here.", "unclear-keep")
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_keep")
    service = GMOutcomeService(context, require_response_scope=True)
    opened = service.open(
        ADMIN,
        "unclear-frame",
        scene,
        "choice",
        choice["id"],
        TaskFrame(
            stakes="Help here",
            intent="needs_clarification",
            response_scope="self",
            demands=(
                Demand(id="control", question="Can the pilot maintain the attempted control?"),
            ),
        ),
    )
    handoff = service.responses.request(
        ADMIN,
        "intent-question",
        scene,
        opened["id"],
        "What result are you attempting?",
        clarify_intent=True,
    )
    identity = handoff["id"]
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="INTENT_ANSWER_REQUIRED"):
        service.responses.resume(ADMIN, "not-yet", scene, identity)
    assert service.responses.pending(PLAYER, scene)[0]["purpose"] == "intent"
    assert not service.responses.pending(OTHER, scene)
    with pytest.raises(WorkflowError, match="RESPONSE_NOT_OWNED"):
        service.responses.answer(ADMIN, "not-actor", scene, identity, "clarify", "My guessed goal")
    text = "Hold the calibration needle on its mark."
    saved = service.responses.answer(PLAYER, "intent-answer", scene, identity, "clarify", text)
    assert (
        service.responses.answer(PLAYER, "intent-answer", scene, identity, "clarify", text) == saved
    )
    resumed = service.responses.resume(ADMIN, "resume", scene, identity)
    packet = service.packet(ADMIN, scene, resumed["id"])
    assert packet.frame.stakes == text and packet.frame.intent == "established"
    assert state(game).model_dump_json() == before and dice.calls == 1
    with pytest.raises(WorkflowError, match="INTENT_SOURCE"):
        service.open(
            ADMIN,
            "changed-intent",
            scene,
            "choice",
            choice["id"],
            packet.frame.model_copy(update={"stakes": "Force someone else to agree"}),
        )
    outcome = OutcomeProposal(
        request_id=packet.request_id,
        decision=KeepOutcome(
            verdict="enough",
            narration="The Pilot holds the needle steady.",
            assessments=(
                Assessment(
                    demand_id="control",
                    sufficient=True,
                    evidence_ids=("traits", "actor_intent"),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="Control supports the Pilot's clarified precision task.",
                ),
            ),
        ),
        cited_evidence=("source", "native", "actor_intent"),
        private_reasoning="Reviewed actual intent.",
    )
    proposal = service.propose(ADMIN, "intent-ruling", scene, resumed["id"], outcome)
    service.confirm(ADMIN, "confirm-intent", scene, proposal["id"])
    assert game.inspect(PLAYER, action)["state"] == "complete" and dice.calls == 1
    with observer.store.engine.connect() as c:
        role = context._handler_for_request(c, ADMIN, scene)
        assert text not in role.model_dump_json()
