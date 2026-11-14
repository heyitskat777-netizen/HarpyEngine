"""Real intake persistence/auth/native flow; activation must never masquerade as a freeze."""

import asyncio
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from test_facilitator_native import interaction
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, start, state

from girlframe.database import tables as t
from girlframe.discord_adapter.p1_shelving import open_request, register_shelving
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService
from girlframe.services.p1_shelving import ShelvingService


def database_rows(store):
    with store.engine.connect() as c:
        return {
            name: [dict(row) for row in c.execute(sa.select(table)).mappings()]
            for name, table in t.metadata.tables.items()
        }


def test_saved_intake_no_freeze_and_denied_activation_is_atomic(ledger):
    game, _, _, dice = setup_game(ledger)
    FacilitatorService(game).configure(ADMIN, "shelving-human", "user", ADMIN.user_id)
    action = start(game)
    before = state(game).model_dump(mode="json")
    service = ShelvingService(game)
    row = service.request(PLAYER, "individual-shelf-request")
    assert row["pilot_identity_proof"]["character"] == row["original_actor"]["incarnation"]
    with ledger.engine.connect() as c:
        assert c.scalar(
            sa.select(t.snapshots.c.event_id).where(
                t.snapshots.c.campaign_id == ledger.campaign_id,
                t.snapshots.c.event_id == row["pilot_identity_proof"]["snapshot_event"],
            )
        )
    assert service.request(PLAYER, "individual-shelf-request") == row
    assert service.request(PLAYER, "second-request") == row
    assert row["status"] == "requested" and row["player_requested"] is True
    assert (
        row["original_actor"]["incarnation"]
        == before["sheets"][str(PLAYER.user_id)]["character_id"]
    )
    assert service.tasks(OTHER) == []
    with pytest.raises(WorkflowError):
        service.view(OTHER, row["id"])
    with pytest.raises(WorkflowError):
        service.request(OTHER, "proxy-request", PLAYER.user_id)
    assert state(game).model_dump(mode="json") == before
    snapshot = database_rows(ledger)
    for viewer in (PLAYER, ADMIN):
        with pytest.raises(WorkflowError):
            service.change(
                viewer, "cannot-activate-" + str(viewer.user_id), row["id"], 1, "activate"
            )
        assert database_rows(ledger) == snapshot
    assert service.view(ADMIN, row["id"])["status"] == "requested"
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert dice.calls == 0
    assert ShelvingService(game).view(PLAYER, row["id"])["revision"] == 1
    result = service.change(PLAYER, "withdraw-request", row["id"], 1, "withdraw")
    assert result["status"] == "withdrawn"
    assert service.change(PLAYER, "withdraw-request", row["id"], 1, "withdraw") == result
    assert state(game).model_dump(mode="json") == before


def test_current_configured_gm_only_and_proposal_never_infers_player_request(ledger):
    game, _, _, _ = setup_game(ledger)
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, "original-gm", "user", ADMIN.user_id)
    service = ShelvingService(game)
    row = service.request(ADMIN, "gm-proposal", PLAYER.user_id)
    assert not row["player_requested"] and row["configuration_event"]
    assert service.view(PLAYER, row["id"])["own"]
    facilitator.configure(ADMIN, "replacement-gm", "user", OTHER.user_id)
    with pytest.raises(WorkflowError):
        service.change(ADMIN, "stale-gm", row["id"], 1, "decline")
    result = service.change(OTHER, "current-gm", row["id"], 1, "decline")
    assert result["status"] == "declined"
    assert result["configuration_event"] != row["configuration_event"]
    assert service.tasks(PLAYER) == []
    with pytest.raises(WorkflowError, match="STALE_SHELVING_REQUEST"):
        service.change(PLAYER, "stale-player", row["id"], 1, "withdraw")


def test_native_self_request_saved_review_and_withdrawal(ledger):
    game, _, _, dice = setup_game(ledger)
    service = ShelvingService(game)

    async def run():
        tree = MagicMock()
        register_shelving(tree, PLAYER.guild_id, game)
        group = tree.add_command.call_args.args[0]
        current = interaction(PLAYER, "native-shelf-request")
        await group.get_command("request").callback(current)
        packet = current.edit_original_response.call_args.kwargs
        assert "no player is frozen" in packet["content"]
        form = packet["view"]
        assert dict(form.fields[0].options) == {"withdraw": "Withdraw my shelving request"}
        row = service.tasks(PLAYER)[0]
        reopened = interaction(PLAYER, "native-shelf-reopen")
        await open_request(reopened, game, row["id"])
        packet = reopened.response.send_message.call_args.kwargs
        assert packet["ephemeral"] and not packet["allowed_mentions"].everyone
        form = packet["view"]
        form.values.update(operation=("withdraw",))
        await form.confirm.callback(reopened)
        assert form.completed and service.view(PLAYER, row["id"])["status"] == "withdrawn"
        assert dice.calls == 0

    asyncio.run(run())


def test_player_request_supersedes_gm_proposal_without_losing_provenance(ledger):
    game, _, _, _ = setup_game(ledger)
    FacilitatorService(game).configure(ADMIN, "proposal-gm", "user", ADMIN.user_id)
    service = ShelvingService(game)
    proposed = service.request(ADMIN, "proposal-first", PLAYER.user_id)
    requested = service.request(PLAYER, "player-explicitly-requests")
    assert requested["id"] == proposed["id"]
    assert requested["revision"] == 2 and requested["player_requested"]
    assert requested["player_requester"] == PLAYER.user_id
    assert requested["initiator"] == ADMIN.user_id
    assert requested["configuration_event"] == proposed["configuration_event"]
    assert service.request(PLAYER, "player-explicitly-requests") == requested
    assert service.request(PLAYER, "another-current-request") == requested
    with pytest.raises(WorkflowError, match="STALE_SHELVING_REQUEST"):
        service.change(ADMIN, "old-proposal-control", proposed["id"], 1, "decline")

    # A changed sheet field is not an authenticated replacement source.
    replacement = state(game)
    replacement.sheets[str(PLAYER.user_id)].character_id = "synthetic-replacement-character"
    with ledger.transaction() as c:
        c.execute(
            t.m2["m2_state"]
            .update()
            .where(t.m2["m2_state"].c.campaign_id == ledger.campaign_id)
            .values(body_json=replacement.model_dump_json())
        )
    snapshot = database_rows(ledger)
    for key in ("replacement-player-request", "player-explicitly-requests"):
        with pytest.raises(WorkflowError, match="STALE_CHARACTER"):
            service.request(PLAYER, key)
        assert database_rows(ledger) == snapshot
    assert service.view(PLAYER, requested["id"])["original_actor"] == requested["original_actor"]


def test_cached_gm_replays_require_current_authority(ledger):
    game, _, _, _ = setup_game(ledger)
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, "replay-original-gm", "user", ADMIN.user_id)
    service = ShelvingService(game)
    row = service.request(ADMIN, "replay-proposal", PLAYER.user_id)
    result = service.change(ADMIN, "replay-decline", row["id"], 1, "decline")
    assert service.change(ADMIN, "replay-decline", row["id"], 1, "decline") == result
    facilitator.configure(ADMIN, "replay-new-gm", "user", OTHER.user_id)
    snapshot = database_rows(ledger)
    with pytest.raises(WorkflowError, match="currently configured"):
        service.request(ADMIN, "replay-proposal", PLAYER.user_id)
    with pytest.raises(WorkflowError, match="currently configured"):
        service.change(ADMIN, "replay-decline", row["id"], 1, "decline")
    assert database_rows(ledger) == snapshot
