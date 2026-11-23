"""Show Dog stays with its original Off-Duty participants and recipients."""

import json

import pytest
from girlframe.engine.m3_show_dog import RULE
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_show_dog import setup

import mission_lab  # noqa: F401
from off_duty_followups import OffDutyFollowups

ledger = ledger_fixture


def card(desk, viewer, identity):
    state = desk.view(viewer)
    work = next(row for row in state["work"] if row["id"] == identity)
    return state, work


def submit(scope, name, values):
    state, work = scope
    return {key: state[key] for key in ("period", "revision", "game_revision")} | {
        "action": "show_dog",
        "answer": {
            "id": work["id"], "work_revision": work["revision"], "operation": name, "values": values,
        },
    }


def select(scope, operation, key, match=lambda value: True):
    _, work = scope
    step = next(row for row in work["operations"] if row["id"] == operation)
    field = next(row for row in step["fields"] if row["key"] == key)
    return next(value for value, _ in field["options"] if match(value))


def test_show_dog_off_duty_and_private_correspondence_survive_reopen(ledger, tmp_path, monkeypatch):
    game, _, _, action, control, identity = setup(ledger, tmp_path, monkeypatch, (4, 4))
    original = game.inspect(PLAYER, action)["receipt"]
    desk = OffDutyFollowups(game)
    own = card(desk, PLAYER, identity)
    assert RULE == "girl.princess.show-dog"
    assert not any(row["id"] == identity for row in (desk.view(OTHER) or {}).get("work", []))
    addressed = "PRIVATE_ADDRESS: Meet me after the appearance."
    target = select(own, "message", "target", lambda value: json.loads(value)["entity"] == str(OTHER.user_id))
    message = submit(own, "message", {
        "target": target, "account": "I actually deliver the message.", "message": addressed,
    })
    with pytest.raises(WorkflowError):
        desk.perform(OTHER, "wrong-appearance-owner", message)
    saved = desk.perform(PLAYER, "actual-message", message)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    reopened = OffDutyFollowups(fresh)
    risk = submit(card(reopened, ADMIN, identity), "risk", {
        "punish": "no", "account": "The actual appearance raises no disciplinary issue.",
    })
    assert addressed not in json.dumps(reopened.show_dog.correspondence(ADMIN))
    assert addressed in json.dumps(reopened.show_dog.correspondence(OTHER))
    with pytest.raises(WorkflowError):
        reopened.perform(OTHER, "wrong-adjudicator", risk)
    reopened.perform(ADMIN, "original-handler-risk", risk)
    remaining = card(reopened, PLAYER, identity)
    second = submit(remaining, "second", {
        "npc": select(remaining, "second", "npc"), "desire": "emulate",
        "account": "The actual witness wants to imitate me.",
    })
    reopened.perform(PLAYER, "actual-interest", second)
    assert control.view(PLAYER, identity)["complete"]
    assert reopened.perform(PLAYER, "actual-message", message) == saved
    assert fresh.inspect(PLAYER, action)["receipt"] == original and fresh.dice.calls == 1
