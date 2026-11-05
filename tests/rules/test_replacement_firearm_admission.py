"""A free package cannot silently create only a label for an unissued real pistol."""

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ledger as ledger
from test_m2_game import state
from test_replacement import supplied
from test_replacement_service import pending, propose, quote

from girlframe.engine.m3_personal_firearm import RULE
from girlframe.services.onboarding import WorkflowError


def test_even_reviewed_paid_firearm_cannot_skip_distinct_free_package_issuance(
    ledger, tmp_path, monkeypatch
):
    replacement, game, _, work = pending(ledger)
    acquisition = approved(ledger, game, tmp_path, monkeypatch)
    replacement.missions.access.registry = acquisition.registry
    proposed = propose(replacement, work)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="actual owned pistol"):
        quote(replacement, proposed["package_id"], supplied(additional_rules=(RULE,)))
    assert state(game).model_dump_json() == before
