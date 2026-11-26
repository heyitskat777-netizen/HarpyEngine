"""Campaign membership follows the single role selected by its guild owner."""

import json
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from threading import Timer

import discord_session
import pytest
from activity_paths import RUNTIME
from discord_session import DiscordConfig, DiscordSessions, SignInError
from discord_test_host import CONFIG, MANAGED_ROLES, TESTER_ROLE
from test_artwork_activity import request

TESTER = "666666666666666666"


def test_role_is_the_only_access_gate_for_named_and_unlisted_accounts():
    account = TESTER
    roles = [MANAGED_ROLES[0]]

    def provider(path, *, token=None, form=None):
        if form is not None:
            return {
                "access_token": "synthetic-role-user",
                "expires_in": 300,
                "scope": "identify guilds.members.read",
            }
        if path == "/users/@me":
            return {"id": account}
        return {"user": {"id": account}, "roles": roles}

    sessions = DiscordSessions(replace(CONFIG, tester_role_ids=frozenset({TESTER_ROLE})), provider)
    sessions.campaign_roles_only = True
    sessions.managed_roles = lambda: frozenset(MANAGED_ROLES)
    result = sessions.exchange("synthetic", sessions.challenge(), CONFIG.guild_id)
    header = "Bearer " + result["session"]
    identity = sessions.resolve(header)
    assert identity.discord_id == TESTER and identity.role == "campaign_member"
    assert not sessions.can_use_default(identity)
    roles = []
    for candidate in (CONFIG.invited_user_id, CONFIG.handler_user_id):
        account = candidate
        with pytest.raises(SignInError, match="role assigned to a campaign"):
            sessions.exchange("synthetic", sessions.challenge(), CONFIG.guild_id)
    roles = [TESTER_ROLE]
    with pytest.raises(SignInError, match="role assigned to a campaign"):
        sessions.exchange("synthetic", sessions.challenge(), CONFIG.guild_id)


def test_expiry_during_membership_check_does_not_issue_a_session(monkeypatch):
    now = 1000

    def provider(path, *, token=None, form=None):
        nonlocal now
        if form is not None:
            return {
                "access_token": "synthetic",
                "expires_in": 5,
                "scope": "identify guilds.members.read",
            }
        if path == "/users/@me":
            return {"id": CONFIG.invited_user_id}
        now += 5
        return {"roles": [MANAGED_ROLES[0]]}

    monkeypatch.setattr(discord_session, "monotonic", lambda: now)
    sessions = DiscordSessions(CONFIG, provider)
    sessions.campaign_roles_only = True
    sessions.managed_roles = lambda: frozenset(MANAGED_ROLES)
    with pytest.raises(SignInError) as rejected:
        sessions.exchange("synthetic", sessions.challenge(), CONFIG.guild_id)
    assert rejected.value.status == HTTPStatus.UNAUTHORIZED
    assert not sessions.sessions


def test_signed_in_session_uses_one_discord_role_lookup_and_expires_after_an_hour(monkeypatch):
    now = 1000
    calls = []

    def provider(path, *, token=None, form=None):
        calls.append(path)
        if form is not None:
            return {
                "access_token": "synthetic",
                "expires_in": 7200,
                "scope": "identify guilds.members.read",
            }
        if path == "/users/@me":
            return {"id": TESTER}
        return {"roles": [MANAGED_ROLES[0]]}

    monkeypatch.setattr(discord_session, "monotonic", lambda: now)
    sessions = DiscordSessions(CONFIG, provider)
    sessions.campaign_roles_only = True
    sessions.managed_roles = lambda: frozenset(MANAGED_ROLES)
    result = sessions.exchange("synthetic", sessions.challenge(), CONFIG.guild_id)
    header = "Bearer " + result["session"]
    for check_at in (1000, 1021, 4599):
        now = check_at
        assert sessions.resolve(header).role_ids == frozenset({MANAGED_ROLES[0]})
    now = 4600
    with pytest.raises(SignInError) as expired:
        sessions.resolve(header)
    assert expired.value.status == HTTPStatus.UNAUTHORIZED
    assert calls == ["/oauth2/token", "/users/@me", f"/users/@me/guilds/{CONFIG.guild_id}/member"]


def test_campaign_connection_requires_no_saved_persona_roster():
    config = DiscordConfig.load(
        {
            "GIRLFRAME_ACTIVITY_DISCORD_CLIENT_ID": CONFIG.client_id,
            "GIRLFRAME_ACTIVITY_DISCORD_CLIENT_SECRET": "synthetic-only",
            "GIRLFRAME_ACTIVITY_DISCORD_GUILD_ID": CONFIG.guild_id,
            "GIRLFRAME_ACTIVITY_DISCORD_INVITED_USER_ID": "obsolete-persona-config",
            "GIRLFRAME_ACTIVITY_DISCORD_TESTER_ROLE_IDS": "obsolete-tester-config",
        },
        campaign_roles_only=True,
        allow_dm=True,
    )
    assert config.invited_user_id is None
    assert config.other_user_id is None
    assert config.handler_user_id is None


