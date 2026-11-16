"""One bounded synthetic assistance workflow, with affected integrity boundaries."""

from dataclasses import replace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_ledger import ADMIN, OTHER, PLAYER, seed
from test_ledger import ledger as ledger

from girlframe.ai.activity import GenerateDraft, RequestAssistance, ReviewDraft
from girlframe.ai.contracts import DraftProposal, GenerationResponse
from girlframe.ai.synthetic import SyntheticProvider
from girlframe.database import tables as t
from girlframe.engine.drafts import DraftInput
from girlframe.services.ai_assistance import AssistanceService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError


class CountingProvider(SyntheticProvider):
    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return super().generate(request)


def counts(store):
    with store.engine.connect() as c:
        return {
            name: c.scalar(sa.select(sa.func.count()).select_from(table))
            for name, table in t.metadata.tables.items()
        }


def request(service, key="request", audience="player", viewer=PLAYER):
    context = service.context(viewer, audience)
    command = RequestAssistance(
        command_key=key,
        expected_campaign_revision=context.context.campaign_revision,
        audience=audience,
        context_digest=context.context_digest,
    )
    return command, service.request(viewer, command)


def generate_command(receipt, key="generate"):
    return GenerateDraft(
        command_key=key,
        expected_campaign_revision=receipt.campaign_revision,
        expected_proposal_revision=receipt.proposal_revision,
    )


def review_command(receipt, decision="approve", key="review"):
    return ReviewDraft(
        command_key=key,
        expected_campaign_revision=receipt.campaign_revision,
        expected_proposal_revision=receipt.proposal_revision,
        decision=decision,
    )


@pytest.mark.parametrize("decision,status", [("approve", "approved"), ("reject", "rejected")])
def test_request_generate_private_review_reopen_and_retry_without_game_effects(
    ledger, decision, status
):
    seed(ledger)
    provider = CountingProvider()
    service = AssistanceService(ledger, provider)
    before = counts(ledger)
    command, requested = request(service)
    assert requested.status == "requested" and requested.proposal_revision == 1
    assert service.request(PLAYER, command) == requested
    draft_command = generate_command(requested)
    draft = service.generate(PLAYER, requested.proposal_id, draft_command)
    assert draft.status == "draft" and draft.proposal_revision == 2
    assert service.generate(PLAYER, requested.proposal_id, draft_command) == draft
    assert provider.calls == 1
    review = review_command(draft, decision)
    outcome = service.review(PLAYER, requested.proposal_id, review)
    assert service.review(PLAYER, requested.proposal_id, review) == outcome
    assert outcome.status == status and outcome.proposal_revision == 3
    # New service/connection retrieves the durable human outcome; no form memory.
    ledger.engine.dispose()
    reopened = AssistanceService(ledger).get(PLAYER, requested.proposal_id)
    assert reopened.record.status == status and reopened.sources_current
    assert reopened.application == "blocked"
    assert reopened.record.response.proposal.application == "record_review_only"
    assert "SYNTH_A" in reopened.record.response.proposal.text
    assert "PRIVATE_CANARY" not in reopened.model_dump_json()
    after = counts(ledger)
    for name in before:
        if name not in {t.events.name, t.commands.name, t.ai_proposals.name}:
            assert after[name] == before[name], name
    assert after[t.ai_proposals.name] == before[t.ai_proposals.name] + 3
    assert after[t.events.name] == before[t.events.name] + 3
    assert after[t.commands.name] == before[t.commands.name] + 3
    with ledger.engine.connect() as c:
        audits = "\n".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert "OOC public reference summary" not in audits
        assert "PRIVATE_CANARY" not in audits
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        service.review(
            PLAYER,
            requested.proposal_id,
            review.model_copy(
                update={"decision": "reject" if decision == "approve" else "approve"}
            ),
        )


