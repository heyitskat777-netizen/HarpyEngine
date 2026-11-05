"""An imprisoned original returns only by actual Handler and original-owner choices."""

from uuid import uuid4

import pytest
from test_career_service import ended
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m2 import PilotSheet
from girlframe.services.onboarding import WorkflowError


def restore(service, game, identity):
    return service.answer_return(
        PLAYER,
        str(uuid4()),
        identity,
        state(game).revision,
        accept=True,
        account="The original owner resumes her Girl",
    )


def offer(service, game):
    return service.offer_return(
        ADMIN,
        str(uuid4()),
        "original-ended-career",
        state(game).revision,
        0,
        "The Handler explicitly releases the original Girl",
    )


def test_handler_offer_owner_decline_preserves_original_archive_and_inactive_character(ledger):
    service, game, actor, _, _ = ended(ledger, reason="imprisonment")
    ticket = offer(service, game)
    archive = state(game).career_archives[-1]
    with pytest.raises(WorkflowError, match="human owner"):
        service.answer_return(
            ADMIN,
            str(uuid4()),
            ticket["id"],
            state(game).revision,
            accept=True,
            account="Cannot forge another person's choice",
        )
    with pytest.raises(WorkflowError):
        service.get_return(OTHER, ticket["id"])
    service.answer_return(
        PLAYER,
        str(uuid4()),
        ticket["id"],
        state(game).revision,
        accept=False,
        account="The original owner chooses not to resume",
    )
    assert actor.entity not in state(game).sheets
    assert state(game).career_archives[-1] == archive
    assert not service.return_requests(PLAYER)


def test_actual_owner_acceptance_restores_exact_original_without_healing_or_uid_bond_alias(ledger):
    service, game, actor, _, _ = ended(ledger, reason="imprisonment")
    archive = state(game).career_archives[-1]
    original = PilotSheet.model_validate_json(archive.sheet_json)
    ticket = offer(service, game)
    service.answer_return(
        PLAYER,
        str(uuid4()),
        ticket["id"],
        state(game).revision,
        accept=True,
        account="I choose to resume the original Girl",
    )
    restored = state(game).sheets[actor.entity]
    assert restored.character_id == actor.incarnation
    assert restored.permissions == original.permissions and restored.heat == original.heat
    assert restored.identities == original.identities and restored.assets == original.assets
    assert state(game).career_archives[-1] == archive
    assert all(actor.entity not in key.split(":") for key in state(game).bonds)
    assert state(game).career_returns[-1].state == "returned"


def test_death_is_not_a_return_offer_and_stale_roster_does_not_silently_reset_status(ledger):
    service, game, _, _, _ = ended(ledger, reason="death")
    with pytest.raises(WorkflowError, match="archived Girl"):
        offer(service, game)


def test_return_preserves_active_replacement_in_reserve_without_resource_transfer(ledger):
    from test_career_service import begin

    service, game, actor, _, _ = ended(ledger, reason="imprisonment")
    original = state(game).career_archives[-1]
    fresh = begin(service)
    # Synthetic completed activation of a genuinely distinct newcomer, with distinct resources.
    with ledger.transaction() as c:
        canon = state(game)
        newcomer = PilotSheet.model_validate_json(original.sheet_json)
        newcomer.character_id, newcomer.callsign = fresh["character"], "ACTUAL_NEWCOMER"
        newcomer.source_profile_revision = fresh["profile_revision"]
        newcomer.permissions, newcomer.heat = 9, 7
        canon.sheets["2"], canon.order = newcomer, (3, 2)
        game.event(c, 2, str(uuid4()), "synthetic.explicit_completed_activation", canon)
    ticket = offer(service, game)
    restore(service, game, ticket["id"])
    canon = state(game)
    assert canon.sheets["2"].character_id == actor.incarnation
    assert canon.sheets["2"].permissions == 0 and canon.sheets["2"].heat == 0
    saved = canon.career_archives[-1]
    assert saved.ending == "reserve" and saved.actor.incarnation == fresh["character"]
    held = PilotSheet.model_validate_json(saved.sheet_json)
    assert held.permissions == 9 and held.heat == 7 and held.callsign == "ACTUAL_NEWCOMER"


def test_latest_original_archive_prevents_returning_an_old_resource_snapshot(ledger):
    from girlframe.services.m3_careers import end_in_transaction, synchronize_end

    service, game, actor, _, _ = ended(ledger, reason="imprisonment")
    ticket = offer(service, game)
    restore(service, game, ticket["id"])
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 5
        event = str(uuid4())
        canon = end_in_transaction(
            c,
            game,
            canon,
            actor,
            reason="imprisonment",
            source_event=event,
            account="A later actual imprisonment",
            archive_id="later-original",
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_later_ending", canon, event_id=event)
        synchronize_end(c, game, canon.career_archives[-1])
    assert [x["id"] for x in service.return_candidates(ADMIN)] == ["later-original"]
    with pytest.raises(WorkflowError, match="archived Girl"):
        offer(service, game)
