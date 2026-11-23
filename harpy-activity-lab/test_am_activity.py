"""Original operators own the AM discovery and circuit effects after reopening."""

import json

import pytest
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_am, m3_am_body, m3_am_branch, m3_am_code, m3_am_reset
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m3_am_records import RecordsService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from test_am_code import rolled as code_rolled
from test_am_factory_reset import fourth_limiter
from test_am_records import ANSWER, DOCUMENT, QUESTION
from test_am_records import rolled as records_rolled
from test_enforcement_initiative import cast_target
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, state, tick
from test_mission_service import service
from test_physical_operations import place
from test_world import initial

import mission_lab  # noqa: F401
from am_scene_controls import (
    BODY_PREPARE,
    BODY_RETURN,
    BRANCH_ASSIGN,
    BRANCH_TAKEOVER,
    CODE,
    CODE_CONFIRM,
    SCRUTINY,
    SCRUTINY_CONFIRM,
)
from specialist_scene import SpecialistScene
from test_identity_specialists import option, popup, press, respond, scoped, suggestions
from test_prince_activity import pass_windows

ledger = ledger_fixture


def test_am_circuit_uses_original_discovery_roll_and_separate_operator(ledger, tmp_path, monkeypatch):
    _, game = service(ledger, girl="AM", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(m3_am.RULE, m3_am_code.RULE))
    policy = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(update={
        "m3_approval": policy.model_copy(update={"subsystems": policy.subsystems | {"world"}}),
    })
    with ledger.transaction() as c:
        snapshot = state(game)
        snapshot.world = initial()
        game.event(c, 1, "actual-am-scene", "synthetic.am_scene", place(snapshot, 2, mode="outside_frame"))
    npc = ActorRef(kind="npc", entity="am-circuit-operator")
    WorldService(MissionService(ledger)).npc(
        ADMIN, "actual-am-operator", state(game).revision,
        Npc(id=npc.entity, name="Original operator", jobs=("guard",), controller=ADMIN.user_id,
            detail="Actually recognizes the original AM.", cell=(0, 0), revealed=True),
    )
    cast_target(game, npc)
    scene = SpecialistScene(game, 900)
    assert SCRUTINY in suggestions(game, PLAYER) and SCRUTINY not in suggestions(game, OTHER)
    candidate = popup(scene, PLAYER, SCRUTINY)
    target = next(value for value, _ in candidate[1]["fields"][0]["options"]
                  if json.loads(value)["entity"] == npc.entity)
    filed = press(scene, PLAYER, candidate, {"target": target, "account": "The actual operator recognizes me."})
    discovery = popup(scene, ADMIN, SCRUTINY_CONFIRM)
    assert discovery[0]["id"] == f"{SCRUTINY_CONFIRM}:{filed['id']}"
    with pytest.raises(WorkflowError):
        press(scene, OTHER, discovery, {"realized": "yes", "lower": "yes", "human": "yes", "account": "Wrong."})
    press(scene, ADMIN, discovery, {"realized": "yes", "lower": "yes", "human": "yes", "account": "I recognize this AM."})
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    assert SCRUTINY in suggestions(game, PLAYER)
    prepared = popup(scene, PLAYER, SCRUTINY)
    game.dice.faces = (4, 5)
    action = press(scene, PLAYER, prepared, {
        "source": option(prepared, "source"), "heat": "0", "account": "I ask to keep the actual secret.",
    })
    tick(worker, gateway, 3)
    pass_windows(game)
    respond(scoped(game, PLAYER, "am_select"), PLAYER, "am_select", {"options": "secret", "account": "Keep this secret."})
    assert game.inspect(PLAYER, action["action_id"])["state"] == "complete"
    tick(worker, gateway, 5)
    assert CODE in suggestions(game, PLAYER)
    form = popup(scene, PLAYER, CODE)
    operator = next(value for value, _ in form[1]["fields"][0]["options"] if value == f"known:{filed['id']}")
    proposal = press(scene, PLAYER, form, {"operator": operator, "account": "I request physical circuit access."})
    observed = popup(scene, ADMIN, CODE_CONFIRM)
    assert observed[0]["id"] == f"{CODE_CONFIRM}:{proposal['id']}"
    with pytest.raises(WorkflowError):
        press(scene, PLAYER, observed, {"account": "I cannot make the original operator's choice."})
    press(scene, ADMIN, observed, {"account": "The original body has actual circuit access."})
    tick(worker, gateway, 3)
    assert CODE in suggestions(game, PLAYER)
    circuit = popup(scene, PLAYER, CODE)
    result = press(scene, PLAYER, circuit, {
        "source": option(circuit, "source"), "heat": "0", "account": "I complete the circuit procedure.",
    })
    tick(worker, gateway, 3)
    pass_windows(game)
    roll = game.inspect(PLAYER, result["action_id"])["receipt"]
    ledger.engine.dispose()
    reopened = GameService(ledger, dice=game.dice)
    choice = scoped(reopened, ADMIN, "am_code_options")
    with pytest.raises(WorkflowError):
        respond(choice, PLAYER, "am_code_options", {"options": ["identities"]})
    respond(choice, ADMIN, "am_code_options", {"options": ["identities", "backup"]})
    rewrite = scoped(reopened, ADMIN, "am_code_edit")
    original = next(
        field["key"][8:] for field in rewrite[1]["operations"][0]["fields"]
        if field["key"].startswith("rewrite:")
    )
    respond(rewrite, ADMIN, "am_code_edit", {
        "rewrite:" + original: "Self-directed", "memory_scope": "none", "account": "I perform the actual edit.",
    })
    saved = reopened.inspect(PLAYER, result["action_id"])
    assert saved["state"] == "complete" and saved["receipt"] == roll
    completed = m3_am_code.session(state(reopened), proposal["id"])
    assert original in completed.replacements and completed.backup and reopened.dice.calls == 2


