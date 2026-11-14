"""Current private review evidence is not an availability change or a saved permit."""

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state
from test_shelving_intake import database_rows

from girlframe.database import tables as t
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService
from girlframe.services.p1_shelving import ShelvingService
from girlframe.services.p1_shelving_review import ShelvingReviewService


def test_current_facilitator_review_is_private_read_only_and_never_cached_authority(ledger):
    game, _, _, dice = setup_game(ledger)
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, "review-original-human", "user", ADMIN.user_id)
    intake = ShelvingService(game)
    request = intake.request(PLAYER, "review-original-player")
    reviews = ShelvingReviewService(game)
    before = database_rows(ledger)
    evidence = reviews.inspect(ADMIN, request["id"], 1)
    assert evidence.actor.model_dump(mode="json") == request["original_actor"]
    assert evidence.identity.character == request["pilot_identity_proof"]["character"]
    assert evidence.player_requested and evidence.availability_authority is False
    assert evidence.game_revision == state(game).revision
    assert evidence.reviewer == ADMIN.user_id
    assert reviews.inspect(ADMIN, request["id"], 1) == evidence
    with pytest.raises(WorkflowError, match="currently configured"):
        reviews.inspect(PLAYER, request["id"], 1)
    with pytest.raises(WorkflowError, match="STALE_SHELVING_REQUEST"):
        reviews.inspect(ADMIN, request["id"], 2)
    with ledger.engine.connect() as connection:
        with pytest.raises(WorkflowError, match="open SQLite transaction"):
            reviews.inspect_transaction(connection, ADMIN, request["id"], 1)
    assert database_rows(ledger) == before
    assert dice.calls == 0

    facilitator.configure(ADMIN, "review-replacement-human", "user", OTHER.user_id)
    before = database_rows(ledger)
    with pytest.raises(WorkflowError, match="currently configured"):
        reviews.inspect(ADMIN, evidence.request_id, evidence.request_revision)
    current = reviews.inspect(OTHER, request["id"], 1)
    assert current.configuration_event != evidence.configuration_event
    assert current.reviewer == OTHER.user_id and current.actor == evidence.actor
    assert database_rows(ledger) == before
    intake.change(PLAYER, "review-request-withdrawal", request["id"], 1, "withdraw")
    before = database_rows(ledger)
    with pytest.raises(WorkflowError, match="STALE_SHELVING_REQUEST"):
        reviews.inspect(OTHER, request["id"], 1)
    assert database_rows(ledger) == before


def test_review_rechecks_target_membership_and_keeps_gm_proposal_distinct(ledger):
    game, _, _, _ = setup_game(ledger)
    FacilitatorService(game).configure(ADMIN, "review-proposal-human", "user", ADMIN.user_id)
    intake = ShelvingService(game)
    request = intake.request(ADMIN, "review-gm-proposal", PLAYER.user_id)
    reviews = ShelvingReviewService(game)
    evidence = reviews.inspect(ADMIN, request["id"], 1)
    assert evidence.player_requested is False and evidence.availability_authority is False
    with ledger.transaction() as connection:
        connection.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(PLAYER.user_id),
            )
            .values(active=False)
        )
    before = database_rows(ledger)
    with pytest.raises(WorkflowError, match="active campaign member"):
        reviews.inspect(ADMIN, request["id"], 1)
    assert database_rows(ledger) == before
