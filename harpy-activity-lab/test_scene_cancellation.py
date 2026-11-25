"""Scene recovery uses native Handler authority and preserves filed rolls."""

from uuid import uuid4

import mission_lab  # noqa: F401
import pytest
from scene_plays import ScenePlays
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, tick

from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def scene_adapter(game, channel=900):
    return ScenePlays(game, channel, ADMIN, PLAYER, OTHER, handler_proxy=False)


def pending_keep(ledger):
    game, worker, gateway, dice = setup_game(ledger, faces=(5, 6))
    scene = scene_adapter(game)
    root = scene.perform(
        PLAYER,
        str(uuid4()),
        "keep-start",
        {
            "context": "Hold the relay steady.",
            "confirmed": True,
            "character_revision": game.sheet(PLAYER)["revision"],
        },
    )["action_id"]
    tick(worker, gateway, 3)
    return game, scene, worker, gateway, dice, root


def test_cancel_preserves_native_handler_ownership_receipt_and_retry(ledger):
    game, scene, worker, gateway, dice, root = pending_keep(ledger)
    original = game.inspect(PLAYER, root)["receipt"]
    assert original["faces"] == [5, 6]
    assert scene.cancellation(ADMIN)["can_cancel"] is True
    for viewer in (PLAYER, OTHER):
        projected = scene.cancellation(viewer)
        assert projected["id"] == root
        assert projected["can_cancel"] is False
        assert projected["can_request"] is (viewer == PLAYER)
        assert projected["owner_id"] == str(PLAYER.user_id)
        assert projected["reason"] == "The Handler must cancel this pending Play."
        with pytest.raises(WorkflowError, match="Only configured staff"):
            scene.cancel(viewer, str(uuid4()), {"id": root, "confirmed": True})
    with pytest.raises(ValueError, match="Confirm cancellation"):
        scene.cancel(ADMIN, str(uuid4()), {"id": root, "confirmed": False})
    with pytest.raises(WorkflowError, match="this scene's original"):
        scene_adapter(game, 901).cancel(ADMIN, str(uuid4()), {"id": root, "confirmed": True})
    key = str(uuid4())
    payload = {"id": root, "confirmed": True}
    result = scene.cancel(ADMIN, key, payload)
    assert result["state"] == "aborted" and result["receipt_preserved"]
    assert scene.cancel(ADMIN, key, payload) == result
    tick(worker, gateway, 4)
    reopened = GameService(ledger)
    assert reopened.inspect(PLAYER, root)["receipt"] == original
    assert reopened.inspect(PLAYER, root)["state"] == "aborted"
    assert not scene_adapter(reopened).cancellation(PLAYER)
    assert not reopened.choices(PLAYER)
    assert not reopened.choices(ADMIN)
    assert dice.calls == 1
    receipt = scene_adapter(reopened).receipts(PLAYER, {"900": "relay"})[0]
    assert receipt["state"] == "aborted"
    assert receipt["roll"] == {"faces": [5, 6], "pre_total": 11}
    assert receipt["pending"] == []
    assert reopened.scene_info(PLAYER, 900)["lock"]["state"] == "released"
    fresh_scene = scene_adapter(reopened)
    fresh = fresh_scene.perform(
        PLAYER,
        str(uuid4()),
        "keep-start",
        {
            "context": "The next transmission arrives.",
            "confirmed": True,
            "character_revision": reopened.sheet(PLAYER)["revision"],
        },
    )["action_id"]
    assert fresh != root
    assert fresh_scene.cancel(ADMIN, key, payload) == result
    assert fresh_scene.cancellation(ADMIN)["id"] == fresh
    with pytest.raises(WorkflowError, match="STALE_ACTION"):
        fresh_scene.cancel(ADMIN, str(uuid4()), payload)
    unrolled = fresh_scene.cancel(ADMIN, str(uuid4()), {"id": fresh, "confirmed": True})
    assert unrolled["receipt_preserved"] is False
    assert reopened.inspect(PLAYER, fresh)["receipt"] is None
    assert reopened.inspect(PLAYER, root)["receipt"] == original
