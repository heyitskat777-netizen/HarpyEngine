"""The start dashboard reads real saved setup; it never creates consent or progress."""

import json

import pytest
import sqlalchemy as sa
from test_creation_review import ready
from test_dual_role_setup import appointed_pilot
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger

from girlframe.database import tables as t
from girlframe.engine.m2 import ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer
from girlframe.services.start_dashboard import StartDashboardService


def counts(store):
    with store.engine.connect() as connection:
        return {
            table.name: connection.scalar(sa.select(sa.func.count()).select_from(table))
            for table in t.metadata.sorted_tables
        }


def test_new_member_dashboard_has_no_side_effects_and_resumes_after_real_join(ledger):
    source = StartDashboardService(ledger)
    before = counts(ledger)
    initial = source.snapshot(PLAYER)
    assert initial["owner"] == PLAYER.user_id
    assert not initial["joined"] and not initial["campaign"]["bound"]
    assert initial["character"]["next_route"] == "join"
    assert not initial["character"]["exists"]
    assert counts(ledger) == before
    with pytest.raises(WorkflowError):
        source.snapshot(GuildViewer(PLAYER.user_id, 999, True, False))
    assert counts(ledger) == before

    ledger.join(PLAYER, "start-real-member-join")
    joined_counts = counts(ledger)
    resumed = source.snapshot(PLAYER)
    assert resumed["joined"] and resumed["campaign"]["bound"]
    assert resumed["character"]["next_route"] == "profile"
    assert counts(ledger) == joined_counts


def test_completed_review_then_explicit_activation_resumes_without_reset(ledger):
    review, _, _ = ready(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic dashboard fixture only",
                reference="offline test, not live approval",
            ),
        }
    )
    source = StartDashboardService(ledger)
    before = counts(ledger)
    draft = source.snapshot(PLAYER)
    assert draft["character"]["review_ready"]
    assert not draft["character"]["saved_current"]
    assert draft["character"]["next_route"] == "review"
    assert counts(ledger) == before
    current = review.get(PLAYER)
    review.save(PLAYER, "start-owner-save-review", current.saved_revision, current.fingerprint)
    saved = source.snapshot(PLAYER)
    assert saved["character"]["next_route"] == "activate"
    assert not saved["activated"]

    game = GameService(ledger)
    game.activate(PLAYER, "start-owner-explicit-activation", current.fingerprint)
    active_counts = counts(ledger)
    active = source.snapshot(PLAYER)
    assert active["activated"] and active["character"]["next_route"] == "ready"
    assert all(step["status"] == "complete" for step in active["character"]["steps"])
    assert counts(ledger) == active_counts
    assert active["character"]["callsign"] == "SYNTH"


def test_handler_and_pilot_share_dashboard_without_peer_private_data(ledger):
    appointed_pilot(ledger)
    source = StartDashboardService(ledger)
    before = counts(ledger)
    own = source.snapshot(PLAYER)
    peer = source.snapshot(OTHER)
    assert own["is_handler"] and own["character"]["exists"] and not own["is_admin"]
    assert own["campaign"]["pilot_count"] == 2
    assert own["campaign"]["handler_id"] == PLAYER.user_id
    assert own["campaign"]["status_current"] and own["campaign"]["rulings_ready"]
    assert own["character"]["review_ready"]
    assert not peer["is_handler"] and peer["owner"] == OTHER.user_id
    text = json.dumps(own)
    assert "OWNER_PROFILE_SECRET" not in text
    assert "PRIVATE_CANARY" not in text and "SHARED_BOND_CONTEXT" not in text
    assert counts(ledger) == before
    # Admin capability never turns someone else's character into this viewer's.
    admin = source.snapshot(ADMIN)
    assert admin["is_admin"] and not admin["character"]["exists"]


def test_pending_owner_task_and_outgoing_bond_keep_distinct_inbox_scope(ledger, monkeypatch):
    from girlframe.engine.inbox import InboxItem
    from girlframe.services.inbox import InboxService

    # Authorized projection inputs only: no player decision or source approval is
    # fabricated. This normal checks the shared page/count classifier itself.
    task = InboxItem(
        "task:owned",
        "m2",
        "owned",
        1,
        "plays",
        "Your pending choice",
        "Your character",
        "pending",
        False,
        False,
        "Complete your own choice",
        "",
        None,
        task="m2_choice",
    )
    outgoing = InboxItem(
        "bond:outgoing",
        "bond",
        "outgoing",
        1,
        "bonds",
        "Starting Bond",
        "Other participant",
        "pending",
        False,
        False,
        "Other player must accept",
        "",
        None,
    )
    source = InboxService(ledger)
    monkeypatch.setattr(source, "items", lambda viewer: (task, outgoing))
    own = source.page(PLAYER, "you")
    waiting = source.page(PLAYER, "waiting")
    assert own.counts["pending"] == 2
    assert own.counts["you"] == own.counts["waiting"] == 1
    assert own.item == task and waiting.item == outgoing
    assert own.total == waiting.total == 1
