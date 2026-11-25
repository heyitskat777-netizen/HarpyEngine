"""Scene decision ownership for the Discord-bound private roster."""

from http import HTTPStatus
from time import monotonic, sleep

from test_artwork_activity import (
    activate_recruit,
    offline_activity,
    request,
    setup_action,
    sign_in,
)


def wait_for(read, predicate):
    deadline = monotonic() + 8
    while monotonic() < deadline:
        result = next((item for item in read() if predicate(item)), None)
        if result is not None:
            return result
        sleep(0.2)
    raise AssertionError("The engine did not assign the expected scene decision.")


def test_bound_handler_owns_scene_choices(tmp_path):
    with offline_activity(tmp_path, "--bound-roster", "--scene-tier", "mid") as config:
        first = sign_in(config, "invited")
        second = sign_in(config, "other")
        handler = sign_in(config, "handler")

        def current(token):
            return request(config, "/api/player-setup", token)

        setup_action(config, second, "profile", {"revision": 0, "callsign": "PEER"})
        activate_recruit(config, first, second)
        setup_action(config, first, "enter-scene", {"room": "relay"})

        pilot = current(first)
        plays = {play["id"]: play for play in pilot["active_scene"]["plays"]}
        sheet_plays = next(item["plays"] for item in pilot["cadre"] if item["own"])
        assert {play["id"] for play in sheet_plays} <= plays.keys()
        assert plays["go_for_the_core"]["destination"] == "battlefield"
        assert "handler_playbook" not in pilot
        book = current(handler)["handler_playbook"]
        assert {"brief", "punish", "expectation", "off_duty"} <= {
            play["id"] for play in book["plays"]
        }
        start = {"revision": book["revision"], "targets": [book["targets"][0]["ref"]]}
        setup_action(config, first, "handler-play-start", start, HTTPStatus.FORBIDDEN)
        saved_play = setup_action(config, handler, "handler-play-start", start)
        reopened = next(
            task
            for task in current(handler)["handler_playbook"]["tasks"]
            if task["id"] == saved_play["id"]
        )
        assert reopened["state"] == "pending"
        effect = {
            "id": reopened["id"],
            "revision": reopened["revision"],
            "play": "brief",
            "account": "The station lost power at the west relay.",
            "detail": "",
            "stakes": "",
        }
        setup_action(config, first, "handler-play-submit", effect, HTTPStatus.FORBIDDEN)
        assert setup_action(config, handler, "handler-play-submit", effect)["state"] == "complete"
        assert current(handler)["handler_playbook"]["tasks"] == []
        for move, detail, stakes in (
            (
                "escalate",
                "The emergency grid is failing.",
                "The eastern gate will close.",
            ),
            (
                "expectation",
                "The relay must be repaired.",
                "Later patrols depend on it.",
            ),
        ):
            book = current(handler)["handler_playbook"]
            start = {
                "revision": book["revision"],
                "targets": [book["targets"][0]["ref"]],
            }
            saved = setup_action(config, handler, "handler-play-start", start)
            (task,) = current(handler)["handler_playbook"]["tasks"]
            assert task["id"] == saved["id"]
            receipt = setup_action(
                config,
                handler,
                "handler-play-submit",
                effect
                | {
                    "id": task["id"],
                    "revision": task["revision"],
                    "play": move,
                    "detail": detail,
                    "stakes": stakes,
                },
            )
            assert receipt["state"] == "complete"

        def pilot_keep():
            keep = current(first)["active_scene"]["keep"]
            assert all(choice["role"] == "pilot" for choice in keep["choices"])
            return keep

        def handler_choice(step, kind):
            return wait_for(
                lambda: current(handler)["handler_choices"],
                lambda card: card["step"] == step and card["choice"]["kind"] == kind,
            )

        def answer(token, step, choice, value, *, room="relay", status=HTTPStatus.OK):
            return setup_action(
                config,
                token,
                step,
                {
                    "room": room,
                    "id": choice["id"],
                    "role": choice["role"],
                    "revision": choice["revision"],
                    "answer": value,
                },
                status,
            )

        setup_action(
            config,
            first,
            "keep-start",
            {
                "room": "relay",
                "context": "The pilot keeps calm while the station loses power.",
                "confirmed": True,
                "character_revision": pilot_keep()["character_revision"],
            },
        )
        tag = handler_choice("keep-choice", "tag_window")
        assert tag["room"] == "relay" and tag["choice"]["role"] == "handler"
        passed = {"options": ["pass"]}
        answer(first, tag["step"], tag["choice"], passed, status=HTTPStatus.CONFLICT)
        answer(
            first,
            tag["step"],
            tag["choice"] | {"role": "pilot"},
            passed,
            status=HTTPStatus.CONFLICT,
        )
        answer(
            handler,
            tag["step"],
            tag["choice"],
            passed,
            room="unrelated-room",
            status=HTTPStatus.CONFLICT,
        )
        answer(handler, tag["step"], tag["choice"], passed)
        pilot_tag = wait_for(
            lambda: pilot_keep()["choices"],
            lambda choice: choice["kind"] == "tag_window",
        )
        answer(handler, "keep-choice", pilot_tag, passed, status=HTTPStatus.CONFLICT)
        answer(first, "keep-choice", pilot_tag, passed)
        traits = wait_for(
            lambda: pilot_keep()["choices"],
            lambda choice: choice["kind"] == "actor_keep",
        )
        answer(
            first,
            "keep-choice",
            traits,
            {"options": ["vicious", "tough"], "denied": ["desperate"]},
        )
        ruling = handler_choice("keep-choice", "handler_keep")
        transcript = request(config, "/api/rooms/relay/transcript", first)
        receipt = next(
            item for item in transcript["receipts"] if item["id"] == pilot_keep()["current"]["id"]
        )
        assert receipt["roll"]["faces"] == pilot_keep()["current"]["receipt"]["faces"]
        assert receipt["pending"] == []
        assert ruling["choice"]["id"] not in str(transcript)
        request(config, "/api/rooms/relay/transcript", second, status=HTTPStatus.FORBIDDEN)
        outcome = {"flag": True, "text": "Restore the station grid."}
        answer(first, ruling["step"], ruling["choice"], outcome, status=HTTPStatus.CONFLICT)
        answer(handler, ruling["step"], ruling["choice"], outcome)
        result = wait_for(
            lambda: [pilot_keep()["current"]], lambda play: play["state"] == "complete"
        )
        assert result["result"]["ruling"] == outcome["text"]
        saved = request(config, "/api/rooms/relay/transcript", first)["receipts"][0]
        assert saved["roll"] == receipt["roll"]
        assert saved["result"]["ruling"] == outcome["text"]
        assert current(handler)["handler_choices"] == []

        def sensors():
            state = current(first)["active_scene"]["options"]["check_sensors"]
            assert all(choice["role"] == "pilot" for choice in state["choices"])
            return state

        ready = wait_for(lambda: [sensors()], lambda play: play["can_start"])
        setup_action(
            config,
            first,
            "scene-start",
            {
                "room": "relay",
                "play": "check_sensors",
                "context": "Check the sensors after power is restored.",
                "confirmed": True,
                "character_revision": ready["character_revision"],
                "target": None,
            },
        )
        tag = handler_choice("scene-choice", "tag_window")
        answer(first, tag["step"], tag["choice"], passed, status=HTTPStatus.CONFLICT)
        answer(handler, tag["step"], tag["choice"], passed)
        pilot_tag = wait_for(
            lambda: sensors()["choices"], lambda choice: choice["kind"] == "tag_window"
        )
        answer(first, "scene-choice", pilot_tag, passed)
        questions = wait_for(
            lambda: sensors()["choices"],
            lambda choice: choice["kind"] == "actor_sensors",
        )
        field = questions["fields"][0]
        answer(
            first,
            "scene-choice",
            questions,
            {"options": [key for key, _ in field["options"][: field["maximum"]]]},
        )
        card = handler_choice("scene-choice", "handler_sensors")
        answers = {
            "fields": {
                field["key"].removeprefix("fields."): "Sensors report nominal readings."
                for field in card["choice"]["fields"]
            }
        }
        answer(first, card["step"], card["choice"], answers, status=HTTPStatus.CONFLICT)
        answer(handler, card["step"], card["choice"], answers)
        result = wait_for(lambda: [sensors()["current"]], lambda play: play["state"] == "complete")
        assert set(result["result"]["answers"].values()) == {"Sensors report nominal readings."}


