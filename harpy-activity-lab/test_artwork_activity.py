"""Exercise artwork selection through the isolated Activity HTTP adapter."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager
from http import HTTPStatus
from pathlib import Path
from threading import Timer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from discord_test_host import CONFIG


@contextmanager
def offline_activity(runtime, *server_options):
    # The same offline Discord host and engine fixtures, with all output in tmp_path.
    start = """
from pathlib import Path
import runpy
import shutil
import sys
import mission_lab

runtime = Path(sys.argv[1])
sdk = runtime / "discord-sdk" / "embedded-app.js"
sdk.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(mission_lab.RUNTIME / "discord-sdk" / sdk.name, sdk)
mission_lab.RUNTIME = runtime
sys.argv[:] = ["discord_test_host.py", "--campaign", "discord-offline-artwork", *sys.argv[2:]]
runpy.run_path("discord_test_host.py", run_name="__main__")
"""
    server = subprocess.Popen(
        [sys.executable, "-B", "-c", start, str(runtime), *server_options],
        cwd=Path(__file__).resolve().parent,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    startup_timer = Timer(40, server.kill)
    startup_timer.start()
    try:
        line = server.stdout.readline()
        startup_timer.cancel()
        if not line:
            _, error = server.communicate(timeout=5)
            raise RuntimeError(error.decode("utf-8", errors="replace"))
        yield json.loads(line)
    finally:
        startup_timer.cancel()
        try:
            server.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate()


def request(config, path, token=None, data=None, status=HTTPStatus.OK, *, key=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers.update(
            {
                "Origin": config["discord_activity_origin"],
                "Content-Type": "application/json",
                "Idempotency-Key": key if key is not None else str(uuid4()),
            }
        )
    payload = None if data is None else json.dumps(data).encode("utf-8")
    req = Request(config["origin"] + path, data=payload, headers=headers)
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        if status is None:
            return response.status, json.loads(body)
        assert response.status == status, (path, response.status, body[:200])
        if response.headers.get_content_type() == "image/webp":
            return body
        return json.loads(body)


def sign_in(config, role):
    challenge = request(config, "/api/discord/challenge", data={})
    response = request(
        config,
        "/api/discord/session",
        data={"nonce": challenge["nonce"], "code": role, "guild_id": CONFIG.guild_id},
    )
    assert response["discord_user_id"] == getattr(CONFIG, f"{role}_user_id")
    return response["session"]


def setup_action(config, token, action, data, status=HTTPStatus.OK):
    return request(config, f"/api/player-setup/{action}", token, data, status)


def activate_recruit(config, recruit, owner, *, keep_callsign=False):
    initial = request(config, "/api/player-setup", recruit)
    if not keep_callsign:
        setup_action(
            config,
            recruit,
            "profile",
            {"revision": initial["revision"], "callsign": "FALLOW"},
        )
    draft = request(config, "/api/player-setup", recruit)
    options = draft["options"]
    setup_action(
        config,
        recruit,
        "build",
        {
            "revision": draft["revision"],
            "character_revision": draft["character_revision"],
            "draft": {
                "frame_name": "Watchlight",
                "girl_appearance": "Grey visor",
                "frame_appearance": "White ceramic",
                "girl_assets": [
                    {"name": option, "description": "Synthetic test fixture"}
                    for option in options["girl_assets"][:2]
                ],
                "frame_assets": [
                    {"name": option, "description": "Synthetic test fixture"}
                    for option in options["frame_assets"][:2]
                ],
                "void_asset": options["girl_assets"][0],
                "npc_bonds": [{"slot": 0, "name": "Iris", "feelings": ""}],
            },
        },
    )
    setup = request(config, "/api/player-setup", recruit)
    incoming = next(
        (item for item in setup["bonds"] if item["incoming"] and item["state"] == "accepted"),
        None,
    )
    if incoming and setup.get("bond_setup"):
        setup_action(
            config,
            recruit,
            "select-bond",
            {
                "id": incoming["id"],
                "revision": setup["revision"],
                "character_revision": setup["character_revision"],
            },
        )
        review = request(config, "/api/player-setup", recruit)["review"]
        setup_action(
            config,
            recruit,
            "review",
            {"revision": review["revision"], "fingerprint": review["fingerprint"]},
        )
        setup_action(config, recruit, "activate", {"fingerprint": review["fingerprint"]})
        return
    selection = {}
    if setup.get("bond_setup"):
        target = request(config, "/api/player-setup", owner)["enrollment"]["owner_id"]
        bond_setup = setup["bond_setup"]
        match = next(row for row in bond_setup["targets"] if row["id"] == target)
        revisions = {
            "source_revision": bond_setup["source_revision"],
            "target_revision": match["revision"],
        }
        selection = {"target": target}
    else:
        revisions = setup["bond_target"]
    setup_action(
        config,
        recruit,
        "bond",
        {
            **selection,
            "source_revision": revisions["source_revision"],
            "target_revision": revisions["target_revision"],
            "prompt": 0,
            "context": "",
        },
    )
    bond = next(
        item for item in request(config, "/api/player-setup", owner)["bonds"] if item["incoming"]
    )
    setup_action(
        config,
        owner,
        "bond-decision",
        {"id": bond["id"], "revision": bond["revision"], "decision": "accept"},
    )
    review = request(config, "/api/player-setup", recruit)["review"]
    setup_action(
        config,
        recruit,
        "review",
        {"revision": review["revision"], "fingerprint": review["fingerprint"]},
    )
    setup_action(config, recruit, "activate", {"fingerprint": review["fingerprint"]})


def test_artwork_uses_session_ownership_and_persists(tmp_path):
    catalog_path = "/api/artwork/catalog"
    scene_art = "scene-empty-hangar"
    pilot_art = "pilot-mockingbird"
    frame_art = "frame-janus"
    with offline_activity(tmp_path) as config:
        request(config, catalog_path, status=HTTPStatus.UNAUTHORIZED)
        request(config, f"/api/artwork/{scene_art}", status=HTTPStatus.UNAUTHORIZED)
        owner = sign_in(config, "invited")
        recruit = sign_in(config, "other")
        activate_recruit(config, recruit, owner)
        catalog = request(config, catalog_path, owner)
        assert len(catalog) == len({entry["id"] for entry in catalog}) == 48
        assert {entry["kind"] for entry in catalog} == {"scene", "pilot", "frame"}
        image = request(config, f"/api/artwork/{scene_art}", owner)
        assert image[:4] == b"RIFF" and image[8:12] == b"WEBP"
        request(config, "/api/artwork/missing", owner, status=HTTPStatus.NOT_FOUND)

        room_id = setup_action(
            config,
            owner,
            "room-create",
            {"name": "Artwork fixture", "location": "hangar"},
        )["room"]

        def projection(token):
            state = request(config, "/api/player-setup", token)
            pilot = next(item for item in state["cadre"] if item["callsign"] == "SYNTH")
            room = next(item for item in state["directory"]["rooms"] if item["id"] == room_id)
            return pilot, room

        def select(token, kind, target, artwork, previous=None, status=HTTPStatus.OK):
            return setup_action(
                config,
                token,
                "artwork",
                {
                    "kind": kind,
                    "target": target,
                    "artwork": artwork,
                    "previous": previous,
                },
                status,
            )

        owner_id = projection(owner)[0]["id"]
        assert isinstance(owner_id, str)
        select(owner, "scene", room_id, scene_art)
        select(owner, "pilot", owner_id, pilot_art)
        select(owner, "frame", owner_id, frame_art)
        select(owner, "frame", owner_id, pilot_art, status=HTTPStatus.BAD_REQUEST)
        select(owner, "pilot", owner_id, None, status=HTTPStatus.CONFLICT)
        select(recruit, "pilot", owner_id, None, pilot_art, status=HTTPStatus.CONFLICT)
        select(recruit, "frame", owner_id, None, frame_art, status=HTTPStatus.CONFLICT)
        assert projection(recruit)[1].get("artwork") is None

        code = setup_action(config, owner, "invite-issue", {"target": room_id})["code"]
        setup_action(config, recruit, "invite-redeem", {"code": code})
        assert projection(recruit)[1]["artwork"] == scene_art
        select(recruit, "scene", room_id, None, scene_art, status=HTTPStatus.CONFLICT)

        reopened = sign_in(config, "invited")
        pilot, room = projection(reopened)
        assert room["artwork"] == scene_art
        assert pilot["artwork"] == pilot_art
        assert pilot["frame_artwork"] == frame_art
        select(reopened, "scene", room_id, None, scene_art)
        assert projection(owner)[1]["artwork"] is None


def test_scene_posts_use_the_authors_own_portrait(tmp_path):
    directory = tmp_path / "playtest-campaigns" / "discord-offline-artwork"
    directory.mkdir(parents=True)
    with closing(sqlite3.connect(directory / "activity-records.sqlite3")) as db, db:
        db.execute(
            """CREATE TABLE dialogue (
                   room TEXT, actor INTEGER, callsign TEXT, body TEXT,
                   request_key TEXT UNIQUE, created INTEGER
               )"""
        )

    with offline_activity(tmp_path) as config:
        pilot = sign_in(config, "invited")
        recruit = sign_in(config, "other")
        activate_recruit(config, recruit, pilot)
        room = setup_action(
            config,
            pilot,
            "room-create",
            {"name": "Portrait fixture", "location": "hangar"},
        )["room"]
        path = f"/api/rooms/{room}/transcript"
        request(config, path, recruit, status=HTTPStatus.FORBIDDEN)
        code = setup_action(config, pilot, "invite-issue", {"target": room})["code"]
        setup_action(config, recruit, "invite-redeem", {"code": code})

        setup_action(config, pilot, "room-post", {"target": room, "text": "New pilot post"})
        setup_action(config, recruit, "room-post", {"target": room, "text": "Recruit post"})
        with closing(sqlite3.connect(directory / "activity-records.sqlite3")) as db, db:
            authors = list(
                db.execute("SELECT actor, author_character FROM dialogue ORDER BY rowid")
            )
            assert len(authors) == 2 and all(character for _, character in authors)
            (pilot_actor, _), (recruit_actor, _) = authors
            db.executemany(
                """INSERT INTO dialogue (room, actor, callsign, body, request_key, created)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                [
                    (
                        room,
                        pilot_actor,
                        "SYNTH",
                        "Matching legacy post",
                        "old-pilot",
                    ),
                    (
                        room,
                        recruit_actor,
                        "SYNTH",
                        "Unmatched legacy post",
                        "old-recruit",
                    ),
                ],
            )

        pilot_id = next(
            item["id"]
            for item in request(config, "/api/player-setup", pilot)["cadre"]
            if item["callsign"] == "SYNTH"
        )
        setup_action(
            config,
            pilot,
            "artwork",
            {
                "kind": "pilot",
                "target": pilot_id,
                "artwork": "pilot-sorrow",
                "previous": None,
            },
        )
        reopened = sign_in(config, "other")
        entries = request(config, path, reopened)["entries"]
        assert {entry["body"]: entry["portrait"] for entry in entries} == {
            "New pilot post": "pilot-sorrow",
            "Recruit post": None,
            "Matching legacy post": "pilot-sorrow",
            "Unmatched legacy post": None,
        }
        assert all(
            set(entry) == {"id", "callsign", "body", "created", "portrait"} for entry in entries
        )
