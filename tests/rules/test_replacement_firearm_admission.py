"""A free package cannot silently create only a label for an unissued real pistol."""

import pytest
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_replacement import supplied
from test_replacement_service import accept, pending, propose, quote

from girlframe.engine.m3_personal_firearm import RULE
from girlframe.services.onboarding import WorkflowError


def test_reviewed_free_package_only_issues_actual_pistol_after_original_owner_confirmation(
    ledger, tmp_path, monkeypatch
):
    replacement, game, _, work = pending(ledger)
    acquisition = approved(ledger, game, tmp_path, monkeypatch)
    replacement.missions.access.registry = acquisition.registry
    proposed = propose(replacement, work)
    before = state(game).model_dump_json()
    quote(replacement, proposed["package_id"], supplied(additional_rules=(RULE,)))
    assert state(game).model_dump_json() == before
    data = replacement.get(PLAYER, work)
    with pytest.raises(WorkflowError):
        replacement.apply(
            OTHER,
            "cannot-author-other-body",
            work,
            data["revision"],
            data["game_revision"],
            data["package_revision"],
        )
    assert not state(game).personal_firearms
    accept(replacement, work)
    assert len(state(game).personal_firearms) == 1
    assert state(game).personal_firearms[0].source_work == work
