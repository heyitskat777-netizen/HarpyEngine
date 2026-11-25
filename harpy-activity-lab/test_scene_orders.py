"""Verify Activity routing against saved direct and source-owned HarpyEngine orders."""

import json
from uuid import uuid4

import mission_lab

# isort: split
import pytest
from scene_orders import SceneOrders
from scene_plays import ScenePlays
from test_alpha_brutalize import guard_rolled
from test_harpy_actor_plays import ready as harpy_ready
from test_identity_specialists import suggestions
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, state, tick
from test_mission_service import service

from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_alpha import conditions
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture
ROOM = ("orders-room", "Relay orders")


def issue(service, viewer, code, values, key=None):
    card = service.view(viewer, ROOM)[0]
    assert any(form["id"] == code for form in card["operations"])
    return service.perform(
        viewer,
        key or str(uuid4()),
        card | {"answer": {"operation": code, "values": values}},
    )


def selected(service, viewer, code):
    card = service.view(viewer, ROOM)[0]
    operation = next(x for x in card["operations"] if x["id"] == code)
    return operation["fields"][0]["options"][0][0]


def decision(scene, actor, kind):
    choice = next(x for x in scene.game.choices(actor) if x["kind"] == kind)
    return scene.choice_card(actor, "handler" if actor == ADMIN else "pilot", choice)


def respond(scene, actor, card, result, key=None):
    return scene.perform_scene(
        actor,
        key or str(uuid4()),
        "scene-choice",
        {k: card[k] for k in ("id", "revision", "role")} | {"answer": result},
    )


def test_handler_issues_ranked_order_only_original_pilot_can_answer(ledger, monkeypatch):
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules/registry.json"))
    _, game = service(ledger)
    mission_lab.enable_private_subsystems(game)
    from test_m2_game import Gateway

    from girlframe.delivery.m2_worker import GameWorker

    actor_orders = SceneOrders(game, 900)
    direct_card = actor_orders.view(ADMIN, ROOM)[0]
    request = direct_card | {
        "answer": {
            "operation": "direct",
            "values": {
                "target": str(PLAYER.user_id),
                "instruction": "Record the relay readings.",
            },
        }
    }
    with pytest.raises(WorkflowError, match="STALE_ORDER"):
        actor_orders.perform(ADMIN, "old-order", request | {"revision": 0})
    with pytest.raises(WorkflowError):
        actor_orders.perform(OTHER, "rank-spoof", request)
    saved = actor_orders.perform(ADMIN, "issue-order", request)
    assert actor_orders.perform(ADMIN, "issue-order", request) == saved
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 4)
    scene = ScenePlays(GameService(ledger), 900, ADMIN, PLAYER, OTHER, handler_proxy=False)
    assert suggestions(game, PLAYER)["receive_orders"]["control"] == "receive_orders"
    assert "receive_orders" not in suggestions(game, OTHER)
    assert "disobey_orders" not in suggestions(game, PLAYER)
    card = decision(scene, PLAYER, "order_response")
    assert card["prompt"] == "Record the relay readings."
    with pytest.raises(WorkflowError):
        respond(scene, OTHER, card, {"options": ["obedient"]})
    with pytest.raises(WorkflowError):
        respond(scene.for_channel(901), PLAYER, card, {"options": ["obedient"]})
    result = respond(scene, PLAYER, card, {"options": ["obedient"]}, key="actual-pilot-choice")
    assert (
        respond(scene, PLAYER, card, {"options": ["obedient"]}, key="actual-pilot-choice") == result
    )
    assert game.inspect(PLAYER, saved["action_id"])["result"]["response"] == "obedient"


def test_actual_harpy_question_goes_to_its_adjudicator_without_a_roll(ledger, monkeypatch):
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules/registry.json"))
    _, game, _, actor = harpy_ready(ledger)
    from test_m2_game import Gateway

    from girlframe.delivery.m2_worker import GameWorker

    orders = SceneOrders(game, 900)
    ref = selected(orders, PLAYER, "role_sensors")
    assert json.loads(ref)["actor"] == actor.model_dump(mode="json")
    question = "Is the old antenna listening?"
    saved = issue(orders, PLAYER, "role_sensors", {"role": ref, "context": question})
    tick(GameWorker(game), Gateway(), 3)
    scene = ScenePlays(GameService(ledger), 900, ADMIN, PLAYER, OTHER, handler_proxy=False)
    assigned = next(x for x in scene.handler_choices(ADMIN) if x["root"] == saved["action_id"])
    card = assigned["choice"]
    assert card["kind"] == "harpy_sensor_answers" and card["prompt"] == question
    with pytest.raises(WorkflowError):
        respond(scene, OTHER, card, {"flag": True, "text": "A forged answer"})
    respond(scene, ADMIN, card, {"flag": True, "text": "Only on the emergency band."})
    result = scene.game.inspect(PLAYER, saved["action_id"])
    assert result["state"] == "complete" and result["receipt"] is None
    assert result["result"]["answers"] == "Only on the emergency band." and not game.dice.calls


