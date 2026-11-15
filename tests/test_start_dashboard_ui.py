"""Native Start guide navigation, explicit activation and private member rendering."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import sqlalchemy as sa
from test_creation_review import ready
from test_dual_role_setup import appointed_pilot
from test_inbox import request
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger

from girlframe.database import tables as t
from girlframe.discord_adapter.bot import ReadOnlyDiscordBot
from girlframe.discord_adapter.creation_review import ReviewView
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.start_dashboard import GuideAction, StartView
from girlframe.engine.inbox import InboxItem, InboxPage
from girlframe.engine.m2 import ReleaseApproval
from girlframe.engine.m2_registry import registry_digest
from girlframe.services.m2_state import load_state
from girlframe.services.read_only_bot import ReadOnlyBotService


def current(viewer, key, custom_id=None):
    value = request(viewer, key, custom_id)
    value.extras = {}
    value.user.display_name = "SORROW"
    value.user.roles = []
    value.response.is_done.return_value = False

    async def defer(**kwargs):
        value.response.is_done.return_value = True

    value.response.defer = AsyncMock(side_effect=defer)
    value.response.send_modal = AsyncMock()
    value.response.send_message = AsyncMock()
    value.guild = SimpleNamespace(
        fetch_member=AsyncMock(return_value=SimpleNamespace(display_name="Current server nickname"))
    )
    return value


def test_start_is_private_resumable_owned_and_shows_both_account_roles(ledger, monkeypatch):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    appointed_pilot(ledger)

    async def run():
        async with ReadOnlyDiscordBot(
            ledger.policy, ReadOnlyBotService(ledger.policy, MagicMock()), None, ledger
        ) as bot:
            command = bot.tree.get_command("start", guild=discord.Object(id=ledger.policy.guild_id))
            assert command is not None
            assert not bot.tree.get_commands()
            command.to_dict(bot.tree)
            opening = current(PLAYER, 990001)
            await command.callback(opening)
            opening.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
            rendered = opening.edit_original_response.call_args.kwargs
            view = rendered["view"]
            assert isinstance(view, StartView)
            assert "Handler and Pilot" in rendered["content"]
            assert {x.action for x in view.children if isinstance(x, GuideAction)} >= {
                "character",
                "campaign",
                "requests",
                "sheet",
            }
            assert (
                rendered["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
            )
            assert not await view.interaction_check(current(OTHER, 990002))
            with ledger.engine.connect() as c:
                assert not load_state(c, ledger.campaign_id).sheets
            await bot.start_dashboard.show(current(PLAYER, 990003), "campaign")
            # Viewing and revisiting the guide do not appoint, rank, save or activate.
            assert bot.start_dashboard.progress.snapshot(PLAYER)["campaign"]["status_current"]

    asyncio.run(run())


def test_guided_review_requires_real_save_and_explicit_activation_then_prevents_reset(
    ledger, monkeypatch
):
    from girlframe.discord_adapter import onboarding

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)
    ready(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_intense_tag_bonus": 2,
            "m2_approval": ReleaseApproval(
                registry_sha256=registry_digest(),
                reviewer="synthetic guide only",
                reference="offline fixture, not live approval",
            ),
        }
    )

    async def run():
        async with ReadOnlyDiscordBot(
            ledger.policy, ReadOnlyBotService(ledger.policy, MagicMock()), None, ledger
        ) as bot:
            guide = bot.start_dashboard
            opened = current(PLAYER, 991001)
            await guide.open(opened, "review")
            review = opened.edit_original_response.call_args.kwargs["view"]
            assert isinstance(review, ReviewView)
            saved = current(PLAYER, 991002, review.save.custom_id)
            await review.save.callback(saved)
            assert isinstance(saved.edit_original_response.call_args.kwargs["view"], StartView)
            assert guide.progress.snapshot(PLAYER)["character"]["next_route"] == "activate"
            with ledger.engine.connect() as c:
                assert not load_state(c, ledger.campaign_id).sheets
            activation = current(PLAYER, 991003)
            await guide.continue_step(activation, "character")
            form = activation.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, NativeForm)
            with ledger.engine.connect() as c:
                assert not load_state(c, ledger.campaign_id).sheets
            form.values.update(ack=("yes",), public=())
            await form.confirm.callback(current(PLAYER, 991004))
            with ledger.engine.connect() as c:
                actual = load_state(c, ledger.campaign_id)
                original = actual.sheets["2"].model_dump(mode="json")
                assert set(actual.sheets) == {"2"}
                assert c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_receipts"])) == 0
            await guide.open(current(PLAYER, 991005), "profile")
            with ledger.engine.connect() as c:
                assert (
                    load_state(c, ledger.campaign_id).sheets["2"].model_dump(mode="json")
                    == original
                )

    asyncio.run(run())


def test_inbox_counterpart_names_change_only_display_and_keep_owned_source_text():
    async def run():
        uid = 111111111111111111
        item = InboxItem(
            "bond:original",
            "bond",
            "original",
            1,
            "bonds",
            "Starting Bond",
            f"Saved callsign ({uid})",
            "pending",
            True,
            False,
            "Save agreement",
            "Keep original narrative 123456789123456789",
            "Accept",
        )
        page = InboxPage(item, 0, 1, {"pending": 1, "you": 1, "waiting": 0, "history": 0}, (item,))
        service = SimpleNamespace(page=lambda *args, **kwargs: page)
        view = InboxView(service, PLAYER.user_id)
        interaction = current(PLAYER, 992001)
        await interaction.response.defer(ephemeral=True)
        await view.present(interaction)
        result = interaction.edit_original_response.call_args.kwargs
        assert view.page.item.counterpart == "Current server nickname"
        assert item.counterpart == f"Saved callsign ({uid})"
        assert view.page.item.identity == item.identity and view.page.item.details == item.details
        assert str(uid) not in str(result["embed"].to_dict())
        assert view.page.item.incoming and view.page.item.primary == "Accept"
        assert result["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()

    asyncio.run(run())


def test_campaign_guide_reuses_explicit_name_and_handler_confirmation_without_setup_side_effects(
    ledger, monkeypatch
):
    from girlframe.discord_adapter import onboarding
    from girlframe.discord_adapter.handler_setup import ConfirmSetup
    from girlframe.discord_adapter.start_dashboard import CampaignName

    monkeypatch.setattr(onboarding, "allow_action", lambda *args, **kwargs: True)

    async def run():
        async with ReadOnlyDiscordBot(
            ledger.policy, ReadOnlyBotService(ledger.policy, MagicMock()), None, ledger
        ) as bot:
            guide = bot.start_dashboard
            await guide.open(current(ADMIN, 993001), "join", "campaign")
            assert guide.progress.snapshot(ADMIN)["joined"]
            named = CampaignName(guide, ADMIN.user_id)
            named.name_input._value = "GUIDED TEST CAMPAIGN"
            await named.on_submit(current(ADMIN, 993002))
            assert guide.progress.snapshot(ADMIN)["campaign"]["initialized"]
            ledger.join(PLAYER, "guided-real-handler-membership")
            preview = current(ADMIN, 993003)
            await guide.invoke(preview, "campaign handler", member=current(PLAYER, 993004).user)
            form = preview.edit_original_response.call_args.kwargs["view"]
            assert isinstance(form, ConfirmSetup)
            assert not guide.progress.snapshot(ADMIN)["campaign"]["handler_active"]
            await form.confirm.callback(current(ADMIN, 993005))
            result = guide.progress.snapshot(PLAYER)
            assert result["is_handler"] and not result["character"]["exists"]
            assert result["campaign"]["handler_id"] == PLAYER.user_id
            with ledger.engine.connect() as c:
                assert c.scalar(sa.select(sa.func.count()).select_from(t.characters)) == 0
                assert c.scalar(sa.select(sa.func.count()).select_from(t.resources)) == 0
                assert not load_state(c, ledger.campaign_id).sheets

    asyncio.run(run())
