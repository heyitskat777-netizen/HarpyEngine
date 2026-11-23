"""A timed Harpy draft and separate private original-Girl acceptance."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_harpy_rewrite import RewriteService

TITLE = "Nothing Can Ever Be As Important As Us"


async def open_rewrite(
    interaction: discord.Interaction, service: RewriteService, channel: int, actor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.targets, viewer_from_interaction(interaction), channel, actor
    )
    if not data["targets"]:
        await reply(interaction, "No eligible Girl with an Intense Bond is present.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(current),
            str(current.id),
            channel,
            actor,
            data["revision"],
            values["target"][0],
            values["account"],
        )
        return "The original human facilitator can verify the encounter."

    fields = [
        Field("target", "Original Girl", tuple(data["targets"].items())),
        Field("account", "Describe the actual meeting and situation", paragraph=True),
    ]
    form = NativeForm(interaction.user.id, TITLE, "Choose the original Girl.", fields, submit)
    await reply(interaction, form.text(), form)


async def open_rewrite_response(
    interaction: discord.Interaction, service: RewriteService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step, slots = data["step"], data["slots"]
    choices = {
        "verify": (("yes", "They are alone and no help is coming"), ("no", "Decline")),
        "authorize": (("yes", "Open the selected Identities"), ("no", "Decline")),
        "apply": (("yes", "Apply these actual edits"), ("no", "Decline")),
    }
    if step == "verify":
        text = clean(data["account"])
        fields = [
            Field("allow", "Original encounter", choices[step]),
            Field("account", "Record the factual review", paragraph=True, required=False),
        ]
    elif step == "authorize":
        text = (
            "Choose what the original Harpy may see and edit. You can review the draft afterward."
        )
        fields = [Field("allow", "Your decision", choices[step])]
        if slots:
            fields.append(
                Field(
                    "slots",
                    "Your authorized Identities",
                    tuple(slots.items()),
                    minimum=0,
                    maximum=len(slots),
                    required=False,
                )
            )
    elif step == "draft":
        text = f"Submit your changes before the window expires. {data['remaining']} seconds remain."
        fields = [Field(key, f"New name for {old}", required=False) for key, old in slots.items()]
    elif step == "apply":
        text = "\n".join(
            f"{clean(slots[key])} → {clean(new)}" for key, new in data["changes"].items()
        )
        fields = [Field("allow", "Your decision", choices[step])]
    else:
        text = "The one-minute window expired."
        fields = [Field("close", "Close expired edit", (("yes", "Close edit"),))]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            step,
            allow=values["allow"][0] == "yes" if "allow" in values else None,
            selected=values.get("slots", ()),
            changes={key: values[key] for key in slots if values.get(key)}
            if step == "draft"
            else None,
            account=values.get("account", ""),
        )
        return "The original private choice is saved."

    form = NativeForm(interaction.user.id, TITLE, text, fields, submit)
    await reply(interaction, form.text(), form)
