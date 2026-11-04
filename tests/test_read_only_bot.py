import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import discord
import pytest
from pydantic import SecretStr, ValidationError

from girlframe.__main__ import main
from girlframe.discord_adapter.bot import (
    PrivateInteractionResponder,
    ReadOnlyDiscordBot,
    dispatch_read_only,
    viewer_from_interaction,
)
from girlframe.discord_adapter.config import BotPolicy, load_bot_policy, load_bot_token
from girlframe.engine.status import PublicCampaignStatus
from girlframe.engine_adapter.snapshot import SANDBOX_MARKER
from girlframe.services.engine_status import EngineStatusUnavailable
from girlframe.services.read_only_bot import CommandDenied, GuildViewer, ReadOnlyBotService


@pytest.fixture
def policy(tmp_path: Path) -> BotPolicy:
    root = tmp_path / "sandbox"
    (root / "state").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts/gm.py").write_text("# Synthetic placeholder; never executed")
    (root / SANDBOX_MARKER).write_text("Synthetic fixture")
    (root / "state/campaign.json").write_text('{"turn":0,"paused":true,"secret":"CANARY"}')
    return BotPolicy(
        application_id=100,
        guild_id=200,
        campaign_id=UUID("00000000-0000-4000-8000-000000000001"),
        sandbox=root,
        status_user_ids=frozenset({300}),
        allow_guild_administrators=True,
        status_audience_approved=True,
    )


def viewer(user_id=300, guild_id=200, admin=False):
    return GuildViewer(user_id, guild_id, guild_id is not None, admin)


class CountingSource:
    def __init__(self):
        self.calls = 0

    def read_status(self):
        self.calls += 1
        return PublicCampaignStatus(turn=0, paused=True)


@pytest.mark.parametrize("command", ["help", "campaign_status", "health"])
@pytest.mark.parametrize("actor", [viewer(guild_id=None), viewer(guild_id=201)])
def test_dm_and_other_guild_denied_before_data_access(policy, command, actor):
    source = CountingSource()
    with pytest.raises(CommandDenied):
        ReadOnlyBotService(policy, source).execute(command, actor)
    assert source.calls == 0


def test_help_and_campaign_membership_checks(policy):
    source = CountingSource()
    service = ReadOnlyBotService(policy, source)
    assert "No rolls" in service.execute("help", viewer(user_id=400))
    with pytest.raises(CommandDenied):
        service.execute("campaign_status", viewer(user_id=400))
    with pytest.raises(CommandDenied):
        service.execute("help", GuildViewer(300, 200, False, False))
    assert source.calls == 0
    assert service.execute("campaign_status", viewer()) == "Campaign turn 0 (paused)."


def test_audience_and_admin_policy_are_explicit(policy):
    source = CountingSource()
    denied = policy.model_copy(update={"status_audience_approved": False})
    with pytest.raises(CommandDenied):
        ReadOnlyBotService(denied, source).execute("campaign_status", viewer(admin=True))
    with pytest.raises(CommandDenied):
        ReadOnlyBotService(policy, source).execute("health", viewer())
    denied = policy.model_copy(update={"allow_guild_administrators": False})
    with pytest.raises(CommandDenied):
        ReadOnlyBotService(denied, source).execute("health", viewer(admin=True))
    assert source.calls == 0
    result = ReadOnlyBotService(policy, source).execute("health", viewer(user_id=400, admin=True))
    assert "responsive" in result and "turn" not in result


class FakeResponse:
    def __init__(self):
        self.done = False
        self.events = []

    def is_done(self):
        return self.done

    async def defer(self, **kwargs):
        self.done = True
        self.events.append(("defer", kwargs))

    async def send_message(self, content, **kwargs):
        self.done = True
        self.events.append(("send", {"content": content, **kwargs}))


def interaction():
    result = MagicMock(spec=discord.Interaction)
    result.response = FakeResponse()
    result.edit_original_response = AsyncMock()
    result.user = MagicMock(spec=discord.Member)
    result.user.id = 300
    result.user.guild_permissions = discord.Permissions.none()
    result.guild_id = 200
    result.created_at = datetime(2026, 11, 2, tzinfo=UTC)
    return result


def test_private_defer_and_allowlisted_reply(policy):
    request = interaction()
    service = ReadOnlyBotService(policy, CountingSource())
    asyncio.run(
        dispatch_read_only(
            "campaign_status",
            viewer_from_interaction(request),
            PrivateInteractionResponder(request),
            service,
        )
    )
    assert request.response.events == [("defer", {"ephemeral": True, "thinking": True})]
    kwargs = request.edit_original_response.call_args.kwargs
    assert kwargs["content"] == "Campaign turn 0 (paused)."
    assert kwargs["allowed_mentions"].to_dict()["parse"] == []


def test_denial_is_private_and_does_not_read_state(policy):
    request = interaction()
    source = CountingSource()
    asyncio.run(
        dispatch_read_only(
            "health",
            viewer(),
            PrivateInteractionResponder(request),
            ReadOnlyBotService(policy, source),
        )
    )
    kind, kwargs = request.response.events[0]
    assert kind == "send" and kwargs["ephemeral"]
    assert kwargs["allowed_mentions"].to_dict()["parse"] == []
    assert source.calls == 0
    request.edit_original_response.assert_not_called()


