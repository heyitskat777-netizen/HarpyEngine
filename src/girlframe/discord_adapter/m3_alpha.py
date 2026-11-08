"""Real asset damage and owned counter-Play controls for Brutalize."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.m2_game import GameService


async def open_alpha_choice(
    interaction: discord.Interaction, game: GameService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(game.decision, viewer, identity)
    if data["kind"].startswith("battle_"):
        from girlframe.discord_adapter.m3_battle import open_battle

        await open_battle(interaction, game, identity)
        return
    detail = data["alpha"]
    if data["kind"] == "alpha_counter_play" and detail.get("npc"):
        from girlframe.discord_adapter.m3_npc_guard import open_counter
        from girlframe.services.m3_npc_guard import GuardService

        await open_counter(interaction, GuardService(game), data["parent"], identity)
        return
    if data["kind"] == "alpha_damage":
        fields = [
            Field(
                "asset",
                "Damage one actual Girl Asset",
                tuple((x["id"], x["label"]) for x in detail["assets"]),
            )
        ]
        text = (
            "The actual selected Girl Asset is damaged. "
            "This result also applies Broken or Helpless."
        )
    elif data["kind"] == "alpha_npc_damage":
        high = data["result"]["tier"] == "high"
        fields = [] if high else [Field("injury", "The actual injury you inflict", paragraph=True)]
        text = (
            "The actual NPC is killed."
            if high
            else ("Describe the actual injury. This NPC also becomes Broken relative to you.")
        )
    elif data["kind"] == "alpha_npc_mercy":
        fields = [
            Field(
                "choice",
                "Actually reviewed unarmed NPC",
                (
                    ("spare", "Spare the NPC"),
                    ("kill", "Kill the unarmed NPC anyway"),
                ),
            )
        ]
        text = (
            "Their actual one counter opportunity has ended. Choose the printed optional outcome."
        )
    elif data["kind"] == "alpha_low":
        options = [("pass", "Pass this one opportunity")]
        if detail["can_counter"]:
            play = "a printed Guard Play" if detail.get("npc") else "Keep Your Head"
            options.extend(
                (
                    ("counter_broken", "Make " + play + "; then leave them Broken"),
                    ("counter_only", "Make " + play + " without Broken"),
                )
            )
        fields = [Field("choice", "Your actual counter opportunity", tuple(options))]
        text = (
            "The supported counter is a real owned Play against this pressure. "
            "No effect applies before it completes."
        )
    else:
        sheet = await asyncio.to_thread(game.sheet, viewer)
        from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
        from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
        from girlframe.services.m3_dampener import DampenerService

        dampener_controls = await dampener_fields(interaction, DampenerService(game))
        from girlframe.discord_adapter.m3_nightmare import keep_heat, keep_info
        from girlframe.services.m3_nightmare import NightmareService

        nightmare = await keep_info(interaction, NightmareService(game))
        available = sheet["heat"]
        fields = [
            Field("context", "Your actual counter under this pressure", paragraph=True),
            Field(
                "heat",
                "Heat to spend",
                tuple((str(n), str(n)) for n in keep_heat(nightmare, available)),
            ),
        ]
        text = (
            "Make the actual source-bound Keep Your Head counter. "
            "Its roll and required choices must finish."
        )
        if nightmare:
            text += " Nightmare Core uses Void Assets and no Heat; terrifying is established."
        fields.extend(dampener_controls)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if data["kind"] == "alpha_counter_play":
            result = await asyncio.to_thread(
                game.begin,
                viewer_from_interaction(current),
                str(current.id),
                data["channel"],
                sheet["revision"],
                PlayInput(
                    play="keep_your_head",
                    heat=int(values["heat"][0]),
                    dampener_modifier=dampener_modifier(values),
                    context=values["context"],
                    trigger_confirmed=True,
                    parent=data["parent"],
                ),
            )
            return (
                "Actual counter prepared. Continue its owned choices after chat lock confirmation. "
                + str(result["action_id"])
            )
        if data["kind"] == "alpha_npc_damage":
            response = ChoiceAnswer(
                options=("kill" if high else "injure",), text="" if high else values["injury"]
            )
        else:
            choice = values["asset"][0] if data["kind"] == "alpha_damage" else values["choice"][0]
            response = ChoiceAnswer(options=(choice,))
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            response,
        )
        return "Your actual Brutalize response is saved. Immediate consequences remain required."

    form = NativeForm(viewer.user_id, "Brutalize — owned response", text, fields, submit)
    await reply(interaction, form.text(), form)
