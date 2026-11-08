"""Choose actual NPCs and real departures; completed details remain privately readable."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_budget_departures import Departure
from girlframe.engine.m3_world_state import NPC_JOBS
from girlframe.services.m3_budget_departures import DepartureService


async def open_departures(
    interaction: discord.Interaction,
    service: DepartureService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] == "complete":
        record = data["record"]
        names = {x["id"]: x["name"] for x in record["originals"]}
        outcomes = "\n".join(
            names[x["actor"]["entity"]]
            + " — "
            + ("died" if x["outcome"] == "die" else "quit; now " + ", ".join(x["jobs"]))
            for x in record["departures"]
        )
        embeds = [
            discord.Embed(title="Actual departures", description=clean(outcomes)),
            discord.Embed(title="Original source account", description=clean(record["account"])),
        ]
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content="**NPC Bond departures — saved**",
                embeds=embeds,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(
                "**NPC Bond departures — saved**",
                embeds=embeds,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        return
    if len(data["candidates"]) < 3:
        await reply(
            interaction,
            "This consequence needs three to five actual living NPC Bonds. "
            "Fewer than three supported ordinary NPCs are currently available; "
            "the source stays pending. No substitute people are created.",
        )
        return
    available = {x["id"]: x for x in data["candidates"]}

    async def select(current: discord.Interaction, values: dict[str, Any]) -> None:
        selected = values["people"]
        fields = []
        for index, identity in enumerate(selected):
            npc = available[identity]
            options = (
                (("quit", "Quit current work"), ("die", "Die"))
                if npc["employment"] != "unemployed"
                else (("die", "Die"),)
            )
            fields.extend(
                [
                    Field("outcome:" + str(index), npc["label"] + " — outcome", options),
                    Field(
                        "jobs:" + str(index),
                        npc["label"] + " — actual jobs after quitting",
                        tuple(
                            (x, x.replace("_", " ").title()) for x in NPC_JOBS if x != "director"
                        ),
                        0,
                        len(NPC_JOBS) - 1,
                        required=False,
                    ),
                ]
            )
        fields.append(Field("account", "Describe the actual departures", paragraph=True))

        async def submit(final: discord.Interaction, answers: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.apply,
                viewer_from_interaction(final),
                str(final.id),
                data["id"],
                data["revision"],
                data["work_revision"],
                tuple(
                    Departure(
                        actor=ActorRef(kind="npc", entity=npcid),
                        outcome=answers["outcome:" + str(i)][0],
                        jobs=answers.get("jobs:" + str(i), ()),
                    )
                    for i, npcid in enumerate(selected)
                ),
                answers["account"],
            )
            return (
                "Actual NPC departures saved once. "
                "Reopen the original source for its private record."
            )

        form = NativeForm(
            current.user.id,
            "Actual NPC Bond departures",
            "Choose each real outcome. Quitting ends employment with the chosen current jobs; "
            "death ends only this actual NPC. Existing Tags, relationships and history remain.",
            fields,
            submit,
        )
        await reply(current, form.text(), form)

    form = NativeForm(
        interaction.user.id,
        "Budget Endgame — NPC Bonds",
        "Choose three to five distinct actual related NPCs, then specify their real outcomes. "
        "Nothing changes until the final confirmation.",
        [
            Field(
                "people",
                "Actual living NPC Bonds",
                tuple((x["id"], x["label"]) for x in data["candidates"]),
                3,
                min(5, len(available)),
            )
        ],
        select,
    )
    await reply(interaction, form.text(), form)