def test_current_permissions_owner_binding_and_revocation_apply_to_retries(ledger):
    seed(ledger)
    ledger.join(OTHER, "other-join")
    ledger.join(ADMIN, "admin-join")
    service = AssistanceService(ledger)
    with pytest.raises(WorkflowError, match="administrator"):
        service.context(PLAYER, "gm")
    with pytest.raises(WorkflowError, match="appointed"):
        service.context(PLAYER, "handler")
    handlers = HandlerService(ledger)
    handlers.appoint(ADMIN, "appoint", 0, PLAYER.user_id)
    player_context = service.context(PLAYER, "player")
    handler_context = service.context(PLAYER, "handler")
    assert player_context.context.audience != handler_context.context.audience
    assert {x.field for x in handler_context.context.facts} == {"callsign"}
    assert len(service.context(ADMIN, "gm").context.facts) > len(handler_context.context.facts)
    command, receipt = request(service)
    before = counts(ledger)
    for viewer in (OTHER, ADMIN, replace(PLAYER, guild_id=201)):
        with pytest.raises(WorkflowError):
            service.get(viewer, receipt.proposal_id)
        with pytest.raises(WorkflowError):
            service.generate(viewer, receipt.proposal_id, generate_command(receipt))
    assert counts(ledger) == before
    with ledger.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(PLAYER.user_id),
            )
            .values(active=False)
        )
    with pytest.raises(WorkflowError, match="Join"):
        service.request(PLAYER, command)


