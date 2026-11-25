"""Two authenticated recruits save different catalogs and countersign an actual setup."""

from http import HTTPStatus

from test_artwork_activity import offline_activity, request, setup_action, sign_in


def test_enrollment_preserves_playbook_fields_and_their_actual_owners(tmp_path):
    with offline_activity(tmp_path, "--bound-roster") as server:
        pilot = sign_in(server, "invited")
        peer = sign_in(server, "other")
        handler = sign_in(server, "handler")
        initial = request(server, "/api/player-setup", pilot)
        assert len(initial["options"]["girls"]) == 10
        assert set(initial["options"]["frames"]) == {
            "THE PRINCE",
            "CONSUME",
            "JANUS",
            "DOCTORDOCTOR MK. II",
            "WYVERN 0.4",
            "THE ENFORCER",
            "CHANGELING",
            "PROJECT ANKOU",
            "THE RED QUEEN",
        }
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
            record for record in glass["creation_choices"]["proposals"] if record["kind"] == "court"
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
            for token in request(server, "/api/player-setup", peer)["draft"]["shared_tokens"]
        )
        handler_desk = request(server, "/api/player-setup", handler)
        assert any(
            row["kind"] == "vatgrown_handler"
            for row in handler_desk["creation_choices"]["proposals"]
        )


def test_newgirl_prior_missions_round_trip_exact_discord_ids(tmp_path):
    with offline_activity(tmp_path, "--bound-roster") as server:
        pilot = sign_in(server, "invited")
        peer = sign_in(server, "other")
        for token, callsign, girl, frame in (
            (pilot, "RAIL", "NEWGIRL", "CHANGELING"),
            (peer, "GLASS", "MOCKINGBIRD", "JANUS"),
        ):
            setup_action(
                server,
                token,
                "profile",
                {
                    "revision": 0,
                    "callsign": callsign,
                    "girl_playbook": girl,
                    "frame_playbook": frame,
                },
            )
        record = request(server, "/api/player-setup", pilot)
        member = next(item for item in record["enrollment"]["cadre"] if item["callsign"] == "GLASS")
        identity = member["id"]
        assert int(float(identity)) != int(identity)
        declaration = {"user_id": identity, "character_revision": member["revision"], "missions": 0}
        dossier = {"frame_name": "試験 (Shiken)", "prior_missions": [declaration]}
        payload = {
            "revision": record["revision"],
            "character_revision": record["character_revision"],
            "draft": dossier,
        }
        for invalid_id, status in (
            ("+" + identity, HTTPStatus.BAD_REQUEST),
            (str(int(identity) + 1), HTTPStatus.CONFLICT),
        ):
            setup_action(
                server,
                pilot,
                "build",
                payload
                | {
                    "draft": dossier
                    | {
                        "prior_missions": [declaration | {"user_id": invalid_id}],
                    }
                },
                status,
            )
        incomplete = setup_action(
            server,
            pilot,
            "build",
            payload | {"draft": dossier | {"cadre_discussed": True}},
            HTTPStatus.CONFLICT,
        )
        assert incomplete["fields"] == [
            {
                "path": ["prior_missions"],
                "message": (
                    "Answer for every current Cadre member before confirming the discussion."
                ),
            }
        ]
        receipt = setup_action(server, pilot, "build", payload)
        assert receipt["status"] == "creation_in_progress"
        assert receipt["revision"] == record["revision"] + 1

    with offline_activity(tmp_path, "--bound-roster") as server:
        reopened = sign_in(server, "invited")
        restored = request(server, "/api/player-setup", reopened)
        assert restored["revision"] == receipt["revision"]
        assert restored["draft"]["frame_name"] == dossier["frame_name"]
        assert restored["draft"]["prior_missions"] == [declaration]
        assert restored["review"]["ready"] is False
