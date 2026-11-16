"""Synthetic knowledge → shadow → durable outcome, without canonical application."""

import pytest
import sqlalchemy as sa
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger

from girlframe.ai.director import DirectorDecision
from girlframe.database import tables as t
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_shadow import DirectorShadowService
from girlframe.services.onboarding import WorkflowError


def prepared(observed):
    observer, scene, clock, *_ = observed
    _, source = send(observer, scene, "source", text="SYNTHETIC_GM_REFERENCE")
    with observer.store.engine.connect() as c:
        _, _, pilot = observer._authorize_input(c, PLAYER, scene, "pilot")
        _, _, handler = observer._authorize_input(c, ADMIN, scene, "handler")
    context = DirectorContextService(observer)
    fact = context.record(ADMIN, "reference", scene, source.source_id, 0, known_by=(pilot,))
    clock.now += 120
    batch = observer.claim_review(scene)
    return observer, context, scene, source, fact, pilot, handler, batch


def test_isolated_knowledge_order_and_durable_wait(observed):
    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)
    assert len(context.build(ADMIN, scene).references) == 1
    assert len(context.build(PLAYER, scene, actor=pilot).references) == 1
    assert not context.build(ADMIN, scene, actor=handler).references
    assert (
        "SYNTHETIC_GM_REFERENCE" not in context.build(ADMIN, scene, actor=handler).model_dump_json()
    )
    with pytest.raises(WorkflowError):
        context.build(OTHER, scene, actor=pilot)
    with pytest.raises(WorkflowError):
        context.build(PLAYER, scene)
    shadow = DirectorShadowService(context)
    result = shadow.evaluate(ADMIN, scene, batch.run_id)
    assert result["status"] == "wait" and result["application"] == "blocked"
    observer.store.engine.dispose()
    assert DirectorShadowService(context).get(ADMIN, scene, batch.run_id) == result
    assert shadow.evaluate(ADMIN, scene, batch.run_id) == result
    assert observer.status(PLAYER, scene).pending_messages == 0


def test_dependency_and_source_revision_reject_stale_context(observed):
    observer, context, scene, source, _, _, _, _ = prepared(observed)
    _, second = send(observer, scene, "second")
    with pytest.raises(WorkflowError, match="INVALID_CHRONOLOGY"):
        context.record(ADMIN, "bad-order", scene, second.source_id, 1, dependencies=("unknown",))
    with pytest.raises(WorkflowError, match="STALE_CHRONOLOGY"):
        context.record(ADMIN, "stale-order", scene, second.source_id, 0)
    send(
        observer,
        scene,
        "edit",
        text="SYNTHETIC_CORRECTION",
        source_id=source.source_id,
        expected_source_revision=1,
    )
    with pytest.raises(WorkflowError, match="STALE_KNOWLEDGE"):
        context.build(ADMIN, scene)


@pytest.mark.parametrize(
    "kind", ["WAIT", "REQUEST_PLAY", "NPC_DIALOGUE", "WORLD_EVENT_PROPOSAL", "NEEDS_REVIEW"]
)
def test_five_decision_kinds_are_review_only_with_no_effects(observed, kind):
    observer, context, scene, _, fact, _, _, batch = prepared(observed)

    class Fake:
        def decide(self, supplied):
            return DirectorDecision(
                kind=kind,
                reason_code="explicit_request",
                source_refs=(fact["id"],),
                brief="SYNTHETIC_PROPOSAL",
            )

    outcome = DirectorShadowService(context, Fake()).evaluate(ADMIN, scene, batch.run_id)
    assert outcome["status"] == ("wait" if kind == "WAIT" else "needs_review")
    assert outcome["publication"] == outcome["application"] == "blocked"
    with observer.store.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.director_context["shadow"])) == 1


def test_invalid_output_retries_once_and_failure_leaves_input_pending(observed):
    observer, context, scene, _, _, _, _, batch = prepared(observed)

    class Invalid:
        calls = 0

        def decide(self, supplied):
            self.calls += 1
            return DirectorDecision(
                kind="WORLD_EVENT_PROPOSAL",
                reason_code="explicit_request",
                source_refs=("unknown-secret",),
            )

    provider = Invalid()
    service = DirectorShadowService(context, provider)
    outcome = service.evaluate(ADMIN, scene, batch.run_id)
    assert outcome["failure"] == "INVALID_DECISION" and provider.calls == 2
    assert observer.status(PLAYER, scene).pending_messages == 1
    assert service.evaluate(ADMIN, scene, batch.run_id) == outcome and provider.calls == 2


def test_provider_runs_outside_transaction_and_stale_result_cannot_consume(observed):
    observer, context, scene, _, _, _, _, batch = prepared(observed)

    class Concurrent:
        def decide(self, supplied):
            send(observer, scene, "concurrent-input")
            return DirectorDecision(kind="WAIT", reason_code="no_grounded_need")

    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        DirectorShadowService(context, Concurrent()).evaluate(ADMIN, scene, batch.run_id)
    assert observer.status(PLAYER, scene).pending_messages == 2
    with observer.store.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.director_context["shadow"])) == 0