def test_stale_campaign_proposal_and_sources_preserve_draft_and_allow_rejection(ledger):
    seed(ledger)
    service = AssistanceService(ledger)
    _, receipt = request(service)
    command = generate_command(receipt)
    before = counts(ledger)
    with pytest.raises(WorkflowError, match="STALE_CAMPAIGN"):
        service.generate(
            PLAYER,
            receipt.proposal_id,
            command.model_copy(update={"expected_campaign_revision": 0}),
        )
    with pytest.raises(WorkflowError, match="STALE_PROPOSAL"):
        service.generate(
            PLAYER,
            receipt.proposal_id,
            command.model_copy(update={"expected_proposal_revision": 7}),
        )
    assert counts(ledger) == before
    draft = service.generate(PLAYER, receipt.proposal_id, command)
    ledger.save_draft(
        PLAYER,
        "new-profile",
        1,
        DraftInput(callsign="NEWER_SYNTH", girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B"),
    )
    view = service.get(PLAYER, receipt.proposal_id)
    assert not view.sources_current
    review = review_command(draft).model_copy(
        update={"expected_campaign_revision": view.campaign_revision}
    )
    before = counts(ledger)
    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        service.review(PLAYER, receipt.proposal_id, review)
    assert counts(ledger) == before
    rejected = service.review(
        PLAYER, receipt.proposal_id, review.model_copy(update={"decision": "reject"})
    )
    assert rejected.status == "rejected"


@pytest.mark.parametrize("failure", ["PROVIDER_UNAVAILABLE", "INVALID_RESPONSE"])
def test_outage_and_ungrounded_output_record_safe_terminal_failure(ledger, failure):
    seed(ledger)

    class FailingProvider:
        calls = 0

        def generate(self, request):
            self.calls += 1
            if failure == "PROVIDER_UNAVAILABLE":
                raise RuntimeError("SYNTHETIC_PRIVATE_PROVIDER_ERROR")
            return GenerationResponse(proposal=DraftProposal(text="The player agrees."))

    provider = FailingProvider()
    service = AssistanceService(ledger, provider)
    _, receipt = request(service)
    command = generate_command(receipt)
    result = service.generate(PLAYER, receipt.proposal_id, command)
    assert service.generate(PLAYER, receipt.proposal_id, command) == result
    assert provider.calls == 1 and result.status == "failed"
    view = service.get(PLAYER, receipt.proposal_id)
    assert view.record.failure == failure and view.record.response is None
    assert "SYNTHETIC_PRIVATE_PROVIDER_ERROR" not in view.model_dump_json()
    with pytest.raises(WorkflowError, match="only a draft"):
        service.review(PLAYER, receipt.proposal_id, review_command(result))
    # Manual operation and an explicit fresh request remain available.
    _, fresh = request(service, key="fresh-request")
    assert fresh.proposal_id != result.proposal_id


def test_failure_after_staging_rolls_back_and_same_command_can_resume(ledger, monkeypatch):
    seed(ledger)
    service = AssistanceService(ledger)
    context = service.context(PLAYER)
    command = RequestAssistance(
        command_key="atomic-request",
        expected_campaign_revision=context.context.campaign_revision,
        audience="player",
        context_digest=context.context_digest,
    )
    before = counts(ledger)
    original = service._append

    def fail(*args):
        original(*args)
        raise RuntimeError("SYNTHETIC_AFTER_STAGING")

    monkeypatch.setattr(service, "_append", fail)
    with pytest.raises(RuntimeError, match="SYNTHETIC_AFTER_STAGING"):
        service.request(PLAYER, command)
    assert counts(ledger) == before
    assert service.context(PLAYER) == context
    monkeypatch.setattr(service, "_append", original)
    result = service.request(PLAYER, command)
    assert result.proposal_revision == 1
    with ledger.engine.begin() as c:
        with pytest.raises(IntegrityError, match="immutable"):
            c.execute(t.ai_proposals.update().values(status="approved"))
    with ledger.engine.begin() as c:
        with pytest.raises(IntegrityError, match="immutable"):
            c.execute(t.ai_proposals.delete())


def test_pause_blocks_new_generation_approval_but_preserves_review_and_rejection(ledger):
    seed(ledger)
    service = AssistanceService(ledger)
    _, first = request(service)
    draft = service.generate(PLAYER, first.proposal_id, generate_command(first))
    _, second = request(service, key="second-request")
    ledger.safety(PLAYER, "pause", second.campaign_revision, pause=True)
    context = service.context(PLAYER)
    before = counts(ledger)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        request(service, key="paused-request")
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.generate(
            PLAYER,
            second.proposal_id,
            generate_command(second, key="second-generate").model_copy(
                update={"expected_campaign_revision": context.context.campaign_revision}
            ),
        )
    review = review_command(draft).model_copy(
        update={"expected_campaign_revision": context.context.campaign_revision}
    )
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.review(PLAYER, first.proposal_id, review)
    assert counts(ledger) == before
    assert service.get(PLAYER, first.proposal_id).record.status == "draft"
    assert (
        service.review(
            PLAYER, first.proposal_id, review.model_copy(update={"decision": "reject"})
        ).status
        == "rejected"
    )


def test_wire_contracts_reject_browser_authority_and_numeric_discord_ids():
    with pytest.raises(ValidationError):
        RequestAssistance(
            command_key="bad",
            expected_campaign_revision=0,
            audience="player",
            context_digest="a" * 64,
            is_administrator=True,
        )
    from girlframe.ai.contracts import AssistanceContext

    with pytest.raises(ValidationError):
        AssistanceContext(
            campaign_id="synthetic", requester_id=2, audience="player", campaign_revision=0
        )


def test_campaign_isolation_context_digest_and_handler_replacement(ledger):
    seed(ledger)
    ledger.join(ADMIN, "admin-join")
    ledger.join(OTHER, "other-join")
    handlers = HandlerService(ledger)
    handlers.appoint(ADMIN, "appoint", 0, PLAYER.user_id)
    service = AssistanceService(ledger)
    context = service.context(PLAYER, "handler")
    bad = RequestAssistance(
        command_key="bad-digest",
        expected_campaign_revision=context.context.campaign_revision,
        audience="handler",
        context_digest="0" * 64,
    )
    before = counts(ledger)
    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        service.request(PLAYER, bad)
    assert counts(ledger) == before
    command, outcome = request(service, audience="handler")
    handlers.appoint(ADMIN, "replace-handler", 1, OTHER.user_id)
    with pytest.raises(WorkflowError, match="appointed"):
        service.request(PLAYER, command)
    with pytest.raises(WorkflowError, match="appointed"):
        service.get(PLAYER, outcome.proposal_id)
    # A separately bound campaign in the same authority cannot reopen this ID,
    # even for the same Discord user with current membership in both campaigns.
    second_store = OnboardingStore(
        ledger.engine,
        ledger.policy.model_copy(update={"campaign_id": uuid4(), "guild_id": 201}),
    )
    second_viewer = replace(PLAYER, guild_id=201)
    second_store.join(second_viewer, "second-campaign-join")
    with pytest.raises(WorkflowError, match="ASSISTANCE_UNAVAILABLE"):
        AssistanceService(second_store).get(second_viewer, outcome.proposal_id)
