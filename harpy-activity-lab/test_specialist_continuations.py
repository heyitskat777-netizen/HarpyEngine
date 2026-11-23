"""Verify that source work uses the original HarpyEngine participants."""

from uuid import uuid4

import mission_lab  # noqa: F401
import pytest
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from test_defeat_debts import owed
from test_defeat_replacement import destroyed
from test_enforcer_snoop import rolled as snoop_rolled
from test_dive_handler_void import nearby_director
from test_final_handler_workflows import bundled_registry  # noqa: F401
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import pass_tags, state, tick
from test_medical import injured, selection
from test_mockingbird_communion import source
from test_oldgen import ready as oldgen_ready

from owned_followups import OwnedFollowups
from handler_punishments import HandlerPunishments
from scene_beneath_work import SceneBeneathWork
from test_scene_popup_plays import play_options, start
from test_scene_beneath_followups import adapter, submit as scene_response

ledger = ledger_fixture


def test_post_mission_defeat_discipline_uses_only_the_original_debt(ledger):
    game, missions = owed(ledger)
    assert not HandlerPunishments(game).view(ADMIN)
    mission = missions.offer(ADMIN, "offer", "Relay return", (PLAYER.user_id,))
    reply = missions.respond(PLAYER, "accept", mission["id"], 1, "accept")
    started = missions.start(ADMIN, "dispatch", mission["id"], reply["revision"])
    missions.end(ADMIN, "complete", mission["id"], started["revision"], True)
    resumed = GameService(ledger)
    controls = HandlerPunishments(resumed)
    (pending,) = [
        card
        for card in controls.view(ADMIN)
        if card["instruction"] == "Defeat · Post-mission Punishment"
    ]
    assert not any(card["id"] == pending["id"] for card in controls.view(PLAYER))
    payload = {
        key: pending[key] for key in ("id", "revision", "work_revision", "action")
    } | {"answer": {"kind": "stimulant_injection"}}
    with pytest.raises(WorkflowError):
        controls.perform(PLAYER, str(uuid4()), payload)
    key = str(uuid4())
    result = controls.perform(ADMIN, key, payload)
    assert controls.perform(ADMIN, key, payload) == result
    assert not any(card["id"] == pending["id"] for card in controls.view(ADMIN))
    assert any(
        x.state == "fulfilled" and x.details.get("mission") == mission["id"]
        for x in state(resumed).obligations
    )


def room_map():
    return {900: ("relay", "Relay operations")}


def card(game, viewer, action):
    native = OwnedFollowups(game, room_map)
    scene = SceneBeneathWork(game, room_map, native)
    return next(
        row
        for row in scene.view(viewer, native.view(viewer))
        if row["action"] == action
    )


def submit(game, viewer, projection, op, values, *, key=None):
    native = OwnedFollowups(game, room_map)
    scene = SceneBeneathWork(game, room_map, native)
    return scene.perform(
        viewer,
        key or str(uuid4()),
        projection | {"answer": {"operation": op, "values": values}},
    )


