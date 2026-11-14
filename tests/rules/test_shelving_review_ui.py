"""Private current-actor review is a read-only observation, never a freeze button."""

import asyncio

from test_facilitator_native import interaction
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game
from test_shelving_intake import database_rows

from girlframe.discord_adapter.p1_shelving import open_request
from girlframe.services.p1_facilitator import FacilitatorService
from girlframe.services.p1_shelving import ShelvingService


def test_native_actor_review_rechecks_current_request_and_facilitator_without_writes(ledger):
    game, _, _, dice = setup_game(ledger)
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, "native-review-human", "user", ADMIN.user_id)
    intake = ShelvingService(game)
    request = intake.request(ADMIN, "native-review-proposal", PLAYER.user_id)

    async def opened(viewer, key):
        current = interaction(viewer, key)
        await open_request(current, game, request["id"])
        packet = current.response.send_message.call_args.kwargs
        assert packet["ephemeral"] and not packet["allowed_mentions"].everyone
        return current, packet["view"]

    async def submit(viewer, form, key):
        current = interaction(viewer, key)
        form.values.update(operation=("verify_actor",))
        await form.confirm.callback(current)
        packet = current.edit_original_response.call_args.kwargs
        assert not packet["allowed_mentions"].everyone
        assert current.response.defer.call_args.kwargs["ephemeral"]
        return packet["content"]

    async def run():
        _, own_form = await opened(PLAYER, "native-review-owner")
        assert dict(own_form.fields[0].options) == {"withdraw": "Withdraw my shelving request"}
        _, form = await opened(ADMIN, "native-review-gm")
        assert "verify_actor" in dict(form.fields[0].options)
        assert "activate" not in dict(form.fields[0].options)
        before = database_rows(ledger)
        content = await submit(ADMIN, form, "native-review-proposal-check")
        assert form.completed
        assert "for this read only" in content and "no player is frozen" in content
        assert "GM proposal, not player consent" in content
        assert request["id"] in content and "still pending" in content
        for private in (
            request["original_actor"]["incarnation"],
            request["pilot_identity_proof"]["snapshot_event"],
            request["pilot_identity_proof"]["profile"],
            request["configuration_event"],
        ):
            assert private not in content
        assert database_rows(ledger) == before

        _, stale = await opened(ADMIN, "native-review-before-promotion")
        intake.request(PLAYER, "native-review-player-promotion")
        before = database_rows(ledger)
        content = await submit(ADMIN, stale, "native-review-old-revision")
        assert not stale.completed and "STALE_SHELVING_REQUEST" in content
        assert database_rows(ledger) == before
        _, current = await opened(ADMIN, "native-review-current-player-request")
        content = await submit(ADMIN, current, "native-review-player-check")
        assert "Player request" in content and "not player consent" not in content
        assert database_rows(ledger) == before

        _, revoked = await opened(ADMIN, "native-review-before-reconfiguration")
        facilitator.configure(ADMIN, "native-review-new-human", "user", OTHER.user_id)
        before = database_rows(ledger)
        content = await submit(ADMIN, revoked, "native-review-revoked-click")
        assert not revoked.completed and "currently configured" in content
        assert database_rows(ledger) == before
        _, replacement = await opened(OTHER, "native-review-new-human-open")
        content = await submit(OTHER, replacement, "native-review-new-human-check")
        assert replacement.completed and "for this read only" in content
        assert database_rows(ledger) == before
        assert intake.view(PLAYER, request["id"])["status"] == "requested"
        assert dice.calls == 0

    asyncio.run(run())
