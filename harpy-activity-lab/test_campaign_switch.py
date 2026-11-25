"""Bot binding and Activity campaign-scope checks with isolated fixtures."""

import asyncio
from http import HTTPStatus
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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
    assert {item["name"] for item in payload["options"]} == {"create", "launch", "help"}


def test_activity_help_is_private_and_points_to_campaign_safety(tmp_path):
    bot = SetupBot(int(CONFIG.client_id), int(CONFIG.guild_id), CampaignRegistry(tmp_path / "db"))
    response = Mock(spec=discord.InteractionResponse)
    asyncio.run(bot.command.get_command("help").callback(SimpleNamespace(response=response)))
    text = response.send_message.call_args.args[0]
    assert all(
        item in text
        for item in ("/activity-campaign create", "/activity-campaign launch", "**Safety**")
    )
    assert response.send_message.call_args.kwargs["ephemeral"] is True
    assert response.send_message.call_args.kwargs["allowed_mentions"].everyone is False


@pytest.mark.parametrize("mode", ["default", "retire", "list", "failed_publish", "wrong_app"])
def test_activity_registration_only_retires_known_guild_commands_after_publish(
    mode, tmp_path, monkeypatch, capsys
):
    bot = SetupBot(
        int(CONFIG.client_id),
        int(CONFIG.guild_id),
        CampaignRegistry(tmp_path / "db"),
        allow_dm=True,
        retire_legacy=mode in {"retire", "failed_publish", "wrong_app"},
        list_commands=mode == "list",
    )
    activity = SimpleNamespace(
        name="activity-campaign", type=discord.AppCommandType.chat_input, delete=AsyncMock()
    )
    legacy = SimpleNamespace(
        name="play", type=discord.AppCommandType.chat_input, delete=AsyncMock()
    )
    old_help = SimpleNamespace(
        name="help", type=discord.AppCommandType.chat_input, delete=AsyncMock()
    )
    context = SimpleNamespace(name="play", type=discord.AppCommandType.user, delete=AsyncMock())
    other = SimpleNamespace(
        name="other-tool", type=discord.AppCommandType.chat_input, delete=AsyncMock()
    )
    global_launch = SimpleNamespace(
        name="launch", type=discord.AppCommandType.chat_input, delete=AsyncMock()
    )
    calls = []

    async def read(*, guild=None):
        calls.append("guild read" if guild else "global read")
        if guild is None:
            return [global_launch]
        assert guild.id == int(CONFIG.guild_id)
        return [activity, legacy, old_help, context, other]

    async def publish_guild(application, guild, payload):
        assert application == int(CONFIG.client_id) and guild == int(CONFIG.guild_id)
        calls.append("guild upsert")
        assert {item["name"] for item in payload["options"]} == {"create", "help", "launch"}
        if mode == "failed_publish":
            raise RuntimeError("Can't publish.")

    async def publish_dm(application, payload):
        assert application == int(CONFIG.client_id)
        calls.append("global upsert")
        assert {item["name"] for item in payload["options"]} == {"help", "launch"}

    info = SimpleNamespace(
        id=int(CONFIG.client_id) if mode != "wrong_app" else 999,
        user_integration_config=None,
    )
    monkeypatch.setattr(bot, "application_info", AsyncMock(return_value=info))
    monkeypatch.setattr(bot.tree, "fetch_commands", read)
    monkeypatch.setattr(bot.tree, "sync", AsyncMock())
    monkeypatch.setattr(bot.http, "upsert_guild_command", publish_guild)
    monkeypatch.setattr(bot.http, "upsert_global_command", publish_dm)
    if mode in {"failed_publish", "wrong_app"}:
        with pytest.raises(RuntimeError):
            asyncio.run(bot.setup_hook())
    else:
        asyncio.run(bot.setup_hook())

    assert (
        calls
        == {
            "default": ["guild upsert", "global upsert"],
            "retire": ["guild upsert", "global upsert", "guild read"],
            "list": ["guild read", "global read"],
            "failed_publish": ["guild upsert"],
            "wrong_app": [],
        }[mode]
    )
    if mode == "retire":
        legacy.delete.assert_awaited_once()
        old_help.delete.assert_awaited_once()
    else:
        legacy.delete.assert_not_awaited()
        old_help.delete.assert_not_awaited()
    for command in (activity, context, other, global_launch):
        command.delete.assert_not_awaited()
    bot.tree.sync.assert_not_awaited()
    if mode == "list":
        output = capsys.readouterr().out
        assert "guild chat_input play (retired HarpyEngine guild command)" in output
        assert "guild user play\n" in output
        assert "global chat_input launch\n" in output


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
    assert {item["name"] for item in payload["options"]} == {"help", "launch"}
    response = Mock(spec=discord.InteractionResponse)
    asyncio.run(dm.get_command("launch").callback(SimpleNamespace(response=response)))
    response.launch_activity.assert_awaited_once_with()