def test_source_failure_is_sanitized(policy):
    request = interaction()
    source = MagicMock()
    source.read_status.side_effect = EngineStatusUnavailable("CANARY /private/path")
    asyncio.run(
        dispatch_read_only(
            "campaign_status",
            viewer(),
            PrivateInteractionResponder(request),
            ReadOnlyBotService(policy, source),
        )
    )
    content = request.edit_original_response.call_args.kwargs["content"]
    assert "unavailable" in content and "CANARY" not in content and "/private" not in content


def test_sdk_user_without_member_proof_is_not_authorized():
    request = interaction()
    request.user = MagicMock(spec=discord.User)
    request.user.id = 300
    actor = viewer_from_interaction(request)
    assert not actor.is_member and not actor.is_administrator


def test_bot_command_surface_and_intents(policy):
    async def run():
        async with ReadOnlyDiscordBot(
            policy, ReadOnlyBotService(policy, CountingSource()), None
        ) as bot:
            assert not bot.tree.get_commands()
            commands = bot.tree.get_commands(guild=discord.Object(id=policy.guild_id))
            assert {c.name for c in commands} == {"help", "campaign_status", "health"}
            assert all(c.guild_only for c in commands)
            assert next(c for c in commands if c.name == "health").default_permissions.administrator
            assert bot.intents.guilds and not bot.intents.message_content
            assert not bot.intents.members and not bot.intents.presences

    asyncio.run(run())


@pytest.mark.parametrize("matches", [True, False])
def test_setup_verifies_application_then_syncs_only_test_guild(policy, matches):
    async def run():
        async with ReadOnlyDiscordBot(
            policy, ReadOnlyBotService(policy, CountingSource()), None
        ) as bot:
            bot.application_info = AsyncMock(
                return_value=MagicMock(id=policy.application_id if matches else 999)
            )
            bot.fetch_guild = AsyncMock()
            bot.tree.sync = AsyncMock()
            if matches:
                await bot.setup_hook()
                bot.fetch_guild.assert_awaited_once_with(policy.guild_id)
                assert bot.tree.sync.call_args.kwargs["guild"].id == policy.guild_id
            else:
                with pytest.raises(RuntimeError):
                    await bot.setup_hook()
                bot.tree.sync.assert_not_called()
                bot.fetch_guild.assert_not_called()

    asyncio.run(run())


def test_policy_restart_and_cli_check_without_token(policy, tmp_path, monkeypatch, capsys):
    path = tmp_path / "policy.json"
    path.write_text(policy.model_dump_json())
    assert load_bot_policy(path) == policy == load_bot_policy(path)
    monkeypatch.delenv("DiscordBot", raising=False)
    assert main(["start", "--config", str(path), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "m2_review_gated"
    assert main(["start", "--config", str(path)]) == 1
    assert "DiscordBot" in capsys.readouterr().err


def test_secret_repr_and_policy_exclusion(policy):
    secret = "synthetic-credential"
    token = load_bot_token({"DiscordBot": secret})
    assert isinstance(token, SecretStr) and secret not in repr(token)
    with pytest.raises(ValidationError):
        BotPolicy.model_validate_json(
            json.dumps(policy.model_dump(mode="json") | {"token": secret})
        )


def test_startup_exception_is_sanitized(policy, tmp_path, monkeypatch, capsys):
    path = tmp_path / "policy.json"
    path.write_text(policy.model_dump_json())
    monkeypatch.setenv("DiscordBot", "synthetic-credential")

    async def fail(*args, **kwargs):
        raise RuntimeError("synthetic-credential CANARY")

    monkeypatch.setattr("girlframe.__main__.serve", fail)
    assert main(["start", "--config", str(path)]) == 1
    output = capsys.readouterr()
    assert (
        not output.out and "CANARY" not in output.err and "synthetic-credential" not in output.err
    )


def test_cooldown_is_per_guild_and_user(policy):
    async def run():
        async with ReadOnlyDiscordBot(
            policy, ReadOnlyBotService(policy, CountingSource()), None
        ) as bot:
            command = bot.tree.get_command("help", guild=discord.Object(id=policy.guild_id))
            check = command.checks[0]
            request = interaction()
            for _ in range(3):
                assert await check(request)
            with pytest.raises(discord.app_commands.CommandOnCooldown):
                await check(request)
            request.user.id = 301
            assert await check(request)

    asyncio.run(run())


@pytest.mark.parametrize(
    "field,value",
    [("guild_id", True), ("application_id", "100"), ("allow_guild_administrators", "true")],
)
def test_policy_rejects_coerced_identity_and_permission_fields(policy, field, value):
    data = policy.model_dump(mode="json") | {field: value}
    with pytest.raises(ValidationError):
        BotPolicy.model_validate_json(json.dumps(data))


def test_missing_guild_diagnostic_has_no_response_body():
    from girlframe.discord_adapter.runtime import connection_failure_message

    error = discord.NotFound(
        MagicMock(status=404, reason="Not Found"), {"code": 10004, "message": "PRIVATE_CANARY"}
    )
    message = connection_failure_message(error)
    assert "404/10004" in message and "PRIVATE_CANARY" not in message
