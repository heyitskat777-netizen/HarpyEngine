"""Exercise recovered decisions through the Activity's synthetic Discord API."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from http import HTTPStatus
from http.cookiejar import CookieJar
from threading import Barrier
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

from campaign_inbox import InboxNotices
from player_setup import OWNER_CREATION_FIELDS
from test_bot_enrollment import selected
from test_campaign_role_access import CONFIG, request, role_activity
from test_handler_pilot_view import login

PILOT = "666666666666666666"
PRIVATE_BOND = "Synthetic countersignature context."
PRIVATE_OFFER = "Synthetic relay inventory"


def relay(tmp_path, now, **state):
    runtime = tmp_path / "role-runtime"
    runtime.mkdir(exist_ok=True)
    pending = runtime / "relay.pending"
    pending.write_text(json.dumps({"now": now, **state}), encoding="utf-8")
    pending.replace(runtime / "relay.json")


def race(*operations):
    start = Barrier(len(operations))

    def run(operation):
        start.wait(timeout=5)
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(run, operations))


def prepare_bond(host, first, second, query):
    path = "/api/player-setup"
    for token, callsign in ((first, "RELAY ZERO"), (second, "RELAY ONE")):
        state = request(host, path + query, token)
        request(
            host,
            path + "/profile" + query,
            token,
            {
                "revision": state["revision"],
                "callsign": callsign,
            },
        )
    draft = selected("MOCKINGBIRD", "JANUS").model_dump(mode="json")
    for token in (first, second):
        state = request(host, path + query, token)
        request(
            host,
            path + "/build" + query,
            token,
            {
                "revision": state["revision"],
                "character_revision": state["character_revision"],
                "draft": {
                    key: value for key, value in draft.items() if key in OWNER_CREATION_FIELDS
                },
            },
        )
    owner = request(host, path + query, first)["bond_setup"]
    target = next(row for row in owner["targets"] if row["id"] == CONFIG.invited_user_id)
    return request(
        host,
        path + "/bond" + query,
        first,
        {
            "target": target["id"],
            "source_revision": owner["source_revision"],
            "target_revision": target["revision"],
            "prompt": 0,
            "context": PRIVATE_BOND,
        },
    )


def activate(host, first, second, query, bond_id):
    path = "/api/player-setup"
    peer = request(host, path + query, second)
    request(
        host,
        path + "/select-bond" + query,
        second,
        {
            "id": bond_id,
            "revision": peer["revision"],
            "character_revision": peer["character_revision"],
        },
    )
    for token in (first, second):
        review = request(host, path + query, token)["review"]
        assert review["ready"]
        request(
            host,
            path + "/review" + query,
            token,
            {
                "revision": review["revision"],
                "fingerprint": review["fingerprint"],
            },
        )
        review = request(host, path + query, token)["review"]
        request(host, path + "/activate" + query, token, {"fingerprint": review["fingerprint"]})


def test_pending_bond_access_retry_and_restart(tmp_path):
    relay(tmp_path, 1000)
    path = "/api/player-setup"
    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        first, second, outside = [login(host, code) for code in ("role-pilot", "invited", "other")]
        campaign = request(host, "/api/campaigns", first)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        bond = prepare_bond(host, first, second, query)
        incoming = request(host, path + query, second)["bonds"][0]
        assert incoming["id"] == bond["id"] and incoming["state"] == "pending"
        accept = {"id": bond["id"], "revision": incoming["revision"], "decision": "accept"}
        withdraw = accept | {"decision": "withdraw"}
        request(host, path + "/bond-decision" + query, outside, accept, HTTPStatus.CONFLICT)
        request(host, path + "/bond-decision" + query, first, accept, HTTPStatus.CONFLICT)
        assert PRIVATE_BOND not in json.dumps(request(host, path + query, outside))

        # Advance the relay clock past the synthetic OAuth lease without sleeping.
        relay(tmp_path, 1600)
        expired = request(
            host, path + "/bond-decision" + query, second, accept, HTTPStatus.UNAUTHORIZED
        )
        assert expired["reauthenticate"] is True
        first = login(host, "role-pilot")
        assert request(host, path + query, first)["bonds"][0]["state"] == "pending"
        # Role and screening changes are evaluated at the next connection.
        for state in ({"pending": True}, {"revoked": True}):
            relay(tmp_path, 1621, **state)
            assert request(host, path + query, first)["bonds"][0]["state"] == "pending"
            request(host, path + "/bond-decision" + query, first, accept, HTTPStatus.CONFLICT)
            nonce = request(host, "/api/discord/challenge", data={})["nonce"]
            denied = request(
                host,
                "/api/discord/session",
                data={
                    "nonce": nonce,
                    "code": "role-pilot",
                    "guild_id": CONFIG.guild_id,
                },
                status=HTTPStatus.FORBIDDEN,
            )
            assert denied["reauthenticate"] is True
        relay(tmp_path, 2200, revoked=True)
        expired = request(
            host, path + "/bond-decision" + query, first, withdraw, HTTPStatus.UNAUTHORIZED
        )
        assert expired["reauthenticate"] is True
        relay(tmp_path, 2201)
        first = login(host, "role-pilot")
    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        request(host, path + query, first, status=HTTPStatus.UNAUTHORIZED)
        first, second, outside = [login(host, code) for code in ("role-pilot", "invited", "other")]
        assert request(host, path + query, first)["bonds"][0]["state"] == "pending"
        assert request(host, path + query, second)["bonds"] == [incoming]
        assert PRIVATE_BOND not in json.dumps(request(host, path + query, outside))

        def answer():
            return request(host, path + "/bond-decision" + query, second, accept, key="bond-replay")

        one, two = race(answer, answer)
        assert one == two
        request(
            host,
            path + "/bond-decision" + query,
            second,
            accept | {"decision": "decline"},
            HTTPStatus.CONFLICT,
        )
        assert request(host, path + query, first)["bonds"][0]["state"] == "accepted"
    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        second, outside = [login(host, code) for code in ("invited", "other")]
        assert request(host, path + query, second)["bonds"][0]["state"] == "accepted"
        assert answer() == one
        assert PRIVATE_BOND not in json.dumps(request(host, path + query, outside))


def test_declined_bond_is_filed_privately_after_restart(tmp_path):
    relay(tmp_path, 1000)
    path = "/api/player-setup"
    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        first, second = [login(host, code) for code in ("role-pilot", "invited")]
        query = "?campaign=" + request(host, "/api/campaigns", first)["campaigns"][0]["id"]
        bond = prepare_bond(host, first, second, query)
        request(
            host,
            path + "/bond-decision" + query,
            second,
            {"id": bond["id"], "revision": bond["revision"], "decision": "decline"},
        )

    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        for code, incoming in (("role-pilot", False), ("invited", True)):
            state = request(host, path + query, login(host, code))
            assert not state["bonds"]
            (record,) = state["bond_history"]
            assert (record["id"], record["state"], record["context"], record["incoming"]) == (
                bond["id"], "declined", PRIVATE_BOND, incoming,
            )
        outsider = request(host, path + query, login(host, "other"))
        assert PRIVATE_BOND not in json.dumps(outsider)


def test_mission_decisions_are_private_and_revision_checked_across_restarts(tmp_path):
    relay(tmp_path, 1000)
    path = "/api/mission-offers"
    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        first, second = [login(host, code) for code in ("role-pilot", "invited")]
        campaign = request(host, "/api/campaigns", first)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        bond = prepare_bond(host, first, second, query)
        request(
            host,
            "/api/player-setup/bond-decision" + query,
            second,
            {
                "id": bond["id"],
                "revision": bond["revision"],
                "decision": "accept",
            },
        )
        activate(host, first, second, query, bond["id"])

    def respond(row, token, response, key, status=HTTPStatus.OK):
        return request(
            host,
            path + "/" + row["id"] + "/response" + query,
            token,
            {
                "expected_revision": row["revision"],
                "response": response,
            },
            status,
            key=key,
        )

    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        first, second, outside = [login(host, code) for code in ("role-pilot", "invited", "other")]
        saved = request(host, path + query, first)
        solo = next(row for row in saved["offers"] if row["objective"] == PRIVATE_OFFER)
        shared = next(row for row in saved["offers"] if row["id"] != solo["id"])
        assert solo["needs_response"] and solo["waiting_on"] == "viewer"
        assert PRIVATE_OFFER not in json.dumps(request(host, path + query, second))
        assert request(host, path + query, outside)["offers"] == []

        respond(solo, outside, "accept", "outsider", HTTPStatus.NOT_FOUND)
        respond(solo, second, "accept", "not-recipient", HTTPStatus.NOT_FOUND)

    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        first, second, outside = [login(host, code) for code in ("role-pilot", "invited", "other")]
        assert request(host, path + query, first) == saved

        # Opposite clicks with the same revision cannot both take effect.
        attempts = ("accept", "decline")
        results = race(
            lambda: respond(solo, first, attempts[0], "double-accept", None),
            lambda: respond(solo, first, attempts[1], "double-decline", None),
        )
        assert sorted(status for status, _ in results) == [200, 409]
        index = next(i for i, (status, _) in enumerate(results) if status == 200)
        winning_choice = attempts[index]
        winning_receipt = results[index][1]

        accepted = respond(shared, first, "accept", "shared-first")
        assert respond(shared, first, "accept", "shared-first") == accepted
        own = next(
            row for row in request(host, path + query, first)["offers"] if row["id"] == shared["id"]
        )
        assert own["waiting_on"] == "invitees"
        respond(shared, second, "decline", "shared-stale", HTTPStatus.CONFLICT)
        peer = request(host, path + query, second)["offers"][0]
        assert peer["needs_response"] and peer["response"] is None
        respond(peer, second, "decline", "shared-current")
        rows = request(host, path + query, first)["offers"]
        assert next(row for row in rows if row["id"] == shared["id"])["waiting_on"] == "dispatch"
        for row in rows:
            assert "responses" not in row and "offered_to" not in row

    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True) as host:
        first, second, outside = [login(host, code) for code in ("role-pilot", "invited", "other")]
        assert respond(solo, first, winning_choice, "double-" + winning_choice) == winning_receipt
        rows = {row["id"]: row for row in request(host, path + query, first)["offers"]}
        assert (
            rows[solo["id"]]["response"] == winning_choice
            and not rows[solo["id"]]["needs_response"]
        )
        assert rows[shared["id"]]["response"] == "accept"
        peer = request(host, path + query, second)["offers"]
        assert len(peer) == 1 and peer[0]["id"] == shared["id"] and peer[0]["response"] == "decline"
        assert request(host, path + query, outside)["offers"] == []


def test_scene_invite_is_private_and_joins_only_on_owner_acceptance(tmp_path):
    relay(tmp_path, 1000)
    path = "/api/player-setup"
    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True, inbox=True) as host:
        first, second, outsider = [login(host, code) for code in ("role-pilot", "invited", "other")]
        campaign = request(host, "/api/campaigns", first)["campaigns"][0]["id"]
        query = "?campaign=" + campaign
        bond = prepare_bond(host, first, second, query)
        request(
            host,
            path + "/bond-decision" + query,
            second,
            {
                "id": bond["id"],
                "revision": bond["revision"],
                "decision": "accept",
            },
        )
        activate(host, first, second, query, bond["id"])
        room = request(
            host,
            path + "/room-create" + query,
            first,
            {
                "name": "Rehearsal Annex",
                "location": "hangar",
            },
        )["room"]
        invite = {"room": room, "recipient": CONFIG.invited_user_id}
        issued = request(
            host, path + "/scene-invite" + query, first, invite, key="scene-invite-proof"
        )
        assert (
            request(host, path + "/scene-invite" + query, first, invite, key="scene-invite-proof")
            == issued
        )
        proof = "/api/dm-receipts/" + issued["dm_receipt"] + query
        delivery_log = "/api/dm-receipts" + query + "&view=delivery"
        request(host, proof, status=HTTPStatus.UNAUTHORIZED)
        request(host, delivery_log, status=HTTPStatus.UNAUTHORIZED)
        request(host, proof, second, status=HTTPStatus.NOT_FOUND)
        request(host, proof, outsider, status=HTTPStatus.NOT_FOUND)
        queued = {"name": "RELAY ONE", "online": False, "status": "queued"}
        assert request(host, proof, first) == {"recipients": [queued]}
        delivery = {
            "id": issued["dm_receipt"],
            "kind": "scene_invite",
            "record": issued["id"],
            "recipients": [queued],
        }
        assert request(host, delivery_log, first)["deliveries"][-1] == delivery
        assert request(host, delivery_log, second) == {"deliveries": []}
        assert request(host, delivery_log, outsider) == {"deliveries": []}
        outbox = (
            tmp_path
            / "role-runtime"
            / f"activity-inbox-notices-{CONFIG.client_id}-{CONFIG.guild_id}.sqlite3"
        )
        with closing(sqlite3.connect(outbox)) as db:
            (item,) = db.execute(
                "SELECT campaign, kind, record, recipient FROM notices WHERE kind = 'scene_invite'"
            ).fetchall()
            assert item[2:] == (issued["id"], CONFIG.invited_user_id)
        InboxNotices(outbox).finish(item, "sent")
        sent = queued | {"status": "sent"}
        assert request(host, proof, first) == {"recipients": [sent]}
        assert request(host, delivery_log, first)["deliveries"][-1] == delivery | {
            "recipients": [sent]
        }
        request(host, "/api/presence" + query, second)
        assert request(host, proof, first) == {"recipients": [sent | {"online": True}]}
        decision = {"id": issued["id"], "decision": "accept"}
        request(host, path + "/scene-invite-decision" + query, first, decision, HTTPStatus.CONFLICT)
        request(
            host, path + "/scene-invite-decision" + query, outsider, decision, HTTPStatus.CONFLICT
        )
        assert not request(host, path + query, first)["scene_invites"]
        assert not request(host, path + query, outsider).get("scene_invites")
        peer = request(host, path + query, second)
        assert peer["scene_invites"] == [
            {"id": issued["id"], "room": room, "name": "Rehearsal Annex"}
        ]
        assert not next(row for row in peer["directory"]["rooms"] if row["id"] == room)["joined"]

    with role_activity(tmp_path, PILOT, bot_handler=True, decisions=True, inbox=True) as host:
        first = login(host, "role-pilot")
        second = login(host, "invited")
        listed = request(host, "/api/dm-receipts" + query, first)["receipts"]
        assert listed[-1] == issued["dm_receipt"]
        assert request(host, "/api/dm-receipts" + query, second) == {"receipts": []}
        assert request(host, proof, first) == {"recipients": [sent]}
        assert request(host, delivery_log, first)["deliveries"][-1] == delivery | {
            "recipients": [sent]
        }
        assert request(host, path + query, second)["scene_invites"] == peer["scene_invites"]
        saved = request(host, path + "/scene-invite-decision" + query, second, decision)
        assert saved == {"room": room, "decision": "accept"}
        assert request(host, path + "/scene-invite-decision" + query, second, decision) == saved
        request(
            host,
            path + "/scene-invite-decision" + query,
            second,
            decision | {"decision": "decline"},
            HTTPStatus.CONFLICT,
        )
        peer = request(host, path + query, second)
        assert not peer["scene_invites"]
        assert next(row for row in peer["directory"]["rooms"] if row["id"] == room)["joined"]


def local_pilot(host, label):
    browser = build_opener(HTTPCookieProcessor(CookieJar()))
    with browser.open(host["pilots"][label], timeout=10):
        pass

    def read(step="", data=None, *, key=None, status=HTTPStatus.OK):
        headers = {
            "Origin": host["origin"],
            "Content-Type": "application/json",
            "Idempotency-Key": key or str(uuid4()),
        }
        body = None if data is None else json.dumps(data).encode("utf-8")
        request = Request(host["origin"] + "/api/player-setup" + step, body, headers)
        try:
            response = browser.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            assert response.status == status, result
            return result

    return read


def test_create_and_invite_without_discord_and_recover_after_restart(tmp_path):
    from mission_lab import OTHER

    with role_activity(tmp_path, local=True) as host:
        owner = local_pilot(host, "Invited pilot")
        peer = local_pilot(host, "Other pilot")
        invitee = next(
            row for row in owner()["scene_invite_targets"] if row["id"] == str(OTHER.user_id)
        )
        draft = {"name": "Local Annex", "location": "hangar", "recipients": [invitee["id"]]}
        key = "synthetic-room-file"
        receipt = owner("/room-create", draft, key=key)
        (invite,) = receipt["invitations"]
        assert invite["recipient"] == invitee["id"] and "dm_receipt" not in invite
        assert owner("/room-create", draft, key=key) == receipt
        owner("/room-create", draft | {"recipients": []}, key=key, status=HTTPStatus.CONFLICT)
        owner(
            "/room-create",
            draft | {"name": "Invalid Annex", "recipients": ["777777"]},
            status=HTTPStatus.CONFLICT,
        )
        assert "Invalid Annex" not in [row["name"] for row in owner()["directory"]["rooms"]]
        assert not owner()["scene_invites"]
        (pending,) = peer()["scene_invites"]
        assert pending["id"] == invite["id"]

    with role_activity(tmp_path, local=True) as host:
        owner = local_pilot(host, "Invited pilot")
        peer = local_pilot(host, "Other pilot")
        decision = {"id": invite["id"], "decision": "accept"}
        owner("/scene-invite-decision", decision, status=HTTPStatus.CONFLICT)
        assert peer()["scene_invites"] == [pending]
        assert peer("/scene-invite-decision", decision)["room"] == receipt["room"]
        assert next(row for row in peer()["directory"]["rooms"] if row["id"] == receipt["room"])[
            "joined"
        ]
        subsequent = owner("/room-create", {"name": "Second Annex", "location": "hangar"})
        invitation = owner(
            "/scene-invite", {"room": subsequent["room"], "recipient": invitee["id"]}
        )
        assert "dm_receipt" not in invitation
        assert peer()["scene_invites"][0]["id"] == invitation["id"]


def test_pending_plays_in_two_scenes_keep_independent_rolls_and_choices(tmp_path):
    rolls = ((5, 6), (6, 6))

    def keep(client, room):
        scene = client("?scene=" + room)["active_scene"]
        assert scene["id"] == room
        return scene["keep"]

    def start(client, room, status=HTTPStatus.OK):
        return client(
            "/keep-start",
            {
                "room": room,
                "confirmed": True,
                "context": "Hold position in this room.",
                "character_revision": keep(client, room)["character_revision"],
            },
            status=status,
        )

    def respond(client, room, choice, answer, status=HTTPStatus.OK):
        return client(
            "/keep-choice",
            {
                "room": room,
                "id": choice["id"],
                "revision": choice["revision"],
                "role": choice["role"],
                "answer": answer,
            },
            status=status,
        )

    def wait_for(client, room, kind):
        deadline = monotonic() + 15
        while monotonic() < deadline:
            current = keep(client, room)
            for choice in current["choices"]:
                if choice["kind"] == kind:
                    return choice
                if choice["kind"] == "tag_window":
                    respond(client, room, choice, {"options": ["pass"]})
            sleep(0.15)
        raise AssertionError(f"{kind} never opened in the selected scene.")

    with role_activity(tmp_path, local=True, rolls=rolls) as host:
        pilot = local_pilot(host, "Invited pilot")
        room_a, room_b = [
            pilot("/room-create", {"name": name, "location": name})["room"]
            for name in ("Relay maintenance", "Receiving bay")
        ]
        assert pilot("?scene=" + room_b)["active_scene"] is None
        pilot("?scene=relay&scene=relay", status=HTTPStatus.BAD_REQUEST)
        pilot("/enter-scene", {"room": room_a})
        first = start(pilot, room_a)["action_id"]
        respond(pilot, room_a, wait_for(pilot, room_a, "actor_keep"), {"text": "Kept watch."})
        first_choice = wait_for(pilot, room_a, "handler_keep")
        start(pilot, room_a, HTTPStatus.CONFLICT)

        directory = pilot("?scene=" + room_a)["directory"]["rooms"]
        other = next(room for room in directory if room["id"] == room_b)
        assert "keep_your_head" in other["available_play_ids"]
        pilot("/enter-scene", {"room": room_b})
        second = start(pilot, room_b)["action_id"]
        second_choice = wait_for(pilot, room_b, "actor_keep")
        assert first != second
        assert keep(pilot, room_a)["current"]["receipt"]["faces"] == [5, 6]
        assert keep(pilot, room_b)["current"]["receipt"]["faces"] == [6, 6]
        respond(
            pilot, room_b, first_choice, {"flag": True, "text": "Wrong room."}, HTTPStatus.CONFLICT
        )
        assert wait_for(pilot, room_a, "handler_keep") == first_choice

    with role_activity(tmp_path, local=True, rolls=rolls) as host:
        pilot = local_pilot(host, "Invited pilot")
        first_state = keep(pilot, room_a)
        second_state = keep(pilot, room_b)
        assert first_state["current"]["id"] == first and first_state["current"]["receipt"][
            "faces"
        ] == [5, 6]
        assert second_state["current"]["id"] == second and second_state["current"]["receipt"][
            "faces"
        ] == [6, 6]
        assert wait_for(pilot, room_a, "handler_keep") == first_choice
        assert wait_for(pilot, room_b, "actor_keep") == second_choice
        respond(pilot, room_b, second_choice, {"text": "Held the intake."})
        respond(
            pilot,
            room_b,
            wait_for(pilot, room_b, "handler_keep"),
            {"flag": True, "text": "Intake secured."},
        )
        assert keep(pilot, room_b)["current"]["state"] == "complete"
        assert wait_for(pilot, room_a, "handler_keep") == first_choice
        respond(pilot, room_a, first_choice, {"flag": True, "text": "Relay secured."})
        assert keep(pilot, room_a)["current"]["state"] == "complete"
