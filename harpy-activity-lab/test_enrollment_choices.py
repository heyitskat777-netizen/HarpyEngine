"""Two authenticated recruits save different catalogs and countersign an actual setup."""

from http import HTTPStatus

from test_artwork_activity import offline_activity, request, setup_action, sign_in


def test_enrollment_preserves_playbook_fields_and_their_actual_owners(tmp_path):
    with offline_activity(tmp_path, "--bound-roster") as server:
        pilot = sign_in(server, "invited")
        peer = sign_in(server, "other")
        handler = sign_in(server, "handler")
        initial = request(server, "/api/player-setup", pilot)
        assert (
            len(initial["options"]["girls"]) == 10
            and len(initial["options"]["frames"]) == 10
        )
        for token, girl, frame, name in (
            (pilot, "OLDGEN", "THE PRINCE", "LATCH"),
            (peer, "VATGROWN", "THE RED QUEEN", "GLASS"),
        ):
            setup_action(
                server,
                token,
                "profile",
                {
                    "revision": 0,
                    "callsign": name,
                    "girl_playbook": girl,
                    "frame_playbook": frame,
                },
            )
        draft = request(server, "/api/player-setup", pilot)
        initial_choices = {
            "girl_assets": [
                {
                    "name": draft["options"]["girl_assets"][0],
                    "description": "Low-light visor",
                }
            ],
            "frame_name": "Regent",
            "girl_details": {"maxims": [0, 2]},
            "fanbase": {
                "demographics": ["Young boys", "Older men"],
                "demanded": ["Kind", "Relatable"],
                "rejected": ["Dangerous", "A leader"],
            },
        }
        payload = {
            "revision": draft["revision"],
            "character_revision": draft["character_revision"],
            "draft": initial_choices,
        }
        setup_action(server, pilot, "build", payload)
        snapshot = request(server, "/api/player-setup", pilot)
        assert snapshot["draft"]["girl_details"]["maxims"] == [0, 2]
        assert snapshot["draft"]["fanbase"]["demanded"] == ["Kind", "Relatable"]
        assert snapshot["review"]["ready"] is False
        setup_action(
            server,
            pilot,
            "build",
            payload | {"draft": {"shared_tokens": ["forged"]}},
            HTTPStatus.BAD_REQUEST,
        )
        glass = request(server, "/api/player-setup", peer)
        (court,) = [
            record
            for record in glass["creation_choices"]["proposals"]
            if record["kind"] == "court"
        ]
        offered = setup_action(
            server,
            peer,
            "creation-choice",
            {
                "operation": "propose",
                "kind": "court",
                "target": court["target"],
                "context": court["context"],
                "choice": {"role": "The Knight"},
            },
        )
        answer = offered | {
            "operation": "decide",
            "family": "shared",
            "decision": "accept",
        }
        setup_action(server, peer, "creation-choice", answer, HTTPStatus.CONFLICT)
        setup_action(server, pilot, "creation-choice", answer)
        assert any(
            token.startswith("court:")
            for token in request(server, "/api/player-setup", peer)["draft"][
                "shared_tokens"
            ]
        )
        handler_desk = request(server, "/api/player-setup", handler)
        assert any(
            row["kind"] == "vatgrown_handler"
            for row in handler_desk["creation_choices"]["proposals"]
        )
