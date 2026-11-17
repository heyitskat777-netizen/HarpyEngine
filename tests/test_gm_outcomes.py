"""Actual semantic consumers: typed proposals, original owners, no fabricated responses."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_director_adjudication import prepare
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.ai.gm_outcomes import OutcomeNarration, OutcomeProposal, SensorAnswers
from girlframe.database import tables as t
from girlframe.services.gm_outcomes import GMOutcomeService
from girlframe.services.onboarding import WorkflowError


def sensors(routed):
    _, context, scene, game, _ = routed
    _, _, native, worker, gateway = prepare(
        routed,
        "GM, I declare Check Sensors to inspect the hangar.",
        "sensors",
        play="check_sensors",
    )
    svc = GMOutcomeService(context)
    choice = next(x for x in game.choices(ADMIN) if x["kind"] == "handler_sensors")
    request = svc.open(ADMIN, "open", scene, "choice", choice["id"])
    packet = svc.packet(ADMIN, scene, request["id"])
    proposal = OutcomeProposal(
        request_id=packet.request_id,
        decision=SensorAnswers(
            answers={
                "a1": "The observed relay cabinet is intact.",
                "a2": "The visible exit is clear.",
            }
        ),
        cited_evidence=("source", "native"),
        private_reasoning="SYNTHETIC_GM_PRIVATE_REASON",
    )
    return svc, request, proposal, native, worker, gateway


def test_sensor_answers_commit_once_under_actual_owner_and_do_not_copy_private_reason(routed):
    svc, request, proposal, native, worker, gateway = sensors(routed)
    scene, game, dice = routed[2:]
    before = state(game).model_dump_json()
    saved = svc.propose(ADMIN, "propose", scene, request["id"], proposal)
    assert svc.propose(ADMIN, "propose", scene, request["id"], proposal) == saved
    assert state(game).model_dump_json() == before
    with pytest.raises(WorkflowError, match="NOT_OWNED"):
        svc.confirm(PLAYER, "wrong", scene, saved["id"])
    assert "SYNTHETIC_GM_PRIVATE_REASON" not in json.dumps(
        svc.owner_review(ADMIN, scene, saved["id"])
    )
    committed = svc.confirm(ADMIN, "accept", scene, saved["id"])
    assert svc.confirm(ADMIN, "accept", scene, saved["id"]) == committed
    tick(worker, gateway, 5)
    view = game.inspect(PLAYER, native)
    assert view["state"] == "complete" and dice.calls == 1
    assert "SYNTHETIC_GM_PRIVATE_REASON" not in json.dumps(view)
    assert "observed relay" in json.dumps(view)
    # Completion narration describes committed results and applies no extra effects.
    request = svc.open(ADMIN, "narrate-open", scene, "completed", native)
    packet = svc.packet(ADMIN, scene, request["id"])
    saved = svc.propose(
        ADMIN,
        "narrate-propose",
        scene,
        request["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=OutcomeNarration(
                text="The scan resolves the two chosen questions.", effect_refs=("questions",)
            ),
            cited_evidence=("source", "native"),
            private_reasoning="PRIVATE_NARRATION_REASON",
        ),
    )
    before = state(game).model_dump_json()
    contribution = svc.confirm(ADMIN, "narrate-confirm", scene, saved["id"])
    assert not contribution["canon_effects"]
    assert "PRIVATE_NARRATION_REASON" not in json.dumps(
        svc.contribution(PLAYER, scene, contribution["id"])
    )
    assert state(game).model_dump_json() == before and dice.calls == 1


def test_missing_answers_and_request_substitution_do_not_apply_native_effects(routed):
    svc, request, proposal, native, _, _ = sensors(routed)
    before = state(routed[3]).model_dump_json()
    for bad in (
        proposal.model_copy(update={"request_id": "wrong"}),
        proposal.model_copy(update={"decision": SensorAnswers(answers={"a1": "Incomplete"})}),
        proposal.model_copy(update={"cited_evidence": ("source", "invented")}),
    ):
        with pytest.raises(WorkflowError, match="INVALID_GM_OUTCOME"):
            svc.propose(ADMIN, str(uuid4()), routed[2], request["id"], bad)
    assert state(routed[3]).model_dump_json() == before


def test_native_guard_is_checked_inside_transaction_and_contextvar_resets(routed, monkeypatch):
    svc, request, proposal, native, _, _ = sensors(routed)
    scene, game = routed[2:4]
    saved = svc.propose(ADMIN, "propose", scene, request["id"], proposal)
    original = svc.game.respond

    def changed(*args, **kwargs):
        with game.store.transaction() as c:
            canon = state(game)
            canon.facts.append({"kind": "gm_only", "body": "Actual changed source context"})
            game.event(c, 1, "changed", "synthetic.changed", canon)
        return original(*args, **kwargs)

    monkeypatch.setattr(svc.game, "respond", changed)
    with pytest.raises(WorkflowError, match="STALE_GM_OUTCOME"):
        svc.confirm(ADMIN, "accept", scene, saved["id"])
    assert game.inspect(PLAYER, native)["state"] != "complete"
    # A rejected guarded write must not poison a later unrelated command.
    assert game.store._write(
        ADMIN, "unrelated", "synthetic.guard_reset", {}, lambda c: {"reset": True}
    ) == {"reset": True}
    with game.store.engine.connect() as c:
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.commands)
                .where(t.commands.c.interaction_key.like("gm-outcome:%"))
            )
            == 0
        )


def test_sensor_packet_and_private_feedback_expose_exact_consumer_field_mapping(routed):
    svc, request, proposal, native, _, _ = sensors(routed)
    scene, game, dice = routed[2:]
    packet = svc.packet(ADMIN, scene, request["id"])
    assert packet.native["answer_contract"] == {
        "answers": {
            "a1": "Where does the Foundation want us to go?",
            "a2": "What does the Foundation want us to avoid?",
        },
        "consequence_required": False,
        "allowed_consequences": [],
    }
    texts = list(proposal.decision.answers.values())
    wrong = proposal.model_copy(
        update={
            "decision": SensorAnswers(
                answers={"foundation_destination": texts[0], "foundation_avoid": texts[1]},
                consequence="incomplete_information",
            )
        }
    )
    before = state(game).model_dump_json()
    feedback = svc.feedback(ADMIN, scene, request["id"], wrong.model_dump(mode="json"))
    assert not feedback["valid"]
    assert feedback["errors"][0]["code"] == "SENSOR_INPUT_CONTRACT"
    assert "a1, a2" in feedback["errors"][0]["message"]
    assert "consequence=null" in feedback["errors"][0]["message"]
    assert "SYNTHETIC_GM_PRIVATE_REASON" not in json.dumps(feedback)
    with pytest.raises(WorkflowError):
        svc.feedback(PLAYER, scene, request["id"], wrong.model_dump(mode="json"))
    assert svc.feedback(ADMIN, scene, request["id"], proposal.model_dump(mode="json"))["valid"]
    assert state(game).model_dump_json() == before and dice.calls == 1
    assert game.inspect(PLAYER, native)["state"] != "complete"
