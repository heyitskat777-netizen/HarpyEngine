"""Member names change presentation only; message contents and identities stay owned."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from girlframe.discord_adapter.member_names import (
    member_label,
    render_member_labels,
    render_member_view,
)
from girlframe.discord_adapter.onboarding import reply


def test_current_member_names_refresh_keep_opaque_controls_and_plain_text():
    async def run():
        uid = 111111111111111111
        current = SimpleNamespace(display_name="SORROW", name="account-name")
        guild = SimpleNamespace(fetch_member=AsyncMock(return_value=current))

        def interaction():
            return SimpleNamespace(user=SimpleNamespace(id=2), guild=guild, extras={})

        view = discord.ui.View()
        select = discord.ui.Select(
            custom_id="owned-source",
            options=[discord.SelectOption(label=member_label(uid), value=str(uid))],
        )
        view.add_item(select)
        first = interaction()
        await render_member_view(first, view)
        assert select.options[0].label == "SORROW"
        assert select.options[0].value == str(uid) and select.custom_id == "owned-source"
        assert await render_member_labels(first, "Owner: " + member_label(uid)) == "Owner: SORROW"
        # Same-render resolution is shared; a fresh interaction observes the new nickname.
        assert guild.fetch_member.await_count == 1
        current.display_name = "@everyone **WREN**"
        second = interaction()
        await render_member_view(second, view)
        assert "WREN" in select.options[0].label and "@everyone" not in select.options[0].label
        assert guild.fetch_member.await_count == 2
        text = await render_member_labels(second, member_label(uid))
        assert "\\*\\*WREN\\*\\*" in text
        assert select.options[0].value == str(uid)
        narrative = "Unmodified history: 123456789123456789 / **words** / @everyone"
        assert await render_member_labels(second, narrative) == narrative
        assert (
            await render_member_labels(
                SimpleNamespace(user=SimpleNamespace(id=2), guild=None, extras={}),
                member_label(uid),
            )
            == "Unavailable member"
        )

    asyncio.run(run())


def test_member_reply_acknowledges_then_preserves_private_disabled_mentions():
    async def run():
        uid = 222222222222222222
        done = False

        async def defer(**kwargs):
            nonlocal done
            assert kwargs["ephemeral"] is True
            done = True

        response = SimpleNamespace(
            is_done=lambda: done, defer=AsyncMock(side_effect=defer), send_message=AsyncMock()
        )
        current = SimpleNamespace(
            user=SimpleNamespace(id=uid, display_name="SORROW"),
            guild=None,
            extras={},
            response=response,
            edit_original_response=AsyncMock(),
        )
        await reply(current, "Player " + member_label(uid))
        assert response.defer.await_count == 1
        response.send_message.assert_not_awaited()
        result = current.edit_original_response.call_args.kwargs
        assert result["content"] == "Player SORROW"
        assert result["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
        await reply(current, "Player " + member_label(uid))
        assert response.defer.await_count == 1

    asyncio.run(run())