def test_dive_call_assigns_boarding_and_answers_on_source_popup(ledger, monkeypatch):
    game, _, _, root = source(ledger, monkeypatch)
    invite = card(game, OTHER, "dive_call")
    assert invite["root"] == root
    with pytest.raises(WorkflowError):
        submit(game, PLAYER, invite, "accept", {"account": "Wrong participant"})
    key = str(uuid4())
    response = submit(
        game, OTHER, invite, "accept", {"account": "I board the cockpit."}, key=key
    )
    assert (
        submit(
            game, OTHER, invite, "accept", {"account": "I board the cockpit."}, key=key
        )
        == response
    )
    reopened = GameService(ledger)
    effect = card(reopened, OTHER, "dive_call")
    identity = state(game).sheets["3"].identities[0].id
    submit(
        reopened,
        OTHER,
        effect,
        "erase_identity_and_table_question",
        {
            "account": "My original link",
            "identity": identity,
            "question": "What do you remember?",
        },
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        question = card(reopened, viewer, "dive_call")
        assert question["scene"] == "What do you remember?"
        submit(reopened, viewer, question, "table", {"account": "My own answer."})
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert game.dice.calls == 1


def test_dive_handler_void_stays_with_original_body_controller(ledger):
    game, _, _, root, _, identity = nearby_director(ledger)
    work = card(game, OTHER, "handler_void")
    assert work["id"] == identity and work["root"] == root
    with pytest.raises(WorkflowError):
        submit(game, ADMIN, work, "surgery", {"account": "Wrong owner"})
    submit(game, OTHER, work, "surgery", {"account": "I request the actual procedure."})
    surgery = card(GameService(ledger), OTHER, "handler_void")
    assert surgery["operations"][0]["id"] == "record_surgery"
    submit(
        game,
        OTHER,
        surgery,
        "record_surgery",
        {
            "account": "Personnel perform and confirm the source procedure.",
            "performed": "yes",
            "removed": "yes",
        },
    )
    assert game.inspect(PLAYER, root)["state"] == "complete"


def test_defeat_medical_handoff_and_play_exchange_are_owned(ledger):
    service, game, identity = injured(ledger)
    work = card(game, PLAYER, "defeat_medical")
    assert work["id"] == identity
    submit(
        game,
        PLAYER,
        work,
        "propose",
        {"account": "Actual care and waking.", "vitals": "no"},
    )
    review = card(GameService(ledger), ADMIN, "defeat_medical")
    with pytest.raises(WorkflowError):
        submit(
            game,
            OTHER,
            review,
            "confirm",
            {"accepted": "yes", "evidence": "Wrong reviewer"},
        )
    submit(
        game,
        ADMIN,
        review,
        "confirm",
        {"accepted": "yes", "evidence": "The assigned Handler witnessed waking."},
    )
    exchange = card(game, PLAYER, "defeat_medical")
    submit(game, PLAYER, exchange, "exchange", selection().model_dump(mode="json"))
    assert service.get(PLAYER, identity)["stage"] == "complete"


def test_defeat_replacement_requires_pilot_and_handler_and_is_idempotent(ledger):
    game, duty, _ = destroyed(ledger)
    duty.begin(ADMIN, "new-period")
    proposal = card(game, PLAYER, "frame_replacement")
    with pytest.raises(WorkflowError):
        submit(game, ADMIN, proposal, "propose:THE ENFORCER", {})
    submit(
        game, PLAYER, proposal, "propose:THE ENFORCER", {"frame_name": "Still Standing"}
    )
    package = card(GameService(ledger), ADMIN, "frame_replacement")
    submit(
        game,
        ADMIN,
        package,
        "package",
        {
            "explanation": "Supply one verified control Asset.",
            "name0": "Replacement controls",
            "description0": "Controls inspected by the Handler.",
        },
    )
    reviewed = card(GameService(ledger), PLAYER, "frame_replacement")
    assert "Replacement controls" in reviewed["scene"]
    op = reviewed["operations"][0]["id"]
    key = str(uuid4())
    result = submit(game, PLAYER, reviewed, op, {"confirm": "yes"}, key=key)
    assert submit(game, PLAYER, reviewed, op, {"confirm": "yes"}, key=key) == result
    assert state(game).sheets["2"].frame == "THE ENFORCER"


def test_oldgen_advice_uses_native_scene_targets_and_recipient(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = oldgen_ready(ledger, tmp_path, monkeypatch)
    game.dice.faces = (4, 5)
    option = play_options(game, PLAYER, "old_dog_new_pups")
    assert option["can_start"] and option["targets"][0]["id"] == str(OTHER.user_id)
    root = start(
        game, "old_dog_new_pups", "Stay near the relay.", str(OTHER.user_id), heat=1
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    (maxim,) = play_options(game, PLAYER, "old_dog_new_pups")["choices"]
    assert not play_options(game, OTHER, "old_dog_new_pups")["choices"]
    scene_response(
        adapter(game), PLAYER, maxim, {"text": "Hold the line by the relay."}
    )
    (choice,) = play_options(game, OTHER, "old_dog_new_pups")["choices"]
    with pytest.raises(WorkflowError):
        scene_response(adapter(game), PLAYER, choice, {"text": "Wrong pilot"})
    scene_response(
        adapter(game), OTHER, choice, {"text": "I listened to their advice."}
    )
    assert GameService(ledger).inspect(PLAYER, root)["state"] == "complete"


def test_snoop_answers_stay_with_the_original_property_owner(
    ledger, tmp_path, monkeypatch
):
    game, _, _, root = snoop_rolled(ledger, tmp_path, monkeypatch)
    questions = card(game, PLAYER, "snoop_decision")
    assert questions["root"] == root
    submit(
        game,
        PLAYER,
        questions,
        "snoop_select",
        {"questions": ["illegal", "embarrassing"]},
    )
    for _ in range(2):
        finding = card(GameService(ledger), OTHER, "snoop_decision")
        with pytest.raises(WorkflowError):
            submit(game, PLAYER, finding, "snoop_answer", {"account": "Forged finding"})
        submit(
            game,
            OTHER,
            finding,
            "snoop_answer",
            {"account": "The owner records the actual finding."},
        )
    assert game.inspect(PLAYER, root)["state"] == "complete"
