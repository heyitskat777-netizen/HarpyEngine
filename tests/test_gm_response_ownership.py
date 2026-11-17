"""Reviewed providers must establish response authority before native commitment."""

import jsonschema
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


def setup(routed, scope=None, target=None):
    observer, context, scene, game, _ = routed
    _, _, action, _, _ = prepare(routed, "Keep the calibration needle steady.", "prepare")
    service = GMOutcomeService(context, require_response_scope=True)
    with observer.store.engine.connect() as c:
        choice = next(x for x in game.pending_choices(c, ADMIN) if x["kind"] == "handler_keep")
    opened = service.open(
        ADMIN,
        "open",
        scene,
        "choice",
        choice["id"],
        TaskFrame(
            stakes="Keep the needle steady.",
            demands=(Demand(id="steady", question="Can the Pilot maintain control?"),),
            response_scope=scope,
            response_target=target,
        ),
    )
    proposal = OutcomeProposal(
        request_id=service.packet(ADMIN, scene, opened["id"]).request_id,
        decision=KeepOutcome(
            verdict="enough",
            narration="The needle remains steady.",
            assessments=(
                Assessment(
                    demand_id="steady",
                    sufficient=True,
                    evidence_ids=("source", "native", "traits"),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="Control supports precision.",
                ),
            ),
        ),
        cited_evidence=("source", "native"),
        private_reasoning="PRIVATE_OWNERSHIP_REVIEW",
    )
    return service, scene, game, action, opened, proposal


def test_unspecified_response_scope_needs_clarification_and_feedback_is_private(routed):
    service, scene, game, action, opened, proposal = setup(routed)
    feedback = service.feedback(ADMIN, scene, opened["id"], proposal.model_dump(mode="json"))
    assert not feedback["valid"] and feedback["errors"][0]["code"] == "RESPONSE_OWNERSHIP"
    assert "PRIVATE_OWNERSHIP_REVIEW" not in str(feedback)
    with pytest.raises(WorkflowError):
        service.feedback(PLAYER, scene, opened["id"], proposal.model_dump(mode="json"))
    with pytest.raises(WorkflowError, match="INVALID_GM_OUTCOME"):
        service.propose(ADMIN, "reject", scene, opened["id"], proposal)
    assert game.inspect(PLAYER, action)["state"] != "complete"
    clarification = proposal.model_copy(
        update={
            "decision": KeepOutcome(
                verdict="needs_clarification", narration="Whose response determines the outcome?"
            )
        }
    )
    assert service.feedback(ADMIN, scene, opened["id"], clarification.model_dump(mode="json"))[
        "valid"
    ]


def test_other_pilots_reaction_cannot_be_supplied_by_gm(routed):
    observer, _, scene, _, _ = routed
    with observer.store.engine.connect() as c:
        target = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    service, scene, game, action, opened, proposal = setup(routed, "other", target)
    packet = service.packet(ADMIN, scene, opened["id"])
    assert packet.native["response_controller"] == "3" and not packet.native["response_authorized"]
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="INVALID_GM_OUTCOME"):
        service.propose(ADMIN, "not-the-target-owner", scene, opened["id"], proposal)
    assert (
        state(game).model_dump_json() == before
        and game.inspect(PLAYER, action)["state"] != "complete"
    )


def test_self_scope_retains_native_confirmation_and_schema_explains_required_citations(routed):
    service, scene, game, action, opened, proposal = setup(routed, "self")
    assert service.feedback(ADMIN, scene, opened["id"], proposal.model_dump(mode="json"))["valid"]
    raw = proposal.model_dump(mode="json")
    raw["cited_evidence"] = ["native", "traits"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, OutcomeProposal.model_json_schema())
    feedback = service.feedback(ADMIN, scene, opened["id"], raw)
    assert feedback["errors"][0]["code"] == "MISSING_CITATION"
    saved = service.propose(ADMIN, "valid", scene, opened["id"], proposal)
    service.confirm(ADMIN, "confirm", scene, saved["id"])
    assert game.inspect(PLAYER, action)["state"] == "complete"
