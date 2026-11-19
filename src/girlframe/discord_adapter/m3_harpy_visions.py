"""Native private choices for a Harpy’s actual Visions of Infinity."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_visions import Adjustment
from girlframe.services.m3_harpy_visions import VisionsService

TITLE = "Visions of Infinity"
ADJUSTMENTS = (
    ("identity", "Give a new Identity"),
    *((f"tag:{slot}", f"Turn ordinary Identity slot {slot + 1} into a Tag") for slot in range(4)),
    ("deepen", "Deepen the Bond with your Harpy"),
    ("weaken", "Weaken the Bond with your Harpy"),
    ("remove", "Remove the Bond with your Harpy"),
)


async def open_visions(
    interaction: discord.Interaction,
    service: VisionsService,
    channel: int,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(
        service.targets, viewer_from_interaction(interaction), channel, actor
    )
    if not data["targets"]:
        await reply(interaction, "No eligible original recipient is present for this Play.")
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
        return "The original recipient’s consent is pending."

    fields = [
        Field("target", "Original recipient", tuple(data["targets"].items())),
        Field("account", "Describe how your Harpy approaches", paragraph=True),
    ]
    form = NativeForm(interaction.user.id, TITLE, "Choose an actual present Girl.", fields, submit)
    await reply(interaction, form.text(), form)


async def open_visions_response(
    interaction: discord.Interaction,
    service: VisionsService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    maximum = 8 if data["tier"] == "high" else 4
    if step == "consent":
        text = clean(data["account"])
        fields = [
            Field("choice", "Your decision", (("yes", "Allow the contact"), ("no", "Decline"))),
        ]
    elif step == "roll":
        text = f"The original Girl allowed the contact. Your Harpy has {data['heat']} Heat."
        fields = [Field("heat", "Your actual Heat spend")]
    elif step == "replace" and data["can_replace"]:
        text = "Confirm the original low result. Your new Identities would be " + ", ".join(
            clean(x) for x in data["identities"]
        )
        fields = [Field("choice", "Actual original effect", (("yes", "Apply this change"),))]
    elif step == "plan":
        text = (
            "Choose exactly eight ordered effects."
            if maximum == 8
            else "Choose up to four ordered effects."
        )
        text += " You can repeat a choice. Enter new Identity names in the same order."
        fields = [
            Field(f"effect_{index}", f"Effect {index + 1}", ADJUSTMENTS, required=maximum == 8)
            for index in range(maximum)
        ]
        fields.append(
            Field("names", "New Identity names, one per line", paragraph=True, required=False)
        )
    elif step == "confirm":
        descriptions = data["descriptions"]
        options = (("no", "Return the selection"),)
        if descriptions is None:
            text = "The original choices cannot be applied to your current sheet."
        else:
            text = "\n".join(clean(x) for x in descriptions) or "The Harpy chose zero effects."
            options = (("yes", "Apply these effects"), *options)
        fields = [Field("choice", "Your decision", options)]
    else:
        await reply(interaction, "The original saved outcome awaits its actual consequence.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        heat = values.get("heat", "").strip()
        if step == "roll" and (not heat.isascii() or not heat.isdecimal() or len(heat) > 9):
            return "Enter a whole amount of your available Heat."
        choices = None
        if step == "plan":
            selections = [
                values[f"effect_{index}"][0]
                for index in range(maximum)
                if values.get(f"effect_{index}")
            ]
            names = [name.strip() for name in values.get("names", "").splitlines() if name.strip()]
            if len(names) != selections.count("identity"):
                raise ValueError("Provide one name per new Identity choice")
            new_names = iter(names)
            selected_choices = []
            for selection in selections:
                effect, _, slot = selection.partition(":")
                selected_choices.append(
                    Adjustment.model_validate(
                        dict(
                            effect=effect,
                            slot=int(slot) if slot else None,
                            name=next(new_names) if effect == "identity" else "",
                        )
                    )
                )
            choices = tuple(selected_choices)
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            step,
            heat=int(heat) if step == "roll" else None,
            choice=values["choice"][0] == "yes" if "choice" in values else None,
            choices=choices,
        )
        return "The original private decision is saved."

    form = NativeForm(interaction.user.id, TITLE, text, fields, submit)
    await reply(interaction, form.text(), form)
