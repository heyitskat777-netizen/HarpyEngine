"""Actual acquisition transaction and immutable source proof across the common boundary."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_secretary as rules
from girlframe.services.m2_state import load_state
from girlframe.services.m3_secretary import SecretaryService, paid
from girlframe.services.onboarding import WorkflowError


def test_real_service_common_acquisition_rollback_retry_source_and_private_receipt(
    ledger, tmp_path, monkeypatch
):
    game, _, _ = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary.RULE, rules.RULE))
    service = SecretaryService(ledger)
    original = state(game)
    held = next(x for x in awards.awards(original) if x.phase == "held")
    revision = original.revision
    account = "PRIVATE_COMMON_RECEIPT: my actual original personal Secretary acquisition"
    with ledger.engine.connect() as c:
        events = c.scalar(sa.select(sa.func.count()).select_from(t.events))
    for viewer, expected in ((PLAYER, revision), (ADMIN, revision - 1)):
        with pytest.raises(WorkflowError):
            service.buy(viewer, str(uuid4()), held.id, expected, account)
        assert state(game) == original
    key = str(uuid4())
    actual_event = service.game.event

    def interrupted(*args, **kwargs):
        actual_event(*args, **kwargs)
        assert kwargs["award_id"] == held.id and kwargs["rule_id"] == rules.RULE
        # The real receipt, consumed Award, audit and canonical history are staged.
        staged = load_state(args[0], ledger.campaign_id)
        assert rules.acquisitions(staged) and awards.awards(staged)[0].phase == "spent"
        raise WorkflowError("INTERRUPTED_AFTER_ACTUAL_EVENT: rollback this transaction")

    with monkeypatch.context() as patch:
        patch.setattr(service.game, "event", interrupted)
        with pytest.raises(WorkflowError, match="INTERRUPTED_AFTER_ACTUAL_EVENT"):
            service.buy(ADMIN, key, held.id, revision, account)
    assert state(game) == original and rules.acquisitions(state(game)) == ()
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.events)) == events
    # Exact failed key is usable after rollback; exact committed retry is unchanged.
    result = service.buy(ADMIN, key, held.id, revision, account)
    saved = state(game)
    assert result == {"id": "secretary:" + held.id, "phase": "acquired"}
    assert service.buy(ADMIN, key, held.id, revision, account) == result
    assert (
        state(game) == saved and saved.sheets == original.sheets and saved.bonds == original.bonds
    )
    receipt = rules.acquisitions(saved)[0]
    with ledger.engine.connect() as c:
        assert paid(game, c, saved, receipt.id) == receipt
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                t.events.c.campaign_id == ledger.campaign_id, t.events.c.id == receipt.event
            )
        ).one()
        assert (audit.kind, audit.actor_id) == ("m3.handler_advancement_spent", "1")
        assert account not in audit.payload_json
    # A later same-shaped fact is insufficient: prove against the original receipt birth.
    forged = saved.model_copy(deep=True)
    fact = next(x for x in forged.facts if x.get("id") == receipt.id)
    fact["body"] = receipt.model_copy(
        update={"account": "FORGED_PRIVATE_ORIGINAL"}
    ).model_dump_json()
    with ledger.engine.connect() as c, pytest.raises(WorkflowError, match="exact Secretary spend"):
        paid(game, c, forged, receipt.id)
    with pytest.raises(WorkflowError):
        service.buy(ADMIN, str(uuid4()), held.id, saved.revision, account)
    assert state(game) == saved
