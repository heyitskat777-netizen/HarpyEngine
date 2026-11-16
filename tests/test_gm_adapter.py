"""Native provider protocol: proof, scoped output, actual confirmation and invalid plans."""

import json

import pytest
from test_director_adjudication import prepare
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.ai.gm_protocol import (
    Assessment,
    Demand,
    GMProposal,
    Prerequisite,
    TaskFrame,
    TraitClaim,
)
from girlframe.services.gm_adapter import GMAdapterService
from girlframe.services.onboarding import WorkflowError


class ManualGM:
    calls = 0

    def propose(self, packet):
        self.calls += 1
        return GMProposal(
            request_id=packet.request_id,
            verdict="enough",
            cited_evidence=("goal", "receipt", "traits"),
            assessments=tuple(
                Assessment(
                    demand_id=d.id,
                    sufficient=True,
                    evidence_ids=("traits",),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="This is one facilitator's contextual interpretation.",
                )
                for d in packet.frame.demands
            ),
            private_reasoning="SYNTHETIC_GM_SECRET_CANARY: legitimate private reasoning, "
            "never public prose.",
        )


def ready(routed):
    v1, source, native, worker, gateway = prepare(
        routed,
        "GM, I declare Keep Your Head to keep the calibration needle steady.",
        "native-input",
    )
    gm = ManualGM()
    adapter = GMAdapterService(v1.conversation.context, gm)
    frame = adapter.frame(
        ADMIN,
        "frame",
        routed[2],
        source.source_id,
        1,
        native,
        TaskFrame(
            stakes="Keep the indicated mark through the shaking rig.",
            demands=(
                Demand(
                    id="control",
                    question="Are the chosen traits enough for deliberate control here?",
                ),
            ),
        ),
    )
    return adapter, frame, source, native, worker, gateway, gm


def test_private_provider_reasoning_is_not_public_and_actual_confirmation_replays(routed):
    observer, context, scene, game, dice = routed
    adapter, frame, source, native, worker, gateway, provider = ready(routed)
    before = state(game).model_dump_json()
    result = adapter.evaluate(ADMIN, "evaluate", scene, frame["id"])
    assert "SYNTHETIC_GM_SECRET_CANARY" in json.dumps(result)
    assert state(game).model_dump_json() == before
    assert adapter.evaluate(ADMIN, "evaluate", scene, frame["id"]) == result and provider.calls == 1
    for viewer in (PLAYER, OTHER):
        view = adapter.view(viewer, scene, result["id"])
        assert not view["can_confirm"]
        assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(view)
        with pytest.raises(WorkflowError):
            adapter.private(viewer, scene, result["id"])
    with pytest.raises(WorkflowError, match="CHOICE_NOT_OWNED"):
        adapter.confirm_keep(PLAYER, "wrong", scene, result["id"])
    committed = adapter.confirm_keep(ADMIN, "confirm", scene, result["id"])
    assert adapter.confirm_keep(ADMIN, "confirm", scene, result["id"]) == committed
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, native)["result"]["enough"] is True
    view = adapter.view(PLAYER, scene, result["id"])
    assert view["immediate_complete"] and view["fully_resolved"]
    assert view["confirmed"] and not view["can_confirm"]
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(view)
    assert dice.calls == 1


def test_immediate_completion_retains_latest_scene_work_and_its_privacy(routed):
    from girlframe.services.m3_collateral import append, latest
    from girlframe.services.m3_work import related

    adapter, frame, _, native, worker, gateway, _ = ready(routed)
    observer, _, scene, game, _ = routed
    proposal = adapter.evaluate(ADMIN, "evaluate", scene, frame["id"])
    adapter.confirm_keep(ADMIN, "confirm", scene, proposal["id"])
    tick(worker, gateway, 5)
    with observer.store.transaction() as c:
        event = game.action(c, native)["data"]["response_event"]
        related(
            c,
            observer.store,
            {"campaign_id": observer.store.campaign_id, "scene_id": scene},
            "synthetic-required-work",
            ADMIN.user_id,
            PLAYER.user_id,
            "SYNTHETIC_PRIVATE_WORK_KIND",
            {"detail": "SYNTHETIC_PRIVATE_WORK_BODY"},
            event,
        )
    view = adapter.view(PLAYER, scene, proposal["id"])
    assert view["immediate_complete"] and not view["fully_resolved"]
    assert view["followups"] == [{"your_work": False}]
    assert "SYNTHETIC_PRIVATE_WORK" not in json.dumps(view)
    with observer.store.transaction() as c:
        row = latest(game, c, "synthetic-required-work")
        append(c, row, event, {"detail": "Resolved synthetic fixture work"}, "resolved")
    assert adapter.view(PLAYER, scene, proposal["id"])["fully_resolved"]


