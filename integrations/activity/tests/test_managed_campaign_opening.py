"""Exercise the managed Activity setup routes with the supplied simulated Discord host."""

from http import HTTPStatus

from discord_test_host import MANAGED_CHANNELS
from test_artwork_activity import offline_activity, request, sign_in


def test_bound_campaign_can_save_a_private_handler_sheet_before_any_pilot_activates(tmp_path):
    with offline_activity(tmp_path, "--bound-roster", "--managed-campaigns") as host:
        handler = sign_in(host, "handler")
        pilot = sign_in(host, "invited")
        campaigns = request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[0]}", handler)
        north = campaigns["preferred"]
        south = next(
            item["id"] for item in campaigns["campaigns"] if item["name"] == "Southern Signal"
        )

        def path(route, campaign=north):
            return f"/api/campaign-opening/{route}?campaign={campaign}"

        choices = request(host, path("persona-setup"), handler)
        original = choices["sheet"]
        assert original["editable"] and original["revision"] == 0 and original["pilots"] == []
        assert "Advocate" in choices["playbooks"]
        assert choices["profiles"]["Advocate"]["behavior"]["wait"]
        assert request(host, path("persona-setup"), pilot)["sheet"] is None
        assert request(host, path("fictional-time"), pilot)["mode"] == "legacy"
        request(
            host,
            path("time-initialize"),
            pilot,
            {"anchor": {"chapter": "Relay", "position": {"day": 1, "slot": "morning"}}},
            status=HTTPStatus.CONFLICT,
        )
        request(host, path("opening"), pilot, status=HTTPStatus.FORBIDDEN)

        change = {
            "revision": original["revision"],
            "appointment": original["appointment"],
            "generation": original["generation"],
            "draft": original["draft"]
            | {
                "playbook": "Advocate",
                "name": "Anchor",
                "notes": {"concern": "PRIVATE_ACTIVITY_PORTRAYAL", "voice": "Slow and deliberate."},
            },
        }
        request(host, path("persona-save"), pilot, change, status=HTTPStatus.CONFLICT)
        assert request(host, path("persona-save"), handler, change)["revision"] == 1
        saved = request(host, path("persona-setup"), handler)["sheet"]
        assert saved["draft"]["name"] == "Anchor" and saved["draft"]["playbook"] == "Advocate"
        assert saved["draft"]["notes"] == change["draft"]["notes"]
        assert "Get Them Alone" in {rule["title"] for rule in saved["rules"]["playbook"]}
        notes = {"revision": saved["revision"], "persona_id": saved["persona_id"], "notes": None}
        request(host, path("persona-notes"), pilot, notes, status=HTTPStatus.CONFLICT)
        request(host, path("persona-notes"), handler, notes, status=HTTPStatus.CONFLICT)
        assert "PRIVATE_ACTIVITY_PORTRAYAL" not in str(request(host, path("persona-setup"), pilot))
        assert request(host, path("persona-setup", south), handler)["sheet"]["revision"] == 0

        empty = request(host, path("opening"), handler)
        assert not empty["launched"] and empty["roles"] == []
        request(
            host,
            path("opening-save"),
            handler,
            {
                "revision": 0,
                "draft": {
                    "location": "Relay station",
                    "situation": "Maintenance is running behind.",
                    "first_choice": "Wait for the inspection or move the check-in?",
                    "session_zero": {"tone": "Quiet operational drama"},
                },
            },
        )
        reviewed = request(host, path("opening"), handler)
        assert "An active character must join the opening scene." in reviewed["blockers"]
        request(
            host,
            path("opening-launch"),
            handler,
            {"review": reviewed["review"]},
            status=HTTPStatus.CONFLICT,
        )
