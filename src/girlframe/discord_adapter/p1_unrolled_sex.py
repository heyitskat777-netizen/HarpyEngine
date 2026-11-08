"""Private original Animal Tag authoring for a genuine non-rolling Sex source."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_memory_pages import MemoryForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_tasks(
    interaction: discord.Interaction,
    game: GameService,
    source_id: str,
    *,
    source_kind: str | None = None,
) -> None:
    from girlframe.services.m3_bonded import BondedService
    from girlframe.services.p1_unrolled_sex import give

    if source_kind == "changeling_am":
        from girlframe.services.m3_changeling_sex import ChangelingSexService

        data = await asyncio.to_thread(
            ChangelingSexService(game).view_am, viewer_from_interaction(interaction), source_id
        )
    elif source_kind is None:
        data = await asyncio.to_thread(
            BondedService(game).view, viewer_from_interaction(interaction), source_id
        )
    else:
        raise WorkflowError("Use the actual existing source kind, not a borrowed source")
    pending = [x for x in data.get("unrolled_gender", ()) if x["pending"]]
    if not pending:
        raise WorkflowError("No actual source-owned Animal gift awaits your answer")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            give,
            game,
            viewer_from_interaction(current),
            str(current.id),
            values["gift"][0],
            data["revision"],
            values["tag"],
        )
        return "Your actual source-owned Tag is saved. Reopen the original source to continue."

    instructions = "Give your real non-Animal partner one ordinary Tag. No dice or Heat are added."
    fields = [
        Field(
            "gift",
            "Actual source gift",
            tuple((x["id"], "Actual original partner") for x in pending),
        ),
        Field("tag", "Your actual Tag", paragraph=True),
    ]
    if source_kind == "changeling_am":
        from girlframe.discord_adapter.ledger import clean

        instructions += "\n\n" + clean(data["body"]["account"])
        instructions += "\n\n" + "\n\n".join(
            clean(performance["account"]) for performance in data["performances"]
        )
        instructions += "\n\nYour actual source remains pending until its mandatory Tag is given."

        async def access(current: discord.Interaction) -> None:
            await asyncio.to_thread(
                ChangelingSexService(game).view_am, viewer_from_interaction(current), source_id
            )

        form: NativeForm = MemoryForm(
            interaction.user.id,
            "Actual Animal's Tag",
            instructions,
            fields,
            submit,
            authorize=access,
        )
    else:
        form = NativeForm(interaction.user.id, "Actual Animal's Tag", instructions, fields, submit)
    await reply(interaction, form.text(), form)
