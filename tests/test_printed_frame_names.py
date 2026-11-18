"""Canonical JANUS choices with read compatibility for existing synthetic state."""

import hashlib
import json

import sqlalchemy as sa
from test_creation_review import ready
from test_ledger import PLAYER, seed
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state

from girlframe.database import tables as t
from girlframe.engine.drafts import DraftInput
from girlframe.engine.playbooks import FRAME_TYPES
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import digest, load_registry

PREVIOUS_NAME = "-".join(("JANUS", "B"))


def test_catalog_and_existing_draft_project_only_the_printed_name(ledger):
    seed(ledger, notes=PREVIOUS_NAME)
    with ledger.transaction() as conn:
        scope = t.characters.c.user_id == str(PLAYER.user_id)
        old = json.loads(conn.scalar(sa.select(t.characters.c.public_json).where(scope)))
        old["frame_playbook"] = PREVIOUS_NAME
        conn.execute(t.characters.update().where(scope).values(public_json=json.dumps(old)))
    assert list(FRAME_TYPES).count("JANUS") == 1 and PREVIOUS_NAME not in FRAME_TYPES
    assert ledger.draft(PLAYER)["frame_playbook"] == "JANUS"
    assert ledger.draft(PLAYER)["notes"] == PREVIOUS_NAME
    assert (
        DraftInput(
            callsign="FIXTURE", girl_playbook="MOCKINGBIRD", frame_playbook=PREVIOUS_NAME
        ).frame_playbook
        == "JANUS"
    )


def test_saved_character_review_needs_no_new_approval_for_label_alone(ledger):
    review, _, _ = ready(ledger)
    current = review.get(PLAYER)
    old_review = current.sheet.model_dump(mode="json")
    old_review["creation"]["frame_playbook"] = PREVIOUS_NAME
    old_hash = hashlib.sha256(json.dumps(old_review, sort_keys=True).encode()).hexdigest()
    with ledger.transaction() as conn:
        event = ledger._audit(conn, PLAYER.user_id, "old-review", "character.review_saved", {})
        conn.execute(
            t.creation_reviews.insert().values(
                campaign_id=ledger.campaign_id,
                user_id=str(PLAYER.user_id),
                revision=current.saved_revision + 1,
                dependency_hash=old_hash,
                body_json=json.dumps(old_review),
                event_id=event,
            )
        )
    reopened = CreationReviewService(ledger).get(PLAYER)
    assert reopened.saved_current and reopened.fingerprint == current.fingerprint


def test_existing_live_sheet_reopens_with_same_identity_and_resources(ledger):
    game, _, _, _ = setup_game(ledger)
    before = state(game)
    body = before.model_dump(mode="json")
    sheet = body["sheets"][str(PLAYER.user_id)]
    sheet["frame"] = PREVIOUS_NAME
    sheet["review"]["creation"]["frame_playbook"] = PREVIOUS_NAME
    current = t.m2["m2_state"]
    with ledger.transaction() as conn:
        conn.execute(
            current.update()
            .where(current.c.campaign_id == ledger.campaign_id)
            .values(body_json=json.dumps(body))
        )
    assert state(GameService(ledger)) == before
    assert ledger.draft(PLAYER)["frame_playbook"] == "JANUS"


def test_registry_approval_survives_only_the_exact_name_only_edit():
    registry = load_registry()
    assert digest(registry) == "73c4e0c1f3a350fa715fc17d082e40f82f1de05cd520804dae260f542a2f9941"
    first, *rest = registry.entries
    changed = first.model_copy(update={"title": "A different rule title"})
    assert digest(registry.model_copy(update={"entries": (changed, *rest)})) != digest(registry)
