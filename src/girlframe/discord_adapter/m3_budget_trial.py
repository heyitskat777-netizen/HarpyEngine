"""Private court setup and original speakers' controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm, MemoryHistory
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_trial import TrialService


async def open_trial(
    interaction: discord.Interaction, service: TrialService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] == "setup":
        if not data["directors"]:
            await reply(
                interaction,
                "Assign a fictional Director to a joined controller outside the original Cadre.",
            )
            return

        async def setup(click: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.open,
                viewer_from_interaction(click),
                str(click.id),
                identity,
                data["revision"],
                values["director"][0],
            )
            return (
                "The original fictional Director can serve the charge through their private Inbox."
            )

        await NativeForm(
            interaction.user.id,
            "Open the Budget Endgame trial",
            "Choose the independent Director who will hear the case.",
            [Field("director", "Fictional Director", data["directors"])],
            setup,
        ).present(interaction)
        return

    status = {
        "charge": "The charge is being prepared.",
        "hearing": "The original participants can give their statements.",
        "saved": "The Cadre saved the Handler.",
        "execution_due": "The court's sentence is due at the close of Off-Duty.",
        "executed": "The sentence was carried out. An actual successor is required.",
    }[data["phase"]]
    lines = [status, data["charge"], *(x["account"] for x in data["statements"]), data["verdict"]]
    text = "\n\n".join(clean(x) for x in lines if x)

    async def authorize(click: discord.Interaction) -> None:
        await asyncio.to_thread(service.view, viewer_from_interaction(click), identity)

    if not data["options"]:
        history = MemoryHistory(interaction.user.id, text, authorize)
        await reply(interaction, history.text(), history)
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            values["choice"][0],
            values["account"],
        )
        return "Your court record is saved."

    await MemoryForm(
        interaction.user.id,
        "Original Budget trial",
        text,
        [
            Field("choice", "Your decision", data["options"]),
            Field("account", "Your statement or finding", paragraph=True),
        ],
        submit,
        authorize=authorize,
    ).present(interaction)