@contextmanager
def role_activity(
    tmp_path,
    tester=TESTER,
    *,
    bot_handler=False,
    decisions=False,
    inbox=False,
    local=False,
    rolls=None,
):
    candidate = Path(__file__).resolve().parent
    runtime = tmp_path / "role-runtime"
    sdk = runtime / "discord-sdk"
    sdk.mkdir(parents=True, exist_ok=True)
    (sdk / "embedded-app.js").write_bytes(
        (RUNTIME / "discord-sdk" / "embedded-app.js").read_bytes()
    )
    script = """
import json, sys
from dataclasses import replace
from pathlib import Path
candidate, runtime = map(Path, sys.argv[1:3])
tester = sys.argv[3]
bot_mode, decisions, inbox, local, rolls = sys.argv[4:]
sys.argv = [str(candidate / 'mission_lab.py')]
sys.path.insert(0, str(candidate))
import mission_lab as mission
mission.RUNTIME = runtime
if local:
    from discord_test_host import FixedTacticalDice
    dice = FixedTacticalDice(*map(tuple, json.loads(rolls))) if rolls else None
    mission.serve(mission.open_campaign('local-invites'), 0, True, scene_dice=dice)
    raise SystemExit
from discord_test_host import CONFIG, IDENTITIES, managed_campaign_fixture, managed_discord_request
from discord_session import DiscordSessions
IDENTITIES['role-pilot'] = tester
campaign_root = runtime / 'playtest-campaigns' / 'discord-offline-single-role'
catalog = mission.CampaignRegistry(campaign_root / 'managed-fixture.sqlite3')
if bot_mode != 'bot-handler' or not catalog.bindings(CONFIG.client_id, CONFIG.guild_id):
    catalog = managed_campaign_fixture('discord-offline-single-role')
binding = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[0]
service = mission.open_managed_campaign(binding, initialize=False)
if bot_mode == 'bot-handler' and binding.handler_id != CONFIG.client_id:
    from bot_handler_assignment import assign_bot_handler
    binding = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[0]
    assign_bot_handler(service,catalog,binding,bot_id=binding.application_id,expected_handler=binding.handler_id,actor_id=binding.handler_id,key='synthetic-bot-handler')
config = replace(
    CONFIG, invited_user_id=None, other_user_id=None, handler_user_id=None, allow_dm=True
)
provider = managed_discord_request
if decisions == 'decisions':
    import discord_session as auth
    auth.monotonic = lambda: json.loads((runtime / 'relay.json').read_bytes())['now']

    def provider(path, *, token=None, form=None):
        result = managed_discord_request(path, token=token, form=form)
        if token == 'role-pilot' and path.endswith('/member'):
            state = json.loads((runtime / 'relay.json').read_bytes())
            if state.get('revoked'):
                result['roles'] = []
            if state.get('pending'):
                result['pending'] = True
        return result

    from girlframe.services.m2_state import load_state
    from girlframe.services.read_only_bot import GuildViewer
    from mission_desk import MissionDesk
    binding = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[0]
    assert service.store.policy.sandbox.is_relative_to(runtime)
    with service.store.engine.connect() as conn:
        canonical = load_state(conn, service.store.campaign_id)
    if canonical.sheets:
        mission.enable_private_subsystems(service)
        handler = GuildViewer(int(binding.handler_id), int(binding.guild_id), True, False)
        desk = MissionDesk(service)
        for key, objective, recipients in (
            ('solo', 'Synthetic relay inventory', [tester]),
            ('shared', 'Synthetic relay inspection', [tester, CONFIG.invited_user_id]),
        ):
            desk.perform(handler, 'decision-fixture:' + key, {
                'action': 'offer', 'objective': objective, 'pilots': recipients,
            })
bot_token = None
if inbox:
    from contextlib import nullcontext
    import campaign_bot

    def offline_commands(*_, notice_pending, **__):
        bound = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[1]
        item = (bound.id, 'scene_invite', 'unused-invite', bound.handler_id)
        assert notice_pending(bound, item) is False
        return nullcontext()

    campaign_bot.serve_commands = offline_commands
    bot_token = 'synthetic-bot-token'
mission.serve(service, 0, True, DiscordSessions(config, provider),
              bound_roster=True, campaign_registry=catalog, campaign_roles_only=True,
              campaign_bot_token=bot_token)
"""
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-c",
            script,
            str(candidate),
            str(runtime),
            tester,
            "bot-handler" if bot_handler else "human-handler",
            "decisions" if decisions else "",
            "notices" if inbox else "",
            "local" if local else "",
            json.dumps(rolls) if rolls else "",
        ],
        cwd=candidate,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    timeout = Timer(40, child.kill)
    timeout.start()
    try:
        line = child.stdout.readline()
        timeout.cancel()
        if not line:
            _, stderr = child.communicate(timeout=5)
            raise AssertionError(stderr.decode("utf-8", errors="replace"))
        yield json.loads(line)
    finally:
        timeout.cancel()
        try:
            child.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()