def test_dialogue_joins_the_actual_scene_and_starts_beneath_there(tmp_path):
    with offline_activity(tmp_path, "--bound-roster", "--scene-tier", "mid") as config:
        pilot = sign_in(config, "invited")
        peer = sign_in(config, "other")
        setup_action(config, peer, "profile", {"revision": 0, "callsign": "PEER"})
        activate_recruit(config, pilot, peer)
        activate_recruit(config, peer, pilot, keep_callsign=True)
        for member, line in (
            (pilot, "I report to the relay."),
            (peer, "I answer in the relay."),
        ):
            receipt = setup_action(config, member, "room-post", {"target": "relay", "text": line})
            assert receipt["entry"]
            assert request(config, "/api/player-setup", member)["active_scene"]["id"] == "relay"
        transcript = request(config, "/api/rooms/relay/transcript", pilot)
        assert {row["body"] for row in transcript["entries"]} >= {
            "I report to the relay.",
            "I answer in the relay.",
        }
        scene = request(config, "/api/player-setup", pilot)["active_scene"]
        play = scene["options"]["put_someone_beneath_you"]
        assert play["can_start"] and play["targets"]
        result = setup_action(
            config,
            pilot,
            "scene-start",
            {
                "room": "relay",
                "play": "put_someone_beneath_you",
                "target": play["targets"][0]["id"],
                "context": "I confront the peer in the relay.",
                "confirmed": True,
                "heat": play["heat_options"][0],
                "character_revision": play["character_revision"],
            },
        )
        assert result["action_id"]
