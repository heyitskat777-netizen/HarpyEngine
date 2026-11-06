"""Original Handler identifies a real leader and later settles the actual opportunity."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_leader import LeaderService


async def open_leader(
    interaction: discord.Interaction, service: LeaderService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] not in ("identify", "available"):
        embeds = [
            discord.Embed(title=label, description=clean(data[key]))
            for key, label in (("account", "Original opportunity"), ("response", "Actual outcome"))
            if data.get(key)
        ]
        content = "**Rebel leader opportunity — " + clean(data["phase"]) + "**"
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content=content,
                embeds=embeds,
                view=None,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            await interaction.response.send_message(
                content,
                embeds=embeds,
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        return
    if data["phase"] == "identify":
        if not data["candidates"]:
            await reply(
                interaction,
                "Introduce an actual living NPC leader or member of this group, then reopen.",
            )
            return
        fields = [
            Field(
                "leader",
                "Actual living leader",
                tuple((x["id"], x["label"]) for x in data["candidates"]),
            )
        ]
    else:
        fields = [
            Field(
                "action",
                "Your opportunity",
                (
                    ("destroy", "Dismantle group after its leader's actual death"),
                    ("forgo", "Forgo this opportunity"),
                ),
            )
        ]
    fields.append(Field("account", "Actual opportunity or group outcome", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            "identify" if data["phase"] == "identify" else values["action"][0],
            values["account"],
            leader=values["leader"][0] if data["phase"] == "identify" else "",
        )
        return (
            "Actual leader opportunity saved. A future kill remains optional; "
            "destruction needs its real outcome."
        )

    form = NativeForm(
        interaction.user.id,
        "Rebel leader opportunity — " + data["group"],
        "Identify the real leader. Defeat them in play before claiming group destruction; "
        "the opportunity can remain available for later.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
