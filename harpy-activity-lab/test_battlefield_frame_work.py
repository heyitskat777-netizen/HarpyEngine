"""Exercise the Activity forms against native source records."""

from uuid import uuid4

import mission_lab  # noqa: F401
import pytest
from battlefield import Battlefield
from battlefield_frame_work import BattlefieldFrameWork
from owned_followups import OwnedFollowups
from play_continuations import PlayContinuations
from scene_beneath_work import SceneBeneathWork
from test_consume import (
    _elective_partake,
    acquire,
    asset,
    cockpit,
)
from test_consume import (
    ready as consume_ready,
)
from test_final_handler_workflows import bundled_registry  # noqa: F401
from test_frame_control import exposed_core
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_wyvern import free_chat, roll
from test_wyvern import ready as wyvern_ready

from girlframe.services.m2_game import GameService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def find(work, viewer, action):
    return next(x for x in work.view(viewer) if x["action"] == action)


def perform(work, viewer, card, op, values, key=None):
    data = {k: card[k] for k in ("id", "revision", "action")}
    if "game_revision" in card:
        data["game_revision"] = card["game_revision"]
    return work.perform(
        viewer,
        key or str(uuid4()),
        data
        | {
            "answer": {"operation": op, "values": values},
        },
    )


def test_janus_contact_reopens_with_original_judge_and_unplug_owner(ledger, tmp_path, monkeypatch):
    game, _, _ = exposed_core(ledger, tmp_path, monkeypatch, caster_mode="inside_frame")
    work = BattlefieldFrameWork(game, 900)
    start = find(work, PLAYER, "janus_start")
    token = start["operations"][0]["fields"][0]["options"][0][0]
    request = perform(
        work,
        PLAYER,
        start,
        "connect",
        {
            "target": token,
            "account": "I make contact using the reviewed cockpit spinal port.",
        },
    )
    assert request["phase"] == "review"
    resumed = BattlefieldFrameWork(GameService(ledger), 900)
    review = find(resumed, ADMIN, "janus_connection")
    assert review["id"] == request["id"]
    assert not find(resumed, OTHER, "janus_connection")["operations"]
    with pytest.raises(WorkflowError):
        perform(
            resumed,
            OTHER,
            review,
            "decide",
            {"allowed": "yes", "account": "Wrong owner"},
        )
    accepted = {
        "allowed": "yes",
        "account": "I confirm the original port and performed connection.",
    }
    key = str(uuid4())
    receipt = perform(resumed, ADMIN, review, "decide", accepted, key=key)
    assert perform(resumed, ADMIN, review, "decide", accepted, key=key) == receipt
    assert state(game).neural_connections[-1].phase == "connected"
    unplug = find(resumed, PLAYER, "janus_connection")
    assert unplug["operations"][0]["id"] == "unplug"
    assert not BattlefieldFrameWork(game, 901).view(ADMIN)
    perform(resumed, PLAYER, unplug, "unplug", {"account": "I remove my jack."})
    assert state(game).neural_connections[-1].phase == "unplugged"


def test_janus_optional_contact_requires_target_before_judge(ledger, tmp_path, monkeypatch):
    from test_frame_control import place_original
    from test_janus_core_service import cast_core
    from test_janus_requisitions import training

    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_janus_requisitions import UNIVERSAL

    service, game, core = training(ledger, tmp_path, monkeypatch, rule=UNIVERSAL)
    cast_core(service, game, core)
    caster, battery = (current_ref(state(game), viewer.user_id) for viewer in (PLAYER, OTHER))
    for actor in (caster, battery):
        place_original(game, actor, mode="outside_frame")
    work = BattlefieldFrameWork(game, 900)
    start = find(work, PLAYER, "janus_start")
    options = dict(start["operations"][0]["fields"][0]["options"])
    assert battery.token in options
    result = perform(
        work,
        PLAYER,
        start,
        "connect",
        {
            "target": battery.token,
            "account": "I reach the original exposed contact point.",
        },
    )
    assert result["phase"] == "target"
    target = find(work, OTHER, "janus_connection")
    assert not find(work, ADMIN, "janus_connection")["operations"]
    approval = {"allowed": "yes", "account": "I confirm the contact."}
    with pytest.raises(WorkflowError):
        perform(work, ADMIN, target, "decide", approval)
    perform(work, OTHER, target, "decide", approval)
    review = find(BattlefieldFrameWork(GameService(ledger), 900), ADMIN, "janus_connection")
    assert review["id"] == result["id"]
    perform(
        work,
        ADMIN,
        review,
        "decide",
        {"allowed": "yes", "account": "I confirm actual reach and access."},
    )
    assert state(game).neural_connections[-1].phase == "connected"