def test_am_body_uses_the_original_prepared_vessel(ledger, tmp_path, monkeypatch):
    game, identity, _, action, worker, gateway, _ = code_rolled(
        ledger, tmp_path, monkeypatch, (4, 5), choose_identity=False,
    )
    original = game.inspect(PLAYER, action)["receipt"]
    selection = scoped(game, ADMIN, "am_code_options")
    respond(selection, ADMIN, "am_code_options", {"options": "body"})
    scene = SpecialistScene(game, 900)
    prepare = popup(scene, ADMIN, BODY_PREPARE)
    assert prepare[0]["id"] == f"{BODY_PREPARE}:{identity}"
    spec = {
        "vessel": "real-prepared-puppet", "label": "Actual prepared body",
        "source": "The original operator supplies empty local hardware.",
        "processing": "yes", "unoccupied": "yes", "medical": "fit",
        "assets": "Actuator | Installed in this vessel | intact | clear",
    }
    with pytest.raises(WorkflowError):
        press(scene, PLAYER, prepare, spec)
    press(scene, ADMIN, prepare, spec)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    assignment = scoped(fresh, ADMIN, "am_code_body")
    body = next(field for field in assignment[1]["operations"][0]["fields"] if field["key"] == "body")
    payload = {"body": body["options"][0][0], "account": "I connect and move the actual mind into it."}
    with pytest.raises(WorkflowError):
        respond(assignment, PLAYER, "am_code_body", payload)
    respond(assignment, ADMIN, "am_code_body", payload)
    tick(worker, gateway, 5)
    control = SpecialistScene(fresh, 900)
    swapping = m3_am_body.swaps(state(fresh))[0]
    assert swapping.new_vessel == spec["vessel"]
    reenter = popup(control, PLAYER, BODY_RETURN)
    assert reenter[0]["id"] == f"{BODY_RETURN}:{swapping.id}"
    press(control, PLAYER, reenter, {"confirm": "yes"})
    assert m3_am_body.swaps(state(fresh))[0].returned_event
    assert fresh.inspect(PLAYER, action)["receipt"] == original and game.dice.calls == 2


