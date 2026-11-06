"""Owner-only secret installation and actual cockpit Bond/Tag controls."""

import asyncio
from typing import Any, Literal

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine import m3_home as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_home import HomeService
from girlframe.services.onboarding import WorkflowError


async def open_home(interaction: discord.Interaction, service: HomeService) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"]:
        raise WorkflowError("No reviewed Home, of a Sort source is available")
    if data["suspended"]:
        await reply(interaction, "Home, of a Sort is suspended. Restore the original installation.")
        return
    if not data["owned"]:

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.buy,
                viewer_from_interaction(current),
                str(current.id),
                data["revision"],
                ActorRef.model_validate(data["actor"]),
                data["frame"],
                tuple(values["items"]),
                values["account"],
                values["donor"][0] if data["donors"] else None,
            )
            return (
                "Your three secret items are installed. "
                "Reopen Home when someone actually occupies your Frame with you."
            )

        await NativeForm(
            interaction.user.id,
            f"Home, of a Sort — {data['kind'].replace('_', ' ').title()}, "
            f"{data['price']} Permissions",
            "Choose exactly three secret installed items. "
            "The items and installation remain private to you.",
            (
                [Field("donor", "Actual LEGION donor Frame", tuple((x, x) for x in data["donors"]))]
                if data["donors"]
                else []
            )
            + [
                Field("items", "Exactly three secret installed items", rules.ITEMS, 3, 3),
                Field("account", "Record your actual private installation", paragraph=True),
            ],
            submit,
        ).present(interaction)
        return
    if not data["others"]:
        await reply(
            interaction,
            "Your secret Home is installed. Both original people must actually occupy "
            "this exact Frame before using it.",
        )
        return

    async def choose(current: discord.Interaction, operation: str) -> None:
        await open_effect(current, service, "bond" if operation == "bond" else "reject")

    options: tuple[tuple[str, str], ...] = (("bond", "Use an installed item to deepen our Bond"),)
    if data["tags"]:
        options += (("reject", "Reject my own Tag without taking action"),)
    await Picker(
        interaction.user.id, "Home, of a Sort — actual shared cockpit", options, choose
    ).show(interaction)


async def open_effect(
    interaction: discord.Interaction, service: HomeService, operation: Literal["bond", "reject"]
) -> None:
    data = await asyncio.to_thread(service.menu, viewer_from_interaction(interaction))
    if not data["available"] or data["suspended"] or not data["owned"] or not data["others"]:
        raise WorkflowError("Restore the original Home and actual same-Frame occupancy")
    fields = [
        Field(
            "other",
            "Actual other original person in your Frame",
            tuple((x["actor"]["entity"], x["label"]) for x in data["others"]),
        )
    ]
    if operation == "bond":
        fields.append(
            Field(
                "item",
                "Use one of your secret installed items",
                tuple((x, dict(rules.ITEMS)[x]) for x in data["items"]),
            )
        )
    else:
        if not data["tags"]:
            raise WorkflowError("No own Tag may currently be rejected through Home")
        fields.append(
            Field(
                "tag",
                "Reject your actual own Tag",
                tuple((x["id"], x["label"]) for x in data["tags"]),
            )
        )
    fields.append(Field("account", "Describe this actual owned use", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        other = next(x for x in data["others"] if x["actor"]["entity"] == values["other"][0])
        await asyncio.to_thread(
            service.use,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            ActorRef.model_validate(other["actor"]),
            other["physical"],
            operation=operation,
            account=values["account"],
            item=values["item"][0] if operation == "bond" else None,
            tag=values["tag"][0] if operation == "reject" else None,
        )
        return (
            "Your actual Bond deepened."
            if operation == "bond"
            else "Your Tag is rejected without taking action."
        )

    await NativeForm(
        interaction.user.id,
        "Home, of a Sort",
        "Your original private installation and actual shared cockpit "
        "are checked again when you confirm. "
        "Mentor and original Tag-setter restrictions still apply.",
        fields,
        submit,
    ).present(interaction)