def test_consume_repair_runs_in_original_dive_popup_and_saves_once(ledger, tmp_path, monkeypatch):
    from girlframe.engine.m3_consume import PARTAKE

    game, worker, gateway, controls = consume_ready(ledger, tmp_path, monkeypatch)
    acquire(controls, PARTAKE)
    girl, frame = asset(game, 2), asset(game, 2, "frame")
    with ledger.transaction() as c:
        canonical = state(game)
        next(x for x in canonical.sheets["2"].assets if x.id == frame).damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_frame_damage", canonical)
    cockpit(game, "pilot")
    root, _ = _elective_partake(game, worker, gateway)
    original = game.inspect(PLAYER, root)["receipt"]

    def rooms():
        return {900: ("relay", "Relay")}

    resumed = GameService(ledger)
    continuations = OwnedFollowups(resumed, rooms)
    scene = SceneBeneathWork(resumed, rooms, continuations)
    (card,) = [
        x
        for x in scene.view(PLAYER, continuations.view(PLAYER))
        if x["action"] == "consume_partake"
    ]
    assert card["root"] == root
    assert not [
        x for x in PlayContinuations(resumed).view(OTHER) if x["action"] == "consume_partake"
    ]
    values = {
        "girl_asset": girl,
        "frame_1": frame,
        "account": "I grow back the damaged component.",
    }
    payload = {k: card[k] for k in ("id", "revision", "action", "root")} | {
        "answer": {"operation": "regrow", "values": values},
    }
    with pytest.raises(WorkflowError):
        scene.perform(OTHER, str(uuid4()), payload)
    key = str(uuid4())
    receipt = scene.perform(PLAYER, key, payload)
    assert scene.perform(PLAYER, key, payload) == receipt
    assert not next(x for x in state(resumed).sheets["2"].assets if x.id == frame).damaged
    assert next(x for x in state(resumed).sheets["2"].assets if x.id == girl).damaged
    assert resumed.inspect(PLAYER, root)["receipt"] == original


