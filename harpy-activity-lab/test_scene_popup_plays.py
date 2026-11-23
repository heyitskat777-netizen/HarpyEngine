"""Exercise the Play popups against the actual scene adapter and engine."""

from types import SimpleNamespace
from uuid import uuid4

import mission_lab  # noqa: F401
import pytest
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services import m3_mockingbird_plays
from girlframe.services.m2_game import GameService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from test_beneath_service import ready
from test_final_handler_workflows import bundled_registry  # noqa: F401
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from scene_beneath_work import SceneBeneathWork
from test_scene_beneath_followups import adapter, scene_work, submit

from campaign_inbox import pending_interactions
from ai_native_plays import ActivityNativePlays
from player_setup import PlayerSetup
from girlframe.services.m3_access import load_registry

ledger = ledger_fixture


def play_options(game, viewer, play):
    scene = game.scene_info(viewer, 900)
    return adapter(game).play_options(
        viewer,
        scene,
        game.sheet(viewer),
        state(game),
        bool(scene["lock"] and scene["lock"]["state"] != "released"),
        False,
        {},
    )[play]


def start(game, play, context, target=None, *, heat=None):
    return adapter(game).perform_scene(
        PLAYER,
        str(uuid4()),
        "scene-start",
        {
            "play": play,
            "target": target,
            "context": context,
            "confirmed": True,
            "character_revision": game.sheet(PLAYER)["revision"],
            **({"heat": heat} if heat is not None else {}),
        },
    )


@pytest.mark.parametrize("battlefield", [False, True], ids=["native", "battlefield"])
def test_exclusive_scene_still_guards_a_pending_source(ledger, battlefield):
    game, _, _ = ready(ledger)
    ordinary, exclusive = 901, 902
    for channel in (ordinary, exclusive):
        game.bind_scene(ADMIN, f"bind:{channel}", channel)
        game.join_scene(ADMIN, f"handler:{channel}", channel)
    activity = adapter(game)
    room_channels = {ordinary, exclusive} if battlefield else {ordinary}
    activity.has_channel = room_channels.__contains__
    activity.activity_cast_channels = (exclusive,) if battlefield else ()
    play = start(game, "dive_deep", "Follow the Void signal", heat=0)
    activity.for_channel(ordinary).enter(PLAYER, "enter-ordinary")

    with pytest.raises(WorkflowError, match="pending Play before leaving"):
        activity.for_channel(exclusive).enter(PLAYER, "enter-exclusive")

    assert game.scene_info(PLAYER, 900)["lock"]["action_id"] == play["action_id"]
    assert game.scene_info(PLAYER, ordinary)["joined"]
    assert not game.scene_info(PLAYER, exclusive)["joined"]


def test_dive_popup_uses_native_effect_and_individual_table_answers(ledger):
    game, worker, gateway = ready(ledger, (1, 1))
    assert play_options(game, PLAYER, "dive_deep")["can_start"]
    root = start(game, "dive_deep", "Follow the Void signal", heat=0)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    (card,) = adapter(game).handler_choices(ADMIN)
    assert card["root"] == root and card["choice"]["kind"] == "dive_select"
    ledger.engine.dispose()
    reopened = adapter(GameService(ledger))
    assert reopened.handler_choices(ADMIN) == [card]
    assert reopened.handler_choices(PLAYER) == []
    assert reopened.handler_choices(OTHER) == []
    with pytest.raises(WorkflowError):
        submit(
            adapter(game),
            PLAYER,
            card["choice"],
            {"options": ["erase_identity_and_table_question"], "text": "Wrong"},
        )
    submit(
        adapter(game),
        ADMIN,
        card["choice"],
        {"options": ["erase_identity_and_table_question"], "text": "Actual link"},
    )
    (effect,) = play_options(game, PLAYER, "dive_deep")["choices"]
    identity = effect["fields"][0]["options"][0][0]
    submit(
        adapter(game),
        PLAYER,
        effect,
        {"fields": {"identity": identity}, "text": "What waits below?"},
    )
    for viewer in (PLAYER, OTHER):
        (question,) = play_options(game, viewer, "dive_deep")["choices"]
        assert question["prompt"] == "What waits below?"
        submit(adapter(game), viewer, question, {"text": "An original answer."})
    (card,) = adapter(game).handler_choices(ADMIN)
    submit(adapter(game), ADMIN, card["choice"], {"text": "A Handler's answer."})
    reopened = play_options(GameService(ledger), PLAYER, "dive_deep")
    assert reopened["current"]["state"] == "complete"
    assert reopened["current"]["receipt"]["faces"] == [1, 1]
    assert game.dice.calls == 1


