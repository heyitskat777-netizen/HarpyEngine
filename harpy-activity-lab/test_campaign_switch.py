"""Bot binding and Activity campaign-scope checks with isolated fixtures."""

import asyncio
from http import HTTPStatus
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import campaign_bot
import discord
import pytest
from campaign_bot import SetupBot, create_from_interaction, dm_command, serve_commands
from campaign_registry import CampaignBindingError, CampaignRegistry
from discord_session import DiscordSessions, SignInError
from discord_test_host import (
    CONFIG,
    MANAGED_CHANNELS,
    MANAGED_ROLES,
    managed_discord_request,
)
from test_artwork_activity import offline_activity, request


def test_only_guild_owner_can_persist_a_role_binding(tmp_path):
    registry = CampaignRegistry(tmp_path / "campaigns.sqlite3")
    guild = SimpleNamespace(id=int(CONFIG.guild_id), owner_id=int(CONFIG.handler_user_id))
    role = SimpleNamespace(id=int(MANAGED_ROLES[0]), guild=guild)
    interaction = SimpleNamespace(
        guild=guild,
        guild_id=guild.id,
        user=SimpleNamespace(id=int(CONFIG.invited_user_id)),
        application_id=int(CONFIG.client_id),
        id=123456789012345678,
    )
    interaction.user.guild_permissions = SimpleNamespace(administrator=True)
    with pytest.raises(CampaignBindingError, match="server owner"):
        create_from_interaction(registry, interaction, "Northern Reach", role, None)
    assert not registry.path.exists()

    interaction.user.id = guild.owner_id
    with pytest.raises(CampaignBindingError, match="@everyone"):
        create_from_interaction(
            registry,
            interaction,
            "Northern Reach",
            SimpleNamespace(id=guild.id, guild=guild),
            None,
        )
    with pytest.raises(CampaignBindingError, match="from this server"):
        create_from_interaction(
            registry,
            interaction,
            "Northern Reach",
            SimpleNamespace(id=role.id, guild=SimpleNamespace(id=111111111111111119)),
            None,
        )
    channel = SimpleNamespace(id=int(MANAGED_CHANNELS[0]), guild=guild)
    bound = create_from_interaction(
        registry, interaction, "Northern Reach", role, None, channel=channel
    )
    assert bound.role_id == MANAGED_ROLES[0]
    assert bound.channel_id == MANAGED_CHANNELS[0]
    assert CampaignRegistry(registry.path).bindings(CONFIG.client_id, CONFIG.guild_id) == [bound]
    assert CampaignRegistry(registry.path).bindings(CONFIG.client_id, "111111111111111119") == []
    assert (
        create_from_interaction(
            registry, interaction, "Northern Reach", role, None, channel=channel
        )
        == bound
    )
    with pytest.raises(CampaignBindingError, match="different binding"):
        create_from_interaction(registry, interaction, "Changed", role, None)
    interaction.id += 1
    with pytest.raises(CampaignBindingError, match="already exists"):
        create_from_interaction(registry, interaction, "northern reach", role, None)
    with pytest.raises(CampaignBindingError, match="already exists"):
        create_from_interaction(registry, interaction, "New campaign", role, None, channel=channel)
    bot = SetupBot(int(CONFIG.client_id), int(CONFIG.guild_id), registry)
    payload = bot.command.to_dict(bot.tree)
    assert payload["name"] == "activity-campaign"
    assert {item["name"] for item in payload["options"]} == {"create", "launch"}


@pytest.mark.parametrize(
    ("guild_id", "channel_id", "has_role", "error"),
    [
        (CONFIG.guild_id, MANAGED_CHANNELS[0], True, None),
        (CONFIG.guild_id, MANAGED_CHANNELS[0], False, "Discord role"),
        (CONFIG.guild_id, MANAGED_CHANNELS[1], True, "no Activity campaign"),
        ("111111111111111119", MANAGED_CHANNELS[0], True, "no Activity campaign"),
    ],
)
def test_launch_requires_a_bound_channel_and_its_role(
    tmp_path, guild_id, channel_id, has_role, error
):
    registry = CampaignRegistry(tmp_path / "campaigns.sqlite3")
    registry.register(
        application_id=CONFIG.client_id,
        guild_id=CONFIG.guild_id,
        owner_id=CONFIG.handler_user_id,
        actor_id=CONFIG.handler_user_id,
        role_id=MANAGED_ROLES[0],
        role_guild_id=CONFIG.guild_id,
        handler_id=CONFIG.handler_user_id,
        interaction_id="123456789012345678",
        name="Northern Reach",
        channel_id=MANAGED_CHANNELS[0],
        channel_guild_id=CONFIG.guild_id,
    )
    bot = SetupBot(int(CONFIG.client_id), int(CONFIG.guild_id), registry)
    member = Mock(spec=discord.Member)
    member.get_role.return_value = Mock() if has_role else None
    response = Mock(spec=discord.InteractionResponse)
    interaction = SimpleNamespace(
        user=member,
        response=response,
        guild_id=int(guild_id),
        channel_id=int(channel_id),
        application_id=int(CONFIG.client_id),
    )
    asyncio.run(bot.command.get_command("launch").callback(interaction))
    if error:
        response.launch_activity.assert_not_awaited()
        response.send_message.assert_awaited_once()
        assert error in response.send_message.call_args.args[0]
        assert response.send_message.call_args.kwargs["ephemeral"] is True
    else:
        member.get_role.assert_called_once_with(int(MANAGED_ROLES[0]))
        response.launch_activity.assert_awaited_once_with()
        response.send_message.assert_not_awaited()