@pytest.mark.parametrize("ranked", [False, True])
def test_actual_source_and_handler_ruling_stay_on_the_original_order(
    ledger,
    tmp_path,
    monkeypatch,
    ranked,
):
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules/registry.json"))
    game, guard, npc, alpha, worker, gateway = guard_rolled(ledger, tmp_path, monkeypatch, (1, 1))
    answer(game, ADMIN, "alpha_low", options=("counter_broken",))
    pending = next(x for x in game.choices(ADMIN) if x["kind"] == "alpha_counter_play")
    data = guard.counter(ADMIN, alpha, pending["id"])
    guard.perform_counter(
        ADMIN,
        str(uuid4()),
        alpha,
        pending["id"],
        data["revision"],
        "interpose",
        "The original Guard steps in.",
    )
    answer(game, PLAYER, "alpha_npc_mercy", options=("spare",))
    tick(worker, gateway, 5)
    recipient = current_ref(state(game), PLAYER.user_id)
    assert conditions(state(game), recipient, npc)
    orders = SceneOrders(game, 900)
    kind = "ranked" if ranked else "npc"
    source = selected(orders, ADMIN, kind)
    if ranked:
        proposed = json.loads(source)
        assert proposed["issuer"]["kind"] == "handler"
        assert json.loads(selected(orders, ADMIN, "npc"))["actor"] == npc.model_dump(mode="json")
        forged = json.dumps(proposed | {"issuer": npc.model_dump(mode="json")})
        with pytest.raises(WorkflowError, match="original ranked superior"):
            issue(orders, ADMIN, kind, {"target": forged, "instruction": "Forged issuer."})
    started = issue(
        orders,
        ADMIN,
        kind,
        {
            "target" if ranked else "source": source,
            "instruction": "Stand down and return to the relay.",
        },
    )
    tick(worker, gateway, 4)
    scene = ScenePlays(game, 900, ADMIN, PLAYER, OTHER, handler_proxy=False)
    offered = decision(scene, PLAYER, "order_response")
    issuer = "Handler" if ranked else "Actual Guard"
    assert offered["prompt"] == f"{issuer}: Stand down and return to the relay."
    respond(scene, PLAYER, offered, {"options": ["disobey"]})
    assert suggestions(game, PLAYER)["disobey_orders"]["control"] == "receive_orders"
    assert "disobey_orders" not in suggestions(game, OTHER)
    refusal = decision(scene, PLAYER, "order_disobey")
    game.dice.faces = (4, 5)
    reading = {
        "context": "I refuse the actual Guard's order.",
        "character_revision": refusal["character_revision"],
        "heat": 0,
        "witnessed": True,
    }
    with pytest.raises(WorkflowError):
        respond(scene, OTHER, refusal, reading)
    child = respond(scene, PLAYER, refusal, reading, key="real-refusal")
    assert respond(scene, PLAYER, refusal, reading, key="real-refusal") == child
    tick(worker, gateway, 4)
    for viewer in (PLAYER, ADMIN, OTHER):
        if any(
            x["kind"] == "tag_window" and x["action_id"] == child["action_id"]
            for x in game.choices(viewer)
        ):
            respond(
                scene,
                viewer,
                decision(scene, viewer, "tag_window"),
                {"options": ["pass"]},
            )
    native = game.inspect(PLAYER, child["action_id"])["receipt"]
    pilot = decision(scene, PLAYER, "actor_disobey")
    respond(
        scene,
        PLAYER,
        pilot,
        {"options": ["tag_heat"], "text": "Insubordinate", "number": 1}
        if ranked
        else {"options": ["remove_broken"]},
    )
    reopened = ScenePlays(GameService(ledger), 900, ADMIN, PLAYER, OTHER, handler_proxy=False)
    owned = next(
        x for x in reopened.handler_choices(ADMIN) if x["choice"]["kind"] == "handler_disobey"
    )
    assert owned["root"] == started["action_id"]
    with pytest.raises(WorkflowError):
        respond(reopened, PLAYER, owned["choice"], {"flag": False})
    respond(reopened, ADMIN, owned["choice"], {"flag": False})
    assert reopened.game.inspect(PLAYER, child["action_id"])["receipt"] == native
    assert reopened.game.inspect(PLAYER, started["action_id"])["state"] == "complete"
    assert bool(conditions(state(game), recipient, npc)) == ranked
    assert game.dice.calls == 2
    tick(worker, gateway, 4)
    actor = selected(orders, ADMIN, "withdraw")
    cast = orders.view(ADMIN, ROOM)[0]
    request = cast | {"answer": {"operation": "withdraw", "values": {"actor": actor}}}
    with pytest.raises(WorkflowError):
        orders.perform(OTHER, "wrong-controller", request)
    orders.perform(ADMIN, "withdraw-original-npc", request)
    assert all(role["token"] != npc.token for role in orders.cast.view(ADMIN, 900)["roles"])
    issue(orders, ADMIN, "join", {"actor": selected(orders, ADMIN, "join")})
    reopened_orders = SceneOrders(GameService(ledger), 900)
    assert any(
        role["token"] == npc.token for role in reopened_orders.cast.view(ADMIN, 900)["roles"]
    )
