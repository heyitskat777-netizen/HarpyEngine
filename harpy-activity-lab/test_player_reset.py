"""The reset endpoint needs both confirmations from the actual sheet owner."""

from http import HTTPStatus

from test_artwork_activity import (
    activate_recruit,
    offline_activity,
    request,
    setup_action,
    sign_in,
)


def test_approved_sheet_reset_archives_owner_and_reopens_fresh_enrollment(tmp_path):
    with offline_activity(tmp_path, "--bound-roster") as server:
        pilot, peer, handler = (sign_in(server, name) for name in ("invited", "other", "handler"))
        for auth, callsign in ((pilot, "LATCH"), (peer, "ECHO")):
            setup_action(server, auth, "profile", {"revision": 0, "callsign": callsign})
        activate_recruit(server, pilot, peer, keep_callsign=True)
        active = request(server, "/api/player-setup", pilot)
        assert active["stage"] == "active"
        payload = active["sheet_reset"] | {"confirmed": True}
        setup_action(
            server,
            pilot,
            "purge-sheet",
            payload | {"confirmed": False},
            HTTPStatus.BAD_REQUEST,
        )
        setup_action(
            server,
            pilot,
            "purge-sheet",
            payload | {"callsign": "ECHO"},
            HTTPStatus.CONFLICT,
        )
        setup_action(server, peer, "purge-sheet", payload, HTTPStatus.CONFLICT)
        setup_action(server, handler, "purge-sheet", payload, HTTPStatus.FORBIDDEN)
        assert request(server, "/api/player-setup", pilot)["sheet_reset"] == active["sheet_reset"]
        receipt = setup_action(server, pilot, "purge-sheet", payload)
        assert receipt["archive_id"]
        reopened = sign_in(server, "invited")
        intake = request(server, "/api/player-setup", reopened)
        assert intake["stage"] == "profile" and "sheet_reset" not in intake
        setup_action(
            server,
            reopened,
            "profile",
            {
                "revision": intake["revision"],
                "callsign": "LATCH-2",
                "girl_playbook": "MOCKINGBIRD",
                "frame_playbook": "JANUS",
            },
        )
        new_draft = request(server, "/api/player-setup", reopened)
        assert new_draft["callsign"] == "LATCH-2"
        assert new_draft["stage"] == "draft"
        assert not new_draft["draft"]["girl_assets"] and not new_draft["draft"]["frame_assets"]
        status = request(server, "/api/player-setup", handler)["career_status"][0]
        assert status["character"] != payload["character"]
        setup_action(
            server,
            handler,
            "career-status",
            {
                "owner": status["owner"],
                "character": status["character"],
                "revision": status["game_revision"],
                "position": 0,
            },
        )
        assert not request(server, "/api/player-setup", handler)["career_status"]
        try:
            activate_recruit(server, reopened, peer, keep_callsign=True)
        except AssertionError as error:
            raise AssertionError(
                request(server, "/api/player-setup", reopened)["review"]
            ) from error
        recreated = request(server, "/api/player-setup", reopened)
        assert recreated["stage"] == "active"
        assert recreated["sheet_reset"]["character"] == status["character"]
        assert recreated["callsign"] == "LATCH-2"