def test_role_authorized_pilot_files_its_profile_after_starting_status(tmp_path, monkeypatch):
    import mission_lab
    from campaign_registry import CampaignRegistry

    from girlframe.services.m2_state import load_state

    with role_activity(tmp_path, bot_handler=True) as host:
        runtime = tmp_path / "role-runtime"
        catalog = CampaignRegistry(
            runtime
            / "playtest-campaigns"
            / "discord-offline-single-role"
            / "managed-fixture.sqlite3"
        )
        first = catalog.bindings(CONFIG.client_id, CONFIG.guild_id)[0]
        monkeypatch.setattr(mission_lab, "RUNTIME", runtime)
        service = mission_lab.open_managed_campaign(first, initialize=False)
        try:
            with service.store.transaction() as connection:
                state = load_state(connection, service.store.campaign_id)
                state.order = int(CONFIG.invited_user_id), int(CONFIG.other_user_id)
                state.handler = int(first.handler_id)
                service.game.event(
                    connection,
                    int(first.handler_id),
                    "fixture-existing-order",
                    "synthetic.starting_status",
                    state,
                )
        finally:
            service.store.engine.dispose()
        nonce = request(host, "/api/discord/challenge", data={})["nonce"]
        token = request(
            host,
            "/api/discord/session",
            data={
                "code": "role-pilot",
                "nonce": nonce,
                "guild_id": CONFIG.guild_id,
            },
        )["session"]
        setup = "/api/player-setup"
        selection = "?campaign=" + first.id
        profile = request(host, setup + selection, token)
        assert profile["stage"] == "profile"
        request(
            host,
            setup + "/profile" + selection,
            token,
            {
                "revision": profile["revision"],
                "callsign": "HALCYON",
                "girl_playbook": "AM",
                "frame_playbook": "PROJECT ANKOU",
            },
        )
        reopened = request(host, setup + selection, token)
        assert reopened["callsign"] == "HALCYON"
        assert reopened["options"]["girl"] == "AM"
        assert reopened["options"]["frame"] == "PROJECT ANKOU"
        assert "Wing placement filed" in " ".join(reopened["bot_enrollment"]["notes"])


def test_actual_tester_id_enrolls_its_own_sheet_in_only_its_role_campaign(tmp_path):
    with role_activity(tmp_path) as host:
        assert request(host, "/api/activity/config")["director_trial"] is False

        def sign_in(code, status=HTTPStatus.OK, guild_id=CONFIG.guild_id):
            nonce = request(host, "/api/discord/challenge", data={})["nonce"]
            return request(
                host,
                "/api/discord/session",
                data={
                    "code": code,
                    "nonce": nonce,
                    "guild_id": guild_id,
                },
                status=status,
            )

        sign_in("unapproved", HTTPStatus.FORBIDDEN)
        first = sign_in("role-pilot", guild_id=None)
        assert first["discord_user_id"] == TESTER
        token = first["session"]
        options = request(host, "/api/campaigns", token)["campaigns"]
        assert [item["name"] for item in options] == ["Northern Reach"]
        campaign = options[0]["id"]
        initial = request(host, "/api/player-setup", token)
        assert initial["stage"] == "profile"
        assert initial["enrollment"]["owner_id"] == TESTER
        assert request(host, "/api/director-trial", token)["training_available"] is False
        request(
            host,
            f"/api/player-setup/profile?campaign={campaign}",
            token,
            {"revision": initial["revision"], "callsign": "TESTER ROLE"},
        )
        reopened = sign_in("role-pilot")["session"]
        own = request(host, f"/api/player-setup?campaign={campaign}", reopened)
        assert own["callsign"] == "TESTER ROLE"
        assert own["enrollment"]["owner_id"] == TESTER
        other = sign_in("invited")["session"]
        peer = request(host, f"/api/player-setup?campaign={campaign}", other)
        assert peer["enrollment"]["owner_id"] != TESTER
        assert peer.get("callsign") != "TESTER ROLE"
        second = next(
            item
            for item in request(host, "/api/campaigns", other)["campaigns"]
            if item["name"] == "Southern Signal"
        )
        request(
            host, "/api/player-setup?campaign=" + second["id"], token, status=HTTPStatus.FORBIDDEN
        )
