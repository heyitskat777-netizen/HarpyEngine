"""The Doll's substantive answer and original-body departure in the Activity."""

import json

import pytest
from girlframe.services.m2_game import GameService
from girlframe.services.m3_vatgrown import DollService
from girlframe.services.onboarding import WorkflowError
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import tick
from test_vatgrown import ready

import mission_lab  # noqa: F401
from doll_controls import DEPARTURE, DOLL, RETURN
from specialist_scene import SpecialistScene
from test_identity_specialists import option, popup, press, respond, scoped, suggestions
from test_prince_activity import pass_windows

ledger = ledger_fixture


def test_doll_private_answer_and_actual_departure_reopen(ledger, tmp_path, monkeypatch):
    game, worker, gateway, _ = ready(ledger, tmp_path, monkeypatch)
    adapter = SpecialistScene(game, 900)
    assert DOLL in suggestions(game, PLAYER) and DOLL not in suggestions(game, OTHER)
    form = popup(adapter, PLAYER, DOLL)
    assert json.loads(option(form, "target"))["entity"] == str(OTHER.user_id)
    game.dice.faces = (4, 5)
    action = press(adapter, PLAYER, form, {
        "target": option(form, "target"), "heat": "0", "account": "I fade into the background.",
    })
    tick(worker, gateway, 3)
    pass_windows(game)
    root = action["action_id"]
    original = game.inspect(PLAYER, root)["receipt"]
    ask = scoped(game, PLAYER, "vat_doll_benefits")
    respond(ask, PLAYER, "vat_doll_benefits", {
        "options": ["information", "leave"], "text": "Who actually held the key?",
    })
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    reply = scoped(fresh, OTHER, "vat_doll_information")
    with pytest.raises(WorkflowError):
        respond(reply, PLAYER, "vat_doll_information", {"text": "An unauthorized answer."})
    secret = "PRIVATE_DOLL_ANSWER: I had it."
    respond(reply, OTHER, "vat_doll_information", {"text": secret})
    tick(worker, gateway, 5)
    records = DollService(fresh)
    assert records.view(PLAYER, root)["information"]["answer"] == secret
    with pytest.raises(WorkflowError):
        records.view(ADMIN, root)
    resume = SpecialistScene(fresh, 900)
    leave = popup(resume, PLAYER, DEPARTURE)
    press(resume, PLAYER, leave, {"account": "I actually leave without interception."})
    assert not fresh.scene_info(PLAYER, 900)["joined"]
    returning = popup(resume, PLAYER, RETURN)
    press(resume, PLAYER, returning, {"account": "I actually return to the same room."})
    assert fresh.scene_info(PLAYER, 900)["joined"]
    assert fresh.inspect(PLAYER, root)["receipt"] == original and fresh.dice.calls == 1