@pytest.mark.parametrize("faces", [(6, 6), (1, 2)])
def test_mockingbird_popup_uses_real_trigger_and_counterpart(
    ledger, monkeypatch, faces
):
    monkeypatch.setattr(
        m3_mockingbird_plays,
        "load_registry",
        lambda: SimpleNamespace(require_available=lambda _identity: None),
    )
    game, worker, gateway = ready(ledger, faces)
    play = "mockingbird_person"
    target = current_ref(state(game), OTHER.user_id).token
    assert target in {
        row["id"] for row in play_options(game, PLAYER, play)["counterparts"]
    }
    source = start(game, play, "Converse with that pilot", [target])
    (record,) = play_options(game, PLAYER, play)["sources"]
    assert record["id"] == source["id"]
    root = start(game, play, record["label"], record["id"], heat=0)["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    (selection,) = play_options(game, PLAYER, play)["choices"]
    submit(
        adapter(game),
        PLAYER,
        selection,
        {
            "options": ["words", "sentences", "eye_contact", "deception"]
            if faces == (6, 6)
            else []
        },
    )
    (tag,) = play_options(game, OTHER, play)["choices"]
    players = PlayerSetup(game.store, ADMIN, PLAYER, OTHER, bound_roster=True)
    players.enable_activity_records()
    missions = MissionService(game.store)
    notice = ("play", f"{tag['id']}:{tag['revision']}")
    assert notice in pending_interactions(players, missions, None, OTHER)
    assert notice not in pending_interactions(players, missions, None, PLAYER)
    with pytest.raises(WorkflowError):
        submit(adapter(game), PLAYER, tag, {"text": "Forged"})
    submit(adapter(game), OTHER, tag, {"text": "Frozen expression"})
    assert GameService(ledger).inspect(PLAYER, root)["state"] == "complete"
    assert state(game).sheets["2"].tags[-1].giver == OTHER.user_id
    assert play_options(game, OTHER, play)["current"]["id"] == root
    if faces == (1, 2):
        popup = SceneBeneathWork(game, lambda: {900: ("relay", "Relay operations")})
        assert popup.view(PLAYER)[0]["read_only"]
        (permission,) = popup.view(OTHER)
        assert permission["root"] == root
        with pytest.raises(WorkflowError):
            scene_work(popup, PLAYER, permission, {"allow": "yes"})
        scene_work(popup, OTHER, permission, {"allow": "yes"})
        (departure,) = popup.view(PLAYER)
        scene_work(popup, PLAYER, departure, {})
        assert not popup.view(OTHER)


def test_defeat_requires_an_engine_assignment(ledger):
    game, _, _ = ready(ledger)
    assert not play_options(game, PLAYER, "defeat")["can_start"]
    with pytest.raises(WorkflowError, match="pending Defeat"):
        start(game, "defeat", "Missing source", "arbitrary")


def test_scene_followthrough_requires_a_completed_flirt_and_its_assigned_owner(ledger):
    game, worker, gateway = ready(ledger, (4, 5))
    play = "flirt_followthrough"
    projection = ActivityNativePlays(
        SimpleNamespace(
            game=game, handler=ADMIN, scene_plays=adapter(game),
            play_registry=load_registry(),
            handler_rooms=lambda: {900: ("relay", "Relay operations")},
        ),
        None,
    )

    def available(viewer):
        with ledger.engine.connect() as c:
            actor = current_ref(state(game), viewer.user_id)
            return {item["id"]: item for item in projection(c, game.scene(c, 900), actor)}

    assert not play_options(game, PLAYER, play)["can_start"]
    assert play not in available(PLAYER)
    with pytest.raises(WorkflowError, match="assigned follow-through"):
        start(game, play, "An unassigned follow-through", "arbitrary")

    flirt = start(game, "flirt", "Take the next watch together.", str(OTHER.user_id))["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    assert not play_options(game, PLAYER, play)["can_start"]
    answer(game, OTHER, "target_flirt", text="Join the watch.")
    assert game.inspect(PLAYER, flirt)["state"] == "complete"
    tick(worker, gateway, 3)
    (assigned,) = play_options(game, PLAYER, play)["targets"]
    assert not play_options(game, OTHER, play)["can_start"]
    assert available(PLAYER)[play]["control"] == "flirt"
    assert play not in available(OTHER)

    child = start(game, play, "Report for the watch.", assigned["id"])["action_id"]
    tick(worker, gateway, 3)
    assert play_options(game, OTHER, play)["choices"][0]["kind"] == "followthrough_confirm"
    assert not play_options(game, PLAYER, play)["choices"]
    answer(game, OTHER, "followthrough_confirm", flag=True, text="They reported.")
    assert game.inspect(PLAYER, child)["state"] == "complete"


def test_receipt_names_waiting_owner_without_exposing_another_players_choice(ledger):
    game, worker, gateway = ready(ledger, (5, 6))
    root = start(game, "check_sensors", "Inspect the relay signal.")["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    plays = adapter(game)

    def receipt(viewer):
        return next(row for row in plays.receipts(viewer, {"900": "relay"}) if row["id"] == root)

    pilot = receipt(PLAYER)
    assert pilot["waiting_on"] == [game.sheet(PLAYER)["callsign"]]
    assert pilot["pending"][0]["kind"] == "actor_sensors"
    assert receipt(OTHER)["pending"] == []
    answer(game, PLAYER, "actor_sensors", options=(
        "foundation_destination", "foundation_avoid", "enemy_activity",
    ))
    next_receipt = receipt(PLAYER)
    assert next_receipt["waiting_on"] == ["Handler"]
    assert next_receipt["pending"] == []
    assert next_receipt["revision"] > pilot["revision"]
    assert next_receipt["roll"] == pilot["roll"]
    answer(game, ADMIN, "handler_sensors", fields={"a1":"North deck", "a2":"Service lift", "a3":"Scanning"})
    filed = receipt(PLAYER)
    assert filed["state"] == "complete" and filed["waiting_on"] == []
    assert filed["roll"]["faces"] == [5, 6]
