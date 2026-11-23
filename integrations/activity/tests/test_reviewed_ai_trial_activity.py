"""Exercise the reviewed campaign switch and facilitator boundary over offline Discord auth."""

from http import HTTPStatus
from uuid import UUID, uuid4

from discord_test_host import IDENTITIES, MANAGED_CHANNELS
from test_artwork_activity import offline_activity, request, sign_in


def test_reviewed_ai_trial_isolated_to_nominated_managed_campaign(tmp_path, monkeypatch):
    configure = "--bound-roster", "--managed-campaigns", "--ai-provider-stub"
    monkeypatch.setenv("GIRLFRAME_ACTIVITY_AI_CAMPAIGN", str(uuid4()))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with offline_activity(tmp_path, *configure) as host:
        handler = sign_in(host, "handler")
        assert not request(host, "/api/activity/config")["reviewed_ai_trial"]
        listed = request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[0]}", handler)
        north = listed["preferred"]
        south = next(x["id"] for x in listed["campaigns"] if x["name"] == "Southern Signal")
        north_uuid = str(UUID(north))
        setup = f"/api/activity/ai-setup?campaign={north}"
        pilot = sign_in(host, "invited")
        request(host, setup, status=HTTPStatus.UNAUTHORIZED)
        request(host, setup, pilot, status=HTTPStatus.FORBIDDEN)
        assert request(host, setup, handler) == {
            "campaign_id": north_uuid,
            "configured": False,
            "provider": None,
        }

    monkeypatch.setenv("GIRLFRAME_ACTIVITY_AI_CAMPAIGN", north_uuid)
    monkeypatch.setenv("GIRLFRAME_ACTIVITY_AI_FACILITATOR", IDENTITIES["handler"])
    monkeypatch.setenv("GIRLFRAME_ACTIVITY_HANDLER_MODEL", "offline-fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-token")
    monkeypatch.setenv("GIRLFRAME_ACTIVITY_PILOT_MODEL", "offline-fixture")
    monkeypatch.setenv("GIRLFRAME_ACTIVITY_DIRECTOR_MODEL", "offline-denied")
    monkeypatch.setenv("GIRLFRAME_ACTIVITY_AI_ATTEMPTS", "1")
    with offline_activity(tmp_path, *configure) as host:
        config = request(host, "/api/activity/config")
        assert config["reviewed_ai_trial"] and "offline-fixture" not in str(config)
        handler, pilot = (sign_in(host, role) for role in ("handler", "invited"))
        discovery = f"/api/activity/review-scenes?campaign={north}"
        request(host, discovery, status=HTTPStatus.UNAUTHORIZED)
        assert request(host, discovery, pilot) == {"scenes": []}
        # The original non-AI setup still recognizes the same Handler session.
        sheet = request(host, f"/api/campaign-opening/persona-setup?campaign={north}", handler)
        assert sheet["sheet"]["editable"]
        path = f"/api/director/{uuid4()}/activity-policy"
        assert request(host, f"{path}?campaign={north}", handler) == {
            "enabled": False,
            "revision": 0,
        }
        intent = {"revision": 0, "enabled": True}
        for campaign, actor, status in (
            (north, pilot, HTTPStatus.CONFLICT),
            (south, handler, HTTPStatus.NOT_FOUND),
        ):
            request(host, f"{path}-save?campaign={campaign}", actor, intent, status=status)
        assert request(host, f"{path}-save?campaign={north}", handler, intent) == {
            "enabled": True,
            "revision": 1,
        }
        request(host, f"{path}?campaign={south}", handler, status=HTTPStatus.NOT_FOUND)

        provider = f"/api/activity/ai-provider?campaign={north}"
        request(host, provider, status=HTTPStatus.UNAUTHORIZED)
        request(host, provider, pilot, status=HTTPStatus.FORBIDDEN)
        request(host, provider, pilot, {"role": "handler"}, status=HTTPStatus.FORBIDDEN)
        request(
            host,
            f"/api/activity/ai-provider?campaign={south}",
            handler,
            status=HTTPStatus.NOT_FOUND,
        )
        summary = request(host, setup, handler)
        assert summary["campaign_id"] == north_uuid and summary["configured"]
        assert "offline-test-token" not in str(summary)
        request(host, setup, pilot, status=HTTPStatus.FORBIDDEN)
        assert request(host, f"/api/activity/ai-setup?campaign={south}", handler) == {
            "campaign_id": str(UUID(south)),
            "configured": False,
            "provider": None,
        }
        roles = summary["provider"]["roles"]
        assert roles == request(host, provider, handler)["roles"]
        assert roles["handler"]["connection"] == "unchecked"
        assert roles["handler"]["attempts"] == 0
        with monkeypatch.context() as replay:
            replay.setattr("test_artwork_activity.uuid4", lambda: "fixture-probe-same-key")
            checked = request(host, provider, handler, {"role": "handler"})
            assert request(host, provider, handler, {"role": "handler"}) == checked
        assert checked["result"] == "ok"
        assert checked["roles"]["handler"] == checked["roles"]["pilot"]
        assert checked["roles"]["handler"] == {
            "model": "offline-fixture",
            "connection": "ok",
            "attempts": 1,
            "attempt_limit": 1,
            "input_tokens": 64,
            "output_tokens": 7,
            "reported_usage_calls": 1,
            "last_status": "ok",
        }
        limited = request(host, provider, handler, {"role": "pilot"})
        assert limited["result"] == "attempt_limit"
        denied = request(host, provider, handler, {"role": "director"})
        assert denied["result"] == "model_access"
        assert denied["roles"]["director"]["attempts"] == 1
        assert "PRIVATE_PROVIDER_ERROR" not in str(denied)
        assert "offline-test-token" not in str(denied)
