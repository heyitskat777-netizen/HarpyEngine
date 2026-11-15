"""Current server names on the real native Status card; identity values stay stable."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from girlframe.discord_adapter.handler_setup import RankView


def test_status_current_nicknames_preserve_selection_values_order_and_owner():
    async def run():
        handler = 111111111111111111
        peer = 222222222222222222
        members = {
            handler: SimpleNamespace(id=handler, display_name="SORROW", name="old-account"),
            peer: SimpleNamespace(id=peer, display_name="WREN", name="other-account"),
        }
        active = {}

        async def fetch_member(uid):
            assert active["interaction"].response.defer.await_count == 1
            return members[uid]

        guild = SimpleNamespace(get_member=lambda uid: members.get(uid), fetch_member=fetch_member)

        def current(user):
            value = SimpleNamespace(
                user=members.get(user, SimpleNamespace(id=user, display_name="Unrelated")),
                guild=guild,
                guild_id=333333333333333333,
                response=SimpleNamespace(
                    is_done=lambda: False,
                    edit_message=AsyncMock(),
                    send_message=AsyncMock(),
                    defer=AsyncMock(),
                ),
                edit_original_response=AsyncMock(),
            )
            active["interaction"] = value
            return value

        service = Mock()
        prepared = {
            "pilots": {
                handler: {"callsign": "Saved character callsign", "revision": 1},
                peer: {"callsign": "Another saved character", "revision": 1},
            }
        }
        view = RankView(service, handler, prepared)
        opening = current(handler)
        await view.render(opening)
        select = next(x for x in view.children if isinstance(x, discord.ui.Select))
        assert [x.label for x in select.options] == ["SORROW", "WREN"]
        assert [x.value for x in select.options] == [str(handler), str(peer)]
        assert all(str(handler) not in (x.description or "") for x in select.options)

        members[handler].display_name = "SORROW UPDATED"
        view.order = [handler, peer]
        reviewed = current(handler)
        await view.render(reviewed)
        message = reviewed.edit_original_response.call_args.kwargs
        reviewed.response.defer.assert_awaited_once()
        assert "1. SORROW UPDATED — Ace" in message["content"]
        assert "2. WREN — Dog" in message["content"]
        assert "Handler is outside" not in message["content"]
        assert str(handler) not in message["content"] and str(peer) not in message["content"]
        assert message["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
        assert view.order == [handler, peer] and view.prepared == prepared
        assert not await view.interaction_check(current(444444444444444444))
        service.roster.assert_not_called()

    asyncio.run(run())


def test_complete_status_with_25_long_nicknames_fits_without_losing_members():
    async def run():
        identities = [111111111111111111 + i for i in range(25)]
        members = {
            uid: SimpleNamespace(id=uid, display_name=f"{index:02d}" + "*" * 30)
            for index, uid in enumerate(identities)
        }
        guild = SimpleNamespace(fetch_member=AsyncMock(side_effect=lambda uid: members[uid]))
        interaction = SimpleNamespace(
            user=members[identities[0]],
            guild=guild,
            extras={},
            response=SimpleNamespace(is_done=lambda: False, defer=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        view = RankView(
            Mock(),
            identities[0],
            {"pilots": {uid: {"callsign": "saved", "revision": 1} for uid in identities}},
        )
        view.order = identities.copy()
        await view.render(interaction)
        result = interaction.edit_original_response.call_args.kwargs
        assert result["content"] is None
        text = result["embed"].description
        assert 2000 < len(text) <= 4096
        for index in range(25):
            assert f"{index + 1}. {index:02d}" in text
        assert "— Ace" in text and "— Dog" in text
        assert view.order == identities
        assert all(str(uid) not in text for uid in identities)
        assert result["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()

    asyncio.run(run())