def test_wyvern_roused_pin_uses_engine_targets_and_only_pinner_can_release(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, _ = wyvern_ready(ledger, tmp_path, monkeypatch)
    roll(game, worker, gateway)
    free_chat(worker, gateway)
    work = BattlefieldFrameWork(game, 900)
    use = find(work, PLAYER, "wyvern_use")
    option = next(
        token
        for token, label in use["operations"][0]["fields"][0]["options"]
        if label.startswith("Pin ")
    )
    key = str(uuid4())
    receipt = perform(work, PLAYER, use, "use", {"use": option}, key=key)
    assert perform(work, PLAYER, use, "use", {"use": option}, key=key) == receipt
    resumed = BattlefieldFrameWork(GameService(ledger), 900)
    releases = find(resumed, PLAYER, "wyvern_source")
    counter = find(resumed, OTHER, "wyvern_source")
    assert releases["id"] == counter["id"]
    assert [item["id"] for item in counter["operations"]] == ["counter"]
    assert [item["id"] for item in releases["operations"]] == ["release"]
    with pytest.raises(WorkflowError):
        perform(resumed, OTHER, releases, "release", {"account": "I am not the pinner."})
    response = perform(
        resumed,
        PLAYER,
        releases,
        "release",
        {"account": "I lift the Frame and release them."},
    )
    assert response["id"] == releases["id"]
    assert not [x for x in resumed.view(OTHER) if x["action"] == "wyvern_source"]


def test_wyvern_crushing_bulk_offers_only_assessed_scene_vehicle(ledger, tmp_path, monkeypatch):
    from test_wyvern import buy

    from girlframe.engine import m3_vehicles, m3_wyvern
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.m3_vehicles import VehicleService

    game, worker, gateway, source = wyvern_ready(ledger, tmp_path, monkeypatch)
    buy(source, m3_wyvern.CRUSH)
    truck = VehicleService(game).assess(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        "Empty truck",
        "An actual ordinary vehicle at the Wyvern's position.",
        (0, 0),
        "empty",
    )
    action = roll(
        game,
        worker,
        gateway,
        play="engage",
        target=current_ref(state(game), 3),
        faces=(6, 6),
    )
    activity = Battlefield(MissionService(ledger), ADMIN, PLAYER, OTHER, shared=True)
    activity.game = game
    (choice,) = [
        row
        for row in activity.choices(action, PLAYER, str(PLAYER.user_id))
        if row["kind"] == "engage_maneuvers"
    ]
    fields = choice["fields"]
    assert {"encircle", "crush_small"} <= set(fields["maneuvers"])
    assert [x["id"] for x in fields["wyvern_vehicles"]] == [truck["id"]]
    assets = [x["id"] for x in fields["assets"]]
    payload = {
        "role": "pilot",
        "id": choice["id"],
        "revision": choice["revision"],
        "answer": {
            "options": ["crush_small", "encircle", "cover"],
            "fields": {
                "crush_small": assets[0],
                "encircle": assets[1],
                "cover": assets[2],
                "wyvern_vehicle": truck["id"],
            },
            "denied": [assets[0]],
            "text": "I crush the empty truck and encircle the foe.",
        },
    }
    original = game.inspect(PLAYER, action)["receipt"]
    with pytest.raises(WorkflowError):
        activity.respond(OTHER, str(uuid4()), payload)
    activity.respond(PLAYER, str(uuid4()), payload)
    reopened = GameService(ledger)
    vehicle = next(x for x in m3_vehicles.vehicles(state(reopened)) if x.id == truck["id"])
    assert vehicle.destroyed_event and vehicle.source_action == action
    assert reopened.inspect(PLAYER, action)["receipt"] == original


def test_wyvern_too_big_replacement_keeps_incoming_receipt(ledger, tmp_path, monkeypatch):
    from test_m2_game import answer, tick

    from girlframe.engine.m2 import ChoiceAnswer, PlayInput

    game, worker, gateway, _ = wyvern_ready(ledger, tmp_path, monkeypatch)
    roll(game, worker, gateway)
    free_chat(worker, gateway)
    game.dice.faces = (3, 4)
    unmarked = next(
        x.id for x in state(game).sheets["3"].identities if not x.marked and not x.protected
    )
    incoming = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="flirt",
            target=2,
            heat=1,
            identity=unmarked,
            gain=1,
            context="I Flirt over the open cockpit channel.",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(OTHER, incoming)["state"] != "tag_window":
        game.roll(OTHER, str(uuid4()), incoming)
    source_receipt = game.inspect(OTHER, incoming)["receipt"]
    paid_heat = state(game).sheets["3"].heat
    work = BattlefieldFrameWork(game, 900)
    roused = next(
        row
        for row in work.view(PLAYER, proactive=False, busy=True)
        if row["action"] == "wyvern_use"
    )
    ((effect, _),) = roused["operations"][0]["fields"][0]["options"]
    perform(work, PLAYER, roused, "use", {"use": effect})
    response = find(work, OTHER, "wyvern_source")
    values = {
        "play": "keep_your_head",
        "heat": "0",
        "account": "I keep my head through the withdrawal.",
    }
    with pytest.raises(WorkflowError):
        perform(work, PLAYER, response, "counter", values)
    replacement = perform(work, OTHER, response, "counter", values)["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(OTHER, replacement)["state"] != "tag_window":
        resume = find(work, OTHER, "wyvern_source")
        perform(work, OTHER, resume, "roll:" + replacement, {})
    for viewer in (PLAYER, OTHER, ADMIN):
        choice = next(
            x
            for x in game.choices(viewer)
            if x["kind"] == "tag_window" and x["action_id"] == replacement
        )
        game.respond(
            viewer,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(options=("pass",)),
        )
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(OTHER)):
        answer(game, OTHER, "mockingbird_risk")
    activity = Battlefield(MissionService(ledger), ADMIN, PLAYER, OTHER, shared=True, private=True)
    activity.game = game
    response = next(
        row
        for row in activity.choices(replacement, OTHER, str(OTHER.user_id))
        if row["kind"] == "actor_keep"
    )
    activity.respond(
        OTHER,
        str(uuid4()),
        {
            "role": "pilot",
            "id": response["id"],
            "revision": response["revision"],
            "answer": {"options": ["tough"]},
        },
    )
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The different course resolves the danger.",
    )
    reopened = GameService(ledger)
    assert reopened.inspect(OTHER, replacement)["state"] == "complete"
    assert reopened.inspect(OTHER, incoming)["state"] == "complete"
    assert reopened.inspect(OTHER, incoming)["receipt"] == source_receipt
    assert state(reopened).sheets["3"].heat == paid_heat


