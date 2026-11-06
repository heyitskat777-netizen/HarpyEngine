"""Private original Handler offer and affected-player retirement consent."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_void_retirement import StipendService


async def open_offer(
    interaction: discord.Interaction, service: StipendService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] in ("accepted", "declined") or (
        data["phase"] == "offered" and interaction.user.id != data["girl"]
    ):
        embeds = [
            discord.Embed(title=label, description=clean(data[key]))
            for key, label in (
                ("account", "Original retirement offer"),
                ("response", "Player response"),
            )
            if data.get(key)
        ]
        content = "**Retirement with stipend — " + clean(data["phase"]) + "**"
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
    fields = (
        [
            Field(
                "girl",
                "Girl offered retirement",
                tuple((str(x["id"]), x["label"]) for x in data["candidates"]),
            )
        ]
        if data["phase"] == "nominate"
        else [
            Field(
                "response",
                "Your choice",
                (("accept", "Accept retirement with stipend"), ("decline", "Decline and continue")),
            )
        ]
    )
    fields.append(Field("account", "Your actual offer or response", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            "nominate" if data["phase"] == "nominate" else values["response"][0],
            values["account"],
            girl=int(values["girl"][0]) if data["phase"] == "nominate" else None,
        )
        return (
            f"Retirement offer saved: {result['phase']}. "
            "Reopen your requests for the original details."
        )

    form = NativeForm(
        interaction.user.id,
        "Void Endgame — retirement with stipend",
        "Only the affected player accepts or declines. Acceptance ends this original Girl’s career "
        "with a saved archive and stipend; no Permissions are charged. "
        + (data.get("account") or ""),
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