@pytest.mark.parametrize("defect", ["binding", "evidence", "trait", "omitted_demand", "effects"])
def test_invalid_provider_cannot_create_an_authorised_proposal(routed, defect):
    adapter, frame, source, native, worker, gateway, _ = ready(routed)
    scene = routed[2]

    class Invalid(ManualGM):
        def propose(self, packet):
            valid = super().propose(packet)
            if defect == "binding":
                return valid.model_copy(update={"request_id": "some-other-source"})
            if defect == "evidence":
                return valid.model_copy(update={"cited_evidence": ("goal", "receipt", "invented")})
            if defect == "omitted_demand":
                return valid.model_copy(update={"assessments": ()})
            if defect == "effects":
                return valid.model_copy(update={"effects": ({"open_door": True},)})
            return valid.model_copy(
                update={
                    "assessments": (
                        valid.assessments[0].model_copy(
                            update={"traits": (TraitClaim(trait="in_control", polarity="are_not"),)}
                        ),
                    )
                }
            )

    adapter.provider = Invalid()
    before = state(routed[3]).model_dump_json()
    with pytest.raises(WorkflowError, match="INVALID_GM_PROPOSAL"):
        adapter.evaluate(ADMIN, "invalid", scene, frame["id"])
    assert state(routed[3]).model_dump_json() == before and routed[-1].calls == 1


def test_freshness_is_checked_inside_native_confirmation_transaction(routed, monkeypatch):
    adapter, frame, source, native, worker, gateway, _ = ready(routed)
    scene, game = routed[2], routed[3]
    result = adapter.evaluate(ADMIN, "evaluate", scene, frame["id"])
    original = adapter.observer.game.respond

    def changed(*args, **kwargs):
        with game.store.transaction() as c:
            canon = state(game)
            canon.facts.append(
                {"kind": "scene_condition", "body": "Newly established prerequisite."}
            )
            game.event(c, ADMIN.user_id, "changed", "synthetic.changed", canon)
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter.observer.game, "respond", changed)
    with pytest.raises(WorkflowError, match="STALE_GM_CONFIRMATION"):
        adapter.confirm_keep(ADMIN, "stale", scene, result["id"])
    assert game.inspect(PLAYER, native)["state"] != "complete" and routed[-1].calls == 1


def test_constraints_cannot_be_ignored_and_clarification_does_not_apply_a_ruling(routed):
    adapter, _, source, native, worker, gateway, _ = ready(routed)
    scene, game = routed[2], routed[3]
    with game.store.transaction() as c:
        canon = state(game)
        canon.facts.append({"kind": "scene_condition", "body": "Actual fixture access is blocked."})
        game.event(c, ADMIN.user_id, "condition", "synthetic.condition", canon)
    packet = adapter.evidence(ADMIN, scene, source.source_id, 1, native)
    condition = next(x for x in packet.evidence if x.id.startswith("condition:"))

    class CitingGM(ManualGM):
        def propose(self, packet):
            proposal = super().propose(packet)
            return proposal.model_copy(
                update={"cited_evidence": (*proposal.cited_evidence, condition.id)}
            )

    adapter.provider = CitingGM()
    for status in ("unknown", "blocked"):
        framed = adapter.frame(
            ADMIN,
            "constraint:" + status,
            scene,
            source.source_id,
            1,
            native,
            TaskFrame(
                stakes="Use the actual access prerequisite.",
                demands=(Demand(id="control", question="Assess precision."),),
                prerequisites=(
                    Prerequisite(
                        evidence_id=condition.id,
                        state=status,
                        interpretation="Explicit facilitator interpretation.",
                    ),
                ),
            ),
        )
        with pytest.raises(WorkflowError, match="INVALID_GM_PROPOSAL"):
            adapter.evaluate(ADMIN, "bad:" + status, scene, framed["id"])
    from girlframe.ai.gm_protocol import OfflineReviewProvider

    adapter.provider = OfflineReviewProvider()
    result = adapter.evaluate(ADMIN, "review", scene, framed["id"])
    assert result["proposal"]["verdict"] == "needs_clarification"
    with pytest.raises(WorkflowError, match="NO_GM_CONFIRMATION"):
        adapter.confirm_keep(ADMIN, "not-a-ruling", scene, result["id"])
    assert not adapter.view(PLAYER, scene, result["id"])["immediate_complete"]


def test_confirmation_respects_withdrawn_scene_consent(routed):
    adapter, framed, source, native, worker, gateway, _ = ready(routed)
    scene = routed[2]
    result = adapter.evaluate(ADMIN, "evaluate", scene, framed["id"])
    routed[0].set_consent(OTHER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        adapter.confirm_keep(ADMIN, "withdrawn", scene, result["id"])
    assert routed[-1].calls == 1 and routed[3].inspect(PLAYER, native)["state"] != "complete"


def test_source_binding_and_context_change_during_generation_fail_closed(routed):
    adapter, framed, source, native, _, _, _ = ready(routed)
    scene, game = routed[2], routed[3]
    task = TaskFrame(stakes="Retain the original declaration.")
    with pytest.raises(WorkflowError):
        adapter.frame(PLAYER, "not-gm", scene, source.source_id, 1, native, task)
    with pytest.raises(WorkflowError, match="STALE_SOURCE"):
        adapter.frame(ADMIN, "wrong-revision", scene, source.source_id, 2, native, task)

    class ChangedContextGM(ManualGM):
        def propose(self, packet):
            proposal = super().propose(packet)
            with game.store.transaction() as c:
                canon = state(game)
                canon.facts.append({"kind": "gm_only", "body": "New synthetic context."})
                game.event(c, ADMIN.user_id, "generation-change", "synthetic.changed", canon)
            return proposal

    adapter.provider = ChangedContextGM()
    with pytest.raises(WorkflowError, match="STALE_GM_FRAME"):
        adapter.evaluate(ADMIN, "changed-generation", scene, framed["id"])
    assert game.inspect(PLAYER, native)["state"] != "complete" and routed[-1].calls == 1
