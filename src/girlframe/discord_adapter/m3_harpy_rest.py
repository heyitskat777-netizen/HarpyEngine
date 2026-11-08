"""Actual original Harpy chooses her hide; the actual judge reviews its factual route."""

import asyncio
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


async def open_rest(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    if not data.get("harpy_off_duty"):
        raise WorkflowError("Recover this actual original Harpy's Off-Duty choice.")
    if data["kind"] == "harpy_off_duty_route":
        from girlframe.discord_adapter.m3_harpy_defeat import open_task
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        await open_task(
            interaction, HarpyDefeatService(game.store, game=game), "harpy_route", data["route"]
        )
        return
    if data["kind"] != "harpy_off_duty_hide":
        raise WorkflowError("Resume the actual source-specific hide or route review.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if values["confirm"][0] != "yes":
            raise WorkflowError("Confirm your actual owned hide and Identity adjustment.")
        names = [x.strip() for x in values.get("identities", "").splitlines() if x.strip()]
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            ChoiceAnswer(
                flag=True,
                text=values["account"],
                fields={"identities": json.dumps(names), "navigation": values["navigation"]},
            ),
        )
        return (
            "Your actual Voidspace hide awaits its source judge's navigation review. "
            "Recovery follows approval."
        )

    protected = ", ".join(data["protected_identities"]) or "none"
    form = NativeForm(
        interaction.user.id,
        "Harpy: hide in Voidspace",
        "Choose your ordinary Identities, one per line, and describe this actual hide's route. "
        "Approval repairs your actual current Assets and clears the chosen Identity marks. "
        "Protected retained Identities remain: " + protected,
        [
            Field(
                "identities",
                "Ordinary Identity names, one per line",
                paragraph=True,
                required=False,
            ),
            Field("account", "Describe your actual Voidspace hide", paragraph=True),
            Field("navigation", "Describe your actual route into Voidspace", paragraph=True),
            Field(
                "confirm",
                "Owned adjustment and hide",
                (("yes", "Confirm my hide and Identity adjustment"),),
            ),
        ],
        submit,
    )
    form.values["identities"] = "\n".join(data["ordinary_identities"])
    await reply(interaction, form.text(), form)