@pytest.mark.parametrize(
    ("user_install", "contexts", "installs"),
    [
        (False, [1], [0]),
        (True, [1, 2], [0, 1]),
    ],
)
def test_dm_launch_registration_and_callback(tmp_path, user_install, contexts, installs):
    registry = CampaignRegistry(tmp_path / "campaigns.sqlite3")
    bot = SetupBot(int(CONFIG.client_id), int(CONFIG.guild_id), registry, allow_dm=True)
    dm = dm_command(user_install)
    payload = dm.to_dict(bot.tree)
    assert payload["contexts"] == contexts
    assert payload["integration_types"] == installs
    assert [item["name"] for item in payload["options"]] == ["launch"]
    response = Mock(spec=discord.InteractionResponse)
    asyncio.run(dm.get_command("launch").callback(SimpleNamespace(response=response)))
    response.launch_activity.assert_awaited_once_with()


def test_integrated_command_listener_lifetime(tmp_path, monkeypatch):
    started = Event()
    closed = Event()
    registry = CampaignRegistry(tmp_path / "campaigns.sqlite3")

    class OfflineGateway:
        def __init__(self, app, guild, catalog, *, allow_dm, provision):
            assert app == int(CONFIG.client_id)
            assert guild == int(CONFIG.guild_id)
            assert catalog is registry

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.set()

        async def start(self, token):
            assert token == "synthetic-token"
            started.set()
            await asyncio.Future()

    monkeypatch.setattr(campaign_bot, "SetupBot", OfflineGateway)
    with serve_commands(CONFIG, registry, "synthetic-token", None):
        assert started.wait(2)
        assert not closed.is_set()
    assert closed.is_set()


def test_removed_campaign_role_is_checked_on_the_next_sign_in():
    allowed = True

    def provider(path, *, token=None, form=None):
        response = managed_discord_request(path, token=token, form=form)
        if path.endswith("/member") and not allowed:
            response["roles"] = []
        return response

    sessions = DiscordSessions(CONFIG, provider)
    sessions.managed_roles = lambda: frozenset(MANAGED_ROLES)
    result = sessions.exchange("role-pilot", sessions.challenge(), CONFIG.guild_id)
    header = "Bearer " + result["session"]
    session = sessions.resolve(header)
    allowed = False
    assert sessions.resolve(header) is session
    with pytest.raises(SignInError, match="campaign role"):
        sessions.exchange("role-pilot", sessions.challenge(), CONFIG.guild_id)


def test_campaign_scope_is_role_bound_and_keeps_drafts_separate(tmp_path):
    def sign_in(host, identity):
        challenge = request(host, "/api/discord/challenge", data={})
        return request(
            host,
            "/api/discord/session",
            data={
                "nonce": challenge["nonce"],
                "code": identity,
                "guild_id": CONFIG.guild_id,
            },
        )["session"]

    with offline_activity(tmp_path, "--bound-roster", "--managed-campaigns") as host:
        request(host, "/api/campaigns", status=HTTPStatus.UNAUTHORIZED)
        pilot = sign_in(host, "invited")
        outsider = sign_in(host, "role-pilot")
        options = request(host, "/api/campaigns", pilot)["campaigns"]
        names = {item["name"]: item["id"] for item in options}
        north, south = names["Northern Reach"], names["Southern Signal"]
        assert (
            request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[1]}", pilot)["preferred"]
            == south
        )
        assert (
            request(host, f"/api/campaigns?channel={MANAGED_CHANNELS[1]}", outsider)["preferred"]
            is None
        )
        assert request(host, "/api/campaigns", outsider)["campaigns"] == [
            {"id": north, "name": "Northern Reach"},
        ]
        assert request(host, "/api/activity/config")["campaign_role_gate"] is True
        assert {item["name"] for item in options} == {"Northern Reach", "Southern Signal"}
        assert (
            request(host, "/api/player-setup", outsider)["enrollment"]["owner_id"]
            == "666666666666666666"
        )
        for path in (
            f"/api/player-setup?campaign={south}",
            f"/api/player-setup?campaign={north}&campaign={south}",
        ):
            request(
                host,
                path,
                outsider,
                status=HTTPStatus.BAD_REQUEST if "&" in path else HTTPStatus.FORBIDDEN,
            )
        request(
            host,
            f"/api/player-setup/profile?campaign={south}",
            outsider,
            {"revision": 0, "callsign": "FORGED"},
            status=HTTPStatus.FORBIDDEN,
        )
        for campaign, callsign in ((north, "NORTH PILOT"), (south, "SOUTH PILOT")):
            initial = request(host, f"/api/player-setup?campaign={campaign}", pilot)
            assert initial["stage"] == "profile"
            assert not initial.get("callsign")
            request(
                host,
                f"/api/player-setup/profile?campaign={campaign}",
                pilot,
                {"revision": initial["revision"], "callsign": callsign},
            )
        assert (
            request(host, f"/api/player-setup?campaign={north}", pilot)["callsign"] == "NORTH PILOT"
        )
        assert (
            request(host, f"/api/player-setup?campaign={south}", pilot)["callsign"] == "SOUTH PILOT"
        )
        request(host, "/api/player-setup", pilot, status=HTTPStatus.CONFLICT)

    with offline_activity(tmp_path, "--bound-roster", "--managed-campaigns") as reopened:
        signed_in = sign_in(reopened, "invited")
        assert request(reopened, "/api/campaigns", signed_in)["campaigns"] == options
        assert (
            request(reopened, f"/api/player-setup?campaign={north}", signed_in)["callsign"]
            == "NORTH PILOT"
        )
        assert (
            request(reopened, f"/api/player-setup?campaign={south}", signed_in)["callsign"]
            == "SOUTH PILOT"
        )