def test_integrated_command_listener_lifetime(tmp_path, monkeypatch):
    started = Event()
    closed = Event()
    registry = CampaignRegistry(tmp_path / "campaigns.sqlite3")

    class OfflineGateway:
        def __init__(self, app, guild, catalog, *, allow_dm, provision, retire_legacy):
            assert app == int(CONFIG.client_id)
            assert guild == int(CONFIG.guild_id)
            assert catalog is registry
            assert retire_legacy is True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.set()

        async def start(self, token):
            assert token == "synthetic-token"
            started.set()
            await asyncio.Future()

    monkeypatch.setattr(campaign_bot, "SetupBot", OfflineGateway)
    with serve_commands(CONFIG, registry, "synthetic-token", None, retire_legacy=True):
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


def sign_in(host, identity):
    challenge = request(host, "/api/discord/challenge", data={})
    return request(
        host,
        "/api/discord/session",
        data={"nonce": challenge["nonce"], "code": identity, "guild_id": CONFIG.guild_id},
    )["session"]


def test_campaign_safety_is_available_without_a_scene_and_isolated_on_reopen(tmp_path):
    with offline_activity(tmp_path, "--bound-roster", "--managed-campaigns") as host:
        first = sign_in(host, "invited")
        second = sign_in(host, "role-pilot")
        campaigns = {
            row["name"]: row["id"] for row in request(host, "/api/campaigns", first)["campaigns"]
        }
        north = f"/api/activity/safety?campaign={campaigns['Northern Reach']}"
        south = f"/api/activity/safety?campaign={campaigns['Southern Signal']}"
        request(host, north, status=HTTPStatus.UNAUTHORIZED)
        request(host, south, second, status=HTTPStatus.FORBIDDEN)
        request(host, south, second, {"pause": True, "revision": 0}, status=HTTPStatus.FORBIDDEN)
        before = request(host, north, first)
        assert before.keys() == {"paused", "own", "revision"}
        assert before["paused"] is False and before["own"] is False
        assert (
            request(host, north.replace("activity/safety", "player-setup"), first)["stage"]
            == "profile"
        )
        pause = {"pause": True, "revision": before["revision"]}
        receipt = request(host, north, first, pause, key="north-first-pause")
        assert receipt == {"paused": True, "your_pause": True}
        assert request(host, north, first, pause, key="north-first-pause") == receipt
        assert request(host, south, first)["paused"] is False
        another = request(host, north, second)
        assert another["paused"] is True and another["own"] is False
        request(
            host,
            north,
            second,
            {"pause": False, "revision": another["revision"], "owner_id": CONFIG.invited_user_id},
            status=HTTPStatus.BAD_REQUEST,
        )
        assert request(host, north, second, {"pause": False, "revision": another["revision"]}) == {
            "paused": True,
            "your_pause": False,
        }
        request(
            host,
            north,
            first,
            {"pause": False, "revision": before["revision"]},
            status=HTTPStatus.CONFLICT,
        )
        request(host, north, second, {"pause": True, "revision": another["revision"]})

    with offline_activity(tmp_path, "--bound-roster", "--managed-campaigns") as host:
        first = sign_in(host, "invited")
        second = sign_in(host, "role-pilot")
        state = request(host, north, first)
        assert state["paused"] is True and state["own"] is True
        assert request(host, south, first)["paused"] is False
        assert request(host, north, first, {"pause": False, "revision": state["revision"]}) == {
            "paused": True,
            "your_pause": False,
        }
        state = request(host, north, second)
        assert state["paused"] is True and state["own"] is True
        assert request(host, north, second, {"pause": False, "revision": state["revision"]}) == {
            "paused": False,
            "your_pause": False,
        }
        assert request(host, north, first, pause, key="north-first-pause") == receipt
        assert request(host, north, first)["paused"] is False


def test_campaign_scope_is_role_bound_and_keeps_drafts_separate(tmp_path):

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
