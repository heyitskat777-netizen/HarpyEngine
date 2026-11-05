"""Real confirmation callbacks retain the next owned form and then finish once."""

import asyncio
from unittest.mock import AsyncMock

from test_battle_service import prepared
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_battle import open_declaration, open_npc_damage
from girlframe.discord_adapter.onboarding import reply


def test_confirmation_keeps_explicit_next_form_and_only_terminal_reply_removes_controls():
    async def run():
        terminal = AsyncMock(return_value="Actual terminal result")
        second = NativeForm(
            2,
            "Next step",
            "Still needs its owner's confirmation",
            [Field("account", "Describe")],
            terminal,
        )

        async def advance(interaction, values):
            await reply(interaction, second.text(), second)
            return None

        first = NativeForm(
            2, "First step", "Choose", [Field("option", "Choose", (("actual", "Actual"),))], advance
        )
        first.values["option"] = ("actual",)
        interaction = current(2, 710)
        await first.confirm.callback(interaction)
        assert interaction.edit_original_response.await_count == 1
        assert interaction.edit_original_response.call_args.kwargs["view"] is second
        assert first.completed and not second.completed and terminal.await_count == 0
        assert not await second.interaction_check(current(3, 711))
        second.values["account"] = "Actual player-selected detail"
        final = current(2, 712)
        await second.confirm.callback(final)
        assert terminal.await_count == 1 and second.completed
        assert final.edit_original_response.call_args.kwargs["view"] is None
        assert final.edit_original_response.call_args.kwargs["content"] == "Actual terminal result"

    asyncio.run(run())


def test_real_battle_prepare_button_preserves_actual_asset_screen_before_proposal(ledger):
    game, _, _, battle, data, declaration = prepared(ledger)
    before = state(game)

    async def run():
        initial = current(2, 720)
        initial.channel_id = 900
        await initial.response.defer(ephemeral=True)
        await open_declaration(initial, battle)
        menu = initial.edit_original_response.call_args.kwargs["view"]
        menu.values.update(
            actor=(declaration.actor.token,),
            target=(declaration.target.token,),
            play=("all_out_assault",),
        )
        advance = current(2, 721)
        await menu.confirm.callback(advance)
        details = advance.edit_original_response.call_args.kwargs["view"]
        assert isinstance(details, NativeForm) and details.title == "Declare actual battle"
        assert not details.completed and menu.completed
        assert {x.key for x in details.fields} == {"asset", "target_asset", "account"}
        assert state(game) == before and game.dice.calls == 0
        details.values.update(
            asset=(declaration.attacking_asset,),
            target_asset=(declaration.target_asset,),
            account=declaration.account,
        )
        final = current(2, 722)
        await details.confirm.callback(final)
        assert "opening/reach review" in final.edit_original_response.call_args.kwargs["content"]
        assert state(game).facts[-1]["kind"] == "battle_context"
        assert game.dice.calls == 0

    asyncio.run(run())


def test_real_npc_consequence_selection_preserves_details_until_actual_source_commit(ledger):
    from test_battle_npc import source

    game, handler, grant, service, row, target, _ = source(ledger)
    before = state(game)

    async def run():
        initial = current(1, 730)
        await initial.response.defer(ephemeral=True)
        await open_npc_damage(initial, service, row["id"])
        menu = initial.edit_original_response.call_args.kwargs["view"]
        menu.values["effect"] = ("injure_tag",)
        next_step = current(1, 731)
        await menu.confirm.callback(next_step)
        details = next_step.edit_original_response.call_args.kwargs["view"]
        assert isinstance(details, NativeForm) and menu.completed and not details.completed
        assert state(game) == before
        details.values.update(account="Actual source injury", tag="Actual source wound")
        await details.confirm.callback(current(1, 732))

    asyncio.run(run())
    npc = next(x for x in state(game).world.npcs if x.id == target.entity)
    assert npc.alive and npc.tags[-1].label == "Actual source wound"
    assert handler.get(__import__("test_ledger").ADMIN, grant)["grant"]["state"] == "complete"