def test_crushing_bulk_sprite_interception_is_owned_and_preserves_original_roll(
    ledger, tmp_path, monkeypatch
):
    from test_enforcement_initiative import cast_target
    from test_m2_game import answer
    from test_world import gorgon
    from test_wyvern import buy
    from test_wyvern_combat import actual_asset

    from girlframe.engine import m3_wyvern
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world import introduce_gorgon

    game, worker, gateway, controls = wyvern_ready(ledger, tmp_path, monkeypatch)
    buy(controls, m3_wyvern.CRUSH)
    with ledger.transaction() as c:
        saved = state(game)
        leader = saved.world.gorgons[0]
        for name in ("crush-target", "interceptor"):
            saved.world = introduce_gorgon(
                saved.world,
                gorgon(
                    "sprite",
                    name,
                    revealed=True,
                    follows=leader.id,
                    types=leader.types,
                ),
            ).world
        game.event(c, ADMIN.user_id, str(uuid4()), "synthetic.test_sprite_bodies", saved)
    target = ActorRef(kind="gorgon", entity="crush-target")
    cast_target(game, target)
    used = actual_asset(game, current_ref(state(game), PLAYER.user_id))
    action = roll(game, worker, gateway, play="engage", target=target, faces=(1, 1))
    original = game.inspect(PLAYER, action)["receipt"]
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("crush_small",),
        fields={"crush_small": used},
        denied=(used,),
        text="The Frame crushes the original Sprite body.",
    )
    resumed = BattlefieldFrameWork(GameService(ledger), 900)
    choice = find(resumed, ADMIN, "battle_sprite_intercept")
    options = choice["operations"][0]["fields"][0]["options"]
    assert options[0][0] == "pass" and len(options) > 1
    assert not any(x["action"] == "battle_sprite_intercept" for x in resumed.view(PLAYER))
    values = {"target": "pass", "account": "The nearby Sprite declines."}
    with pytest.raises(WorkflowError):
        perform(resumed, PLAYER, choice, "intercept", values)
    key = str(uuid4())
    receipt = perform(resumed, ADMIN, choice, "intercept", values, key)
    assert perform(resumed, ADMIN, choice, "intercept", values, key) == receipt
    assert game.inspect(PLAYER, action)["receipt"] == original
    assert game.inspect(PLAYER, action)["state"] == "complete"