def test_explicit_disclosure_and_corrected_source_are_reconciled(observed):
    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)
    context.record(
        ADMIN,
        "disclose",
        scene,
        source.source_id,
        1,
        known_by=(handler,),
        dependencies=(fact["id"],),
    )
    assert len(context.build(ADMIN, scene, actor=handler).references) == 1
    assert len(context.build(PLAYER, scene, actor=pilot).references) == 1
    send(
        observer,
        scene,
        "correction",
        text="SYNTHETIC_CORRECTION",
        source_id=source.source_id,
        expected_source_revision=1,
    )
    context.record(ADMIN, "reconcile", scene, source.source_id, 2, known_by=(pilot,))
    assert not context.build(ADMIN, scene, actor=handler).references
    assert context.build(PLAYER, scene, actor=pilot).references[0].source_revision == 2


def test_private_review_is_durable_retry_safe_and_never_applies(observed):
    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)

    class Proposal:
        def decide(self, supplied):
            return DirectorDecision(
                kind="WORLD_EVENT_PROPOSAL",
                reason_code="explicit_request",
                source_refs=(fact["id"],),
                brief="SYNTHETIC_DRAFT",
            )

    service = DirectorShadowService(context, Proposal())
    service.evaluate(ADMIN, scene, batch.run_id)
    with pytest.raises(WorkflowError):
        service.review(PLAYER, "foreign-review", scene, batch.run_id, decision="approve")
    result = service.review(ADMIN, "review", scene, batch.run_id, decision="approve")
    assert service.review(ADMIN, "review", scene, batch.run_id, decision="approve") == result
    assert result["application"] == result["publication"] == "blocked"
    assert service.get(ADMIN, scene, batch.run_id + ":review") == result
    with pytest.raises(WorkflowError, match="REVIEW_FINAL"):
        service.review(ADMIN, "change-review", scene, batch.run_id, decision="reject")


def test_shadow_outcome_insert_failure_rolls_back_frontier(observed):
    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)

    def fail(connection, cursor, statement, parameters, sql_context, many):
        if statement.startswith("INSERT INTO director_shadow"):
            raise RuntimeError("SYNTHETIC_STORAGE_FAILURE")

    sa.event.listen(observer.store.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="SYNTHETIC_STORAGE_FAILURE"):
            DirectorShadowService(context).evaluate(ADMIN, scene, batch.run_id)
    finally:
        sa.event.remove(observer.store.engine, "before_cursor_execute", fail)
    assert observer.status(PLAYER, scene).pending_messages == 1
    outcome = DirectorShadowService(context).evaluate(ADMIN, scene, batch.run_id)
    send(
        observer,
        scene,
        "correction-after-review",
        text="SYNTHETIC_LATER_CORRECTION",
        source_id=source.source_id,
        expected_source_revision=1,
    )
    assert DirectorShadowService(context).get(ADMIN, scene, batch.run_id) == outcome
    assert DirectorShadowService(context).evaluate(ADMIN, scene, batch.run_id) == outcome


def test_bounded_repair_can_recover_without_duplicate_outcome(observed):
    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)

    class Repair:
        calls = 0

        def decide(self, supplied):
            self.calls += 1
            if self.calls == 1:
                return DirectorDecision(
                    kind="WAIT", reason_code="no_grounded_need", source_refs=("unknown",)
                )
            return DirectorDecision(kind="WAIT", reason_code="no_grounded_need")

    provider = Repair()
    assert (
        DirectorShadowService(context, provider).evaluate(ADMIN, scene, batch.run_id)["status"]
        == "wait"
    )
    assert provider.calls == 2


def test_provider_outage_preserves_unread_input_and_sanitizes_errors(observed):
    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)

    class Outage:
        def decide(self, supplied):
            raise RuntimeError("SYNTHETIC_PRIVATE_PROVIDER_ERROR")

    service = DirectorShadowService(context, Outage())
    outcome = service.evaluate(ADMIN, scene, batch.run_id)
    assert outcome["failure"] == "PROVIDER_UNAVAILABLE"
    assert observer.status(PLAYER, scene).pending_messages == 1
    assert "SYNTHETIC_PRIVATE_PROVIDER_ERROR" not in str(service.get(ADMIN, scene, batch.run_id))


def test_handler_dialogue_uses_only_explicit_knowledge_and_never_portrays_pilot(observed):
    from girlframe.services.director_dialogue import DirectorDialogueService

    observer, context, scene, source, fact, pilot, handler, batch = prepared(observed)
    context.record(ADMIN, "handler-disclosure", scene, source.source_id, 1, known_by=(handler,))
    own = context.build(ADMIN, scene, actor=handler)
    dialogue = DirectorDialogueService(context)
    with pytest.raises(WorkflowError, match="PLAYER_AGENCY"):
        dialogue.draft(PLAYER, "forge-pilot", scene, pilot, own.revision, (own.references[0].id,))
    with pytest.raises(WorkflowError, match="UNKNOWN_KNOWLEDGE"):
        dialogue.draft(ADMIN, "unknown", scene, handler, own.revision, ("unknown",))
    draft = dialogue.draft(
        ADMIN, "handler-draft", scene, handler, own.revision, tuple(x.id for x in own.references)
    )
    assert "SYNTHETIC_GM_REFERENCE" in dialogue.get(ADMIN, scene, draft["id"])["text"]
    assert (
        dialogue.review(ADMIN, "reject-handler-draft", scene, draft["id"], decision="reject")[
            "publication"
        ]
        == "blocked"
    )
