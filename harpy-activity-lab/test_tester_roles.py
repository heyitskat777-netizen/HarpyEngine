"""Verify role-gated access with an isolated Discord Activity host."""

from dataclasses import replace
from http import HTTPStatus

import pytest

from discord_session import DiscordSessions, SignInError
from discord_test_host import CONFIG, IDENTITIES, TESTER_ROLE, offline_discord_request
from test_artwork_activity import offline_activity, request, setup_action


def test_approved_role_starts_a_separate_pilot_draft(tmp_path):
    with offline_activity(tmp_path, "--bound-roster", "--tester-roles") as host:
        assert request(host, "/api/activity/config")["tester_role_gate"] is True

        def exchange(code, guild=CONFIG.guild_id, status=HTTPStatus.OK):
            challenge = request(host, "/api/discord/challenge", data={})
            return request(
                host,
                "/api/discord/session",
                data={"nonce": challenge["nonce"], "code": code, "guild_id": guild},
                status=status,
            )

        exchange("unapproved", status=HTTPStatus.FORBIDDEN)
        exchange("role-pilot", guild="999999999999999999", status=HTTPStatus.FORBIDDEN)
        admitted = exchange("role-pilot")
        assert admitted["discord_user_id"] == IDENTITIES["role-pilot"]
        initial = request(host, "/api/player-setup", admitted["session"])
        assert initial["stage"] == "profile"
        assert initial["enrollment"]["owner_id"] == IDENTITIES["role-pilot"]
        setup_action(
            host,
            admitted["session"],
            "profile",
            {"revision": initial["revision"], "callsign": "WEIR"},
        )
        resumed = request(host, "/api/player-setup", exchange("role-pilot")["session"])
        assert resumed["callsign"] == "WEIR"
        primary = request(host, "/api/player-setup", exchange("invited")["session"])
        assert primary["stage"] == "profile"
        assert primary["enrollment"]["owner_id"] == IDENTITIES["invited"]


def test_removed_role_is_rechecked_for_existing_session():
    has_role = True

    def provider(path, *, token=None, form=None):
        result = offline_discord_request(path, token=token, form=form)
        if path.endswith("/member") and not has_role:
            return {**result, "roles": []}
        return result

    sessions = DiscordSessions(
        replace(CONFIG, tester_role_ids=frozenset({TESTER_ROLE})), provider
    )
    result = sessions.exchange("role-pilot", sessions.challenge(), CONFIG.guild_id)
    authorization = "Bearer " + result["session"]
    session = sessions.resolve(authorization)
    assert session.role == "role_tester"
    has_role = False
    session.membership_valid_until = 0
    with pytest.raises(SignInError, match="Girl or Frame role"):
        sessions.resolve(authorization)
