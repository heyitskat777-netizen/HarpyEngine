"""Exercise Session Zero ownership with the Activity's simulated Discord sign-in."""

from http import HTTPStatus

from discord_test_host import IDENTITIES, MANAGED_CHANNELS
from test_artwork_activity import offline_activity, request, sign_in


def test_session_zero_difficulty_and_cast_use_the_current_private_group(tmp_path):
    with offline_activity(tmp_path, "--bound-roster", "--managed-campaigns") as host:
        handler, pilot, other = (sign_in(host, role) for role in ("handler", "invited", "other"))
        campaigns = request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[0]}", handler)
        north = campaigns["preferred"]
        south = next(
            row["id"] for row in campaigns["campaigns"] if row["name"] == "Southern Signal"
        )

        def route(name, campaign=north):
            return f"/api/campaign-opening/{name}?campaign={campaign}"

        def get(owner=handler, campaign=north):
            return request(host, route("session-zero", campaign), owner)

        def post(name, owner, data, status=HTTPStatus.OK):
            return request(host, route("session-zero-" + name), owner, data, status=status)

        for owner in (pilot, other):
            request(host, f"/api/player-setup?campaign={north}", owner)
            request(host, route("session-zero"), owner, status=HTTPStatus.FORBIDDEN)
        hm, pm = (IDENTITIES[role] for role in ("handler", "invited"))
        members = {"revision": get()["revision"], "members": [hm, pm]}
        post("group", pilot, members, HTTPStatus.CONFLICT)
        post("group", handler, members)
        profile = {
            "member": hm,
            "control": "ai",
            "name": "Sable",
            "archetype": "Advocate",
            "appearance": "A blue flight jacket.",
            "personality": "Waits for a call.",
        }
        post("propose", handler, {"revision": get()["revision"], "profile": profile})
        nomination = get()["proposal"]
        for owner in (handler, pilot):
            post("handler-vote", owner, {"proposal": nomination, "approve": True})
        assert get(pilot)["handler_ready"] == hm
        assert get(pilot)["player_count"] == 1
        assert set(get(pilot)["difficulty_options"]) == {"narrative", "normal", "hard"}
        plan = {
            "revision": get()["revision"],
            "difficulty": "narrative",
            "goals": "Find out who owns the relay.",
            "seats": {"player_count": 1, "ai_pilots": [{"callsign": "Orchard"}]},
        }
        post("plan", pilot, plan, HTTPStatus.CONFLICT)
        post("plan", handler, plan | {"seats": {"player_count": 2}}, HTTPStatus.CONFLICT)
        post("plan", handler, plan)
        prior = get()["plan_proposal"]
        post("plan-vote", pilot, {"proposal": prior, "approve": True})
        post("plan", handler, plan | {"revision": get()["revision"], "difficulty": "hard"})
        assert get(pilot)["plan_approvals"] == 0
        assert get(pilot)["seats"]["ai_pilots"][0]["callsign"] == "Orchard"
        post("plan-vote", pilot, {"proposal": prior, "approve": True}, HTTPStatus.CONFLICT)
        request(host, route("session-zero"), other, status=HTTPStatus.FORBIDDEN)
        assert get(handler, south)["members"] == []
        post(
            "open",
            handler,
            {"revision": get()["revision"], "introduction": "Cadre, check in.", "days": 3},
            HTTPStatus.CONFLICT,
        )
