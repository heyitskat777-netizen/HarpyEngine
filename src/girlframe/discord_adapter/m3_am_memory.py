"""Private OOC recovery of a committed fictional AM memory loss."""

import asyncio
import io
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.services.m3_am_memory import MemoryService


async def open_memory(
    interaction: discord.Interaction, service: MemoryService, identity: str
) -> None:
    value = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    contents = (
        "All memories held through this operation are erased."
        if value["scope"] == "all"
        else "The following actual memories are erased:\n" + "\n".join(value["memories"])
    )
    text = (
        f"{value['actor']}: Just Code memory effect\n{contents}\n"
        f"Through state revision {value['through_revision']}; source event {value['event']}.\n"
        "This is an OOC record of lost fictional recall. It does not restore the memories. "
        "Later genuinely learned memories remain available. Historical events, resources, "
        "Identity marks and other people's knowledge remain intact.\n"
    )
    attachment = discord.File(io.BytesIO(text.encode()), filename="am-memory-" + identity + ".txt")
    kwargs: dict[str, Any] = dict(
        content="Your original private Just Code memory effect.",
        file=attachment,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
