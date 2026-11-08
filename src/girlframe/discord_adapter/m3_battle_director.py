"""Owned Director body consequences and separately accepted replacement role setup."""

import asyncio
from typing import Any
from uuid import uuid4

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_battle_director import DirectorService


async def open_director(
    interaction: discord.Interaction, service: DirectorService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] == "resolved":
        await reply(interaction, "This actual Director consequence is resolved.")
        return
    if data["kind"] == "director_replacement":
        if data["role_offer"]:
            await reply(
                interaction,
                "The actual new Director role awaits its invited human's response in requests.",
            )
            return
        if not data["members"] or not data["locations"]:
            await reply(
                interaction,
                "A real different member and recorded location are needed for this new Director.",
            )
            return

        async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
            location = next(x for x in data["locations"] if x["id"] == values["location"][0])
            npc = Npc(
                id="director:" + str(uuid4()),
                name=values["name"],
                jobs=("director",),
                detail=values["detail"],
                controller=int(values["controller"][0]),
                cell=tuple(location["cell"]),
            )
            await asyncio.to_thread(
                service.offer,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                npc,
            )
            return (
                "Actual new Director setup offered. The invited human must accept their own role."
            )

        form = NativeForm(
            interaction.user.id,
            "Required new Director",
            "Create a distinct role without inheriting the dead body.",
            [
                Field("name", "New Director name"),
                Field("detail", "Actual appearance and defining detail", paragraph=True),
                Field(
                    "controller",
                    "Invite a different real human",
                    tuple((str(x["id"]), x["label"]) for x in data["members"]),
                ),
                Field(
                    "location",
                    "Actual new Director location",
                    tuple((x["id"], x["name"]) for x in data["locations"]),
                ),
            ],
            propose,
        )
        await reply(interaction, form.text(), form)
        return

    async def act(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["choice"][0],
            values["account"],
        )
        return "The actual Director-owned replacement effect is saved."

    form = NativeForm(
        interaction.user.id,
        "Director: actual body consequence",
        data["label"],
        [
            Field(
                "choice",
                "Choose your printed Handler-rule effect",
                (
                    ("opportunity", "Offer an actual opportunity"),
                    ("chance_to_act", "Offer a real chance to act"),
                    ("weakness", "Show an actual weakness"),
                    ("injury", "Suffer an injury and survive"),
                    ("death", "This actual Director dies"),
                ),
            ),
            Field("account", "Describe your actual consequence", paragraph=True),
        ],
        act,
    )
    await reply(interaction, form.text(), form)