def test_am_branch_has_separate_handler_assignment_and_owner_takeover(ledger, tmp_path, monkeypatch):
    game, _, _, action, worker, gateway, _ = code_rolled(
        ledger, tmp_path, monkeypatch, (4, 5), choose_identity=False,
    )
    original = game.inspect(PLAYER, action)["receipt"]
    respond(scoped(game, ADMIN, "am_code_options"), ADMIN, "am_code_options", {"options": "branch"})
    scene = SpecialistScene(game, 900)
    press(scene, ADMIN, popup(scene, ADMIN, BODY_PREPARE), {
        "vessel": "actually-independent-puppet", "label": "Prepared branch body",
        "source": "The original operator provides an empty independent processor.",
        "processing": "yes", "unoccupied": "yes", "medical": "fit",
        "assets": "Branch actuator | Installed here | intact | clear",
    })
    choice = scoped(game, ADMIN, "am_code_branch")
    body = next(x for x in choice[1]["operations"][0]["fields"] if x["key"] == "body")
    respond(choice, ADMIN, "am_code_branch", {
        "body": body["options"][0][0], "account": "I form the independent branch.",
    })
    branch = m3_am_branch.branches(state(game))[0]
    assert branch.owner == PLAYER.user_id and branch.controller == ADMIN.user_id
    tick(worker, gateway, 5)
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    scene = SpecialistScene(fresh, 900)
    assign = popup(scene, ADMIN, BRANCH_ASSIGN)
    assert assign[0]["id"] == f"{BRANCH_ASSIGN}:{branch.id}"
    assignment = {"position": option(assign, "position"), "account": "I file the actual branch position."}
    with pytest.raises(WorkflowError):
        press(scene, PLAYER, assign, assignment)
    press(scene, ADMIN, assign, assignment)
    takeover = popup(scene, PLAYER, BRANCH_TAKEOVER)
    with pytest.raises(WorkflowError):
        press(scene, ADMIN, takeover, {"confirm": "yes"})
    saved = press(scene, PLAYER, takeover, {"confirm": "yes"}, key="one-branch-takeover")
    assert press(scene, PLAYER, takeover, {"confirm": "yes"}, key="one-branch-takeover") == saved
    after = m3_am_branch.branches(state(fresh))[0]
    assert after.id == branch.id and after.takeover_event
    assert fresh.inspect(PLAYER, action)["receipt"] == original and game.dice.calls == 2


def test_am_factory_reset_uses_the_original_fourth_limiter_and_handler(ledger, tmp_path, monkeypatch):
    game, identity, _, action, _, _, original, *_ = fourth_limiter(ledger, tmp_path, monkeypatch)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert len(m3_am.limiters(state(game), original)) == 4
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    scene = SpecialistScene(fresh, 900)
    reset = popup(scene, ADMIN, "am_reset")
    assert reset[0]["id"] == f"am_reset:{identity}"
    fields = {"job": "ex_pilot", "account": "The original Handler files the actual reassignment."}
    with pytest.raises(WorkflowError):
        press(scene, PLAYER, reset, fields)
    saved = press(scene, ADMIN, reset, fields, key="fourth-limiter-handler-response")
    assert press(scene, ADMIN, reset, fields, key="fourth-limiter-handler-response") == saved
    records = m3_am_reset.records(state(fresh))
    assert len(records) == 1 and records[0].archive
    assert fresh.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 4


def test_am_records_only_show_the_full_file_to_its_actual_operator(ledger, tmp_path, monkeypatch):
    game, _, _, action, _, _, document = records_rolled(ledger, tmp_path, monkeypatch, (4, 5))
    receipt = game.inspect(PLAYER, action)["receipt"]
    respond(scoped(game, ADMIN, "am_code_options"), ADMIN, "am_code_options", {"options": "records"})
    assigned = scoped(game, ADMIN, "am_code_records_question")
    assert DOCUMENT in assigned[1]["instruction_details"]
    with pytest.raises(StopIteration):
        scoped(game, PLAYER, "am_code_records_question")
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    respond(scoped(fresh, ADMIN, "am_code_records_question"), ADMIN, "am_code_records_question", {
        "account": QUESTION,
    })
    conclusion = scoped(fresh, ADMIN, "am_code_records_answer")
    with pytest.raises(WorkflowError):
        respond(conclusion, OTHER, "am_code_records_answer", {"account": ANSWER, "honest": "yes"})
    respond(conclusion, ADMIN, "am_code_records_answer", {"account": ANSWER, "honest": "yes"})
    assert RecordsService(fresh).document(ADMIN, document)["answer"] == ANSWER
    with pytest.raises(WorkflowError):
        RecordsService(fresh).document(PLAYER, document)
    assert fresh.inspect(PLAYER, action)["receipt"] == receipt and fresh.dice.calls == 2
