"""Native choices for the original Foundation court and successor."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_succession import SuccessionService


async def open_succession(
    interaction: discord.Interaction, service: SuccessionService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["setup"] and not data["courts"]:
        await reply(
            interaction,
            "Choose a living Director of this faction who has a separate controller.",
        )
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            "open" if data["setup"] else values["choice"][0],
            judge=values["judge"][0] if data["setup"] else None,
            ideals=values.get("ideals", ""),
            account=values.get("account", ""),
        )
        return "Your original court decision was recorded."

    if data["setup"]:
        await NativeForm(
            interaction.user.id,
            "Convene the new Foundation court",
            "Choose the original fictional Director who will act for this faction.",
            [Field("judge", "Original court authority", data["courts"])],
            submit,
        ).present(interaction)
        return

    if data["complete"]:
        status = "The approved successor now holds office."
    elif data["approved"]:
        status = "The court approved the pledge. Activate the exact Handler draft."
    elif data["executed"]:
        status = "The original Handler was executed. Prepare and submit an owned successor draft."
    elif data["sentenced"]:
        status = "The court's sentence is due at the close of Off-Duty."
    else:
        status = "The court awaits its original authority's decision."
    text = "\n\n".join(
        [status] + [clean(data[k]) for k in ("ideals", "sentence", "pledge") if data[k]]
    )

    async def authorize(click: discord.Interaction) -> None:
        await asyncio.to_thread(service.get, viewer_from_interaction(click), identity)

    choices = data["choices"]
    if not choices:
        history = MemoryHistory(interaction.user.id, text, authorize)
        await reply(interaction, history.text(), history)
        return
    fields = [Field("choice", "Your actual decision", choices)]
    if choices[0][0] == "sentence":
        fields += [
            Field("ideals", "The new Foundation's ideals", paragraph=True),
            Field("account", "The actual sentence", paragraph=True),
        ]
    elif choices[0][0] == "pledge":
        fields.append(Field("account", "Your successor's own pledge", paragraph=True))
    await MemoryForm(
        interaction.user.id, "New Foundation court", text, fields, submit, authorize=authorize
    ).present(interaction)
