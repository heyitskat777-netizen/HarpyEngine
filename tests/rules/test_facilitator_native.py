"""One native human scene-ruling journey, with real services and private saved readback."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game

from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.p1_facilitator import open_request, register_facilitator
from girlframe.services.p1_facilitator import FacilitatorService


def interaction(viewer, key):
    current = MagicMock()
    current.user = MagicMock(spec=discord.Member)
    current.user.id = viewer.user_id
    current.user.roles = []
    current.user.guild_permissions = discord.Permissions(administrator=viewer.is_administrator)
    current.guild_id, current.channel_id, current.id = viewer.guild_id, 900, key
    current.response.is_done.return_value = False

    async def defer(**kwargs):
        current.response.is_done.return_value = True

    current.response.defer = AsyncMock(side_effect=defer)
    current.response.send_message = AsyncMock()
    current.edit_original_response = AsyncMock()
    return current


def test_native_scene_request_share_rule_resume_and_saved_readback(ledger):
    game, _, _, dice = setup_game(ledger)
    service = FacilitatorService(game)
    service.configure(ADMIN, "native-human-facilitator", "user", ADMIN.user_id)
    reason = "PRIVATE_REQUEST: Is the abandoned light still visible? " + "detail " * 70
    ruling = "PRIVATE_RULING: The light is visible; no mechanical effect. " + "detail " * 70

    async def run():
        tree = MagicMock()
        register_facilitator(tree, PLAYER.guild_id, game)
        group = tree.add_command.call_args.args[0]
        create = interaction(PLAYER, "native-request")
        await group.get_command("request").callback(create)
        form = create.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        source = next(value for value, _ in form.fields[0].options if value.startswith("scene:"))
        rule = form.fields[1].options[0][0]
        form.values.update(source=(source,), rule=(rule,), shared=("no",), reason=reason)
        await form.confirm.callback(create)
        assert form.completed
        identity = service.tasks(PLAYER)[0]["id"]

        # Opening the real native view respects the original owner's sharing choice.
        withheld = interaction(ADMIN, "native-withheld")
        await open_request(withheld, game, identity)
        packet = withheld.response.send_message.call_args.kwargs
        assert packet["ephemeral"] and not packet["allowed_mentions"].everyone
        assert reason not in "".join(embed.description for embed in packet["embeds"])
        assert "withheld" in packet["embeds"][0].description
        assert service.tasks(OTHER) == []

        async def choose(viewer, key, operation, adapter="blocked", text=""):
            current = interaction(viewer, key)
            await open_request(current, game, identity)
            form = current.response.send_message.call_args.kwargs["view"]
            assert operation in dict(form.fields[0].options)
            form.values.update(operation=(operation,), adapter=(adapter,), reason=text)
            await form.confirm.callback(current)
            assert form.completed
            return current

        await choose(PLAYER, "native-share", "share")
        assert service.view(ADMIN, identity)["request"]["reason"] == reason
        await choose(ADMIN, "native-rule", "rule", "fiction_only", ruling)
        pending = service.view(PLAYER, identity)["request"]
        assert pending["status"] == "awaiting_owned_effect"
        assert pending["source_kind"] == "scene" and not pending["mandatory"]
        await choose(PLAYER, "native-resume", "resume", "fiction_only")
        assert service.tasks(PLAYER) == []
        assert service.view(PLAYER, identity)["request"]["status"] == "resolved"

        # Reopening persisted work shows complete text rather than the form's 180-char preview.
        saved = interaction(PLAYER, "native-saved")
        await saved.response.defer(ephemeral=True)
        await open_request(saved, game, identity)
        packet = saved.edit_original_response.call_args.kwargs
        assert packet["content"] == "Saved adjudication: resolved" and packet["view"] is None
        assert [embed.description for embed in packet["embeds"]] == [clean(reason), clean(ruling)]
        assert not packet["allowed_mentions"].everyone
        assert dice.calls == 0

    asyncio.run(run())
