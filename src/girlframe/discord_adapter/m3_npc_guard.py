"""Original Guard weapon review and source-owned printed counter moves."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_npc_guard as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_npc_guard import GuardService


async def open_guard(interaction: discord.Interaction, service: GuardService) -> None:
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    )
    if not data["guards"]:
        await reply(
            interaction,
            "Join your Guard and the outside-Frame opponent to this scene, with known co-presence. "
            "The current adjudicator must control the Guard.",
        )
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        guard = next(
            x
            for x in data["guards"]
            if ActorRef.model_validate(x["ref"]).token == values["guard"][0]
        )

        async def submit(response: discord.Interaction, details: dict[str, Any]) -> str:
            opponent = next(
                x
                for x in guard["targets"]
                if ActorRef.model_validate(x["ref"]).token == details["opponent"][0]
            )
            await asyncio.to_thread(
                service.assess,
                viewer_from_interaction(response),
                str(response.id),
                int(response.channel_id or 0),
                ActorRef.model_validate(guard["ref"]),
                ActorRef.model_validate(opponent["ref"]),
                data["revision"],
                details["weapons"][0] == "unarmed",
                details["account"],
            )
            return "Your Guard's real weapon assessment is saved before the roll."

        form = NativeForm(
            current.user.id,
            "Guard: weapon facts",
            "Review the person's actual weapons. Missing inventory entries do not prove "
            "someone is unarmed.",
            [
                Field(
                    "opponent",
                    "Co-present opponent",
                    tuple(
                        (ActorRef.model_validate(x["ref"]).token, x["label"])
                        for x in guard["targets"]
                    ),
                ),
                Field(
                    "weapons",
                    "Actual weapons",
                    (
                        ("unarmed", "I confirm this Guard is unarmed"),
                        ("armed", "This Guard carries its recorded weapon"),
                    ),
                ),
                Field("account", "Describe the existing weapon facts", paragraph=True),
            ],
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        interaction.user.id,
        "Guard preparation",
        "Review your actual Guard's weapon facts before the opposing roll.",
        [
            Field(
                "guard",
                "Your Guard",
                tuple(
                    (ActorRef.model_validate(x["ref"]).token, x["label"]) for x in data["guards"]
                ),
            )
        ],
        choose,
    )
    await reply(interaction, form.text(), form)


async def open_counter(
    interaction: discord.Interaction, service: GuardService, parent: str, choice: str
) -> None:
    data = await asyncio.to_thread(
        service.counter, viewer_from_interaction(interaction), parent, choice
    )
    moves = (
        rules.MOVES if data["weapons"] else tuple(x for x in rules.MOVES if x[0] != "draw_weapon")
    )
    fields = [Field("move", "Printed Guard move", moves)]
    if data["weapons"]:
        fields.append(
            Field(
                "weapon",
                "If drawing: carried weapon",
                (("none", "No weapon drawn"),)
                + tuple((x["id"], x["label"]) for x in data["weapons"]),
            )
        )
    fields.append(Field("account", "Describe the performed Guard move", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        weapon = values.get("weapon", ("none",))[0]
        await asyncio.to_thread(
            service.perform_counter,
            viewer_from_interaction(current),
            str(current.id),
            parent,
            choice,
            data["revision"],
            values["move"][0],
            values["account"],
            None if weapon == "none" else weapon,
        )
        return "The Guard's performed move and its chosen consequence are saved."

    form = NativeForm(
        interaction.user.id,
        "Guard counter: " + data["label"],
        "Perform a printed move with this original body. "
        "This creates no NPC dice or invented damage.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
