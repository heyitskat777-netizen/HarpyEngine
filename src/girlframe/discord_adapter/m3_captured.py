"""Private original Captured! decisions through native Discord controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_captured import HIGH, MID, CapturedService

TITLE = "Captured!"


async def open_capture(
    interaction: discord.Interaction, service: CapturedService, channel: int, captor: ActorRef
) -> None:
    data = await asyncio.to_thread(
        service.menu, viewer_from_interaction(interaction), channel, captor
    )
    if not data["targets"]:
        await reply(interaction, "No eligible original Girl is present at this Rebel base.")
        return

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.start,
            viewer_from_interaction(click),
            str(click.id),
            channel,
            captor,
            data["revision"],
            values["subject"][0],
            values["account"],
        )
        return "The original Girl can confirm the actual capture."

    fields = [
        Field("subject", "Original Girl", tuple(data["targets"].items())),
        Field("account", "Describe how the actual capture occurred", paragraph=True),
    ]
    form = NativeForm(
        interaction.user.id, TITLE, "Record the captured original body.", fields, submit
    )
    await reply(interaction, form.text(), form)


async def open_capture_choice(
    interaction: discord.Interaction, service: CapturedService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    step = data["step"]
    if step == "low_review" and not data["can_stage_low"]:
        await reply(
            interaction,
            "The original low roll is saved. Actual Ancillary conversion is pending.",
        )
        return
    if step == "consent":
        text = clean(data["account"])
        fields = [
            Field("choice", "Original capture", (("accept", "Confirm"), ("decline", "Decline"))),
        ]
    elif step == "roll":
        text = (
            "No Heat can be spent on this roll."
            if data["no_heat"]
            else f"You have {data['heat']} Heat."
        )
        if data["room_account"]:
            text = clean(data["room_account"]) + "\n\n" + text
        fields = (
            [Field("heat", "Actual Heat to spend")]
            if not data["no_heat"]
            else [Field("zero", "Roll without Heat", (("roll", "Roll with zero Heat"),))]
        )
    elif step == "room_review":
        text = clean(data["prompt"])
        fields = [
            Field(
                "choice",
                "Your part in the room scene",
                (
                    ("confirm", "Confirm your presence and play your character"),
                    ("return", "Return this scene choice to the Girl"),
                ),
            ),
            Field("account", "Describe your part if you confirm", paragraph=True, required=False),
        ]
    elif step in ("mid", "high_scene", "low_review"):
        text = "Choose and describe the original Captured! scene."
        choices = MID if step == "mid" else HIGH
        if step == "low_review":
            choices = {key: name for key, name in HIGH.items() if key != "pilot"}
        fields = [
            Field("choice", "Actual scene", tuple(choices.items())),
            Field("account", "Describe the original scene", paragraph=True),
        ]
        if step == "low_review":
            fields.append(Field("new_identity", "The Rebel Handler’s new Identity"))
    elif step == "convert":
        if not data["books"]:
            await reply(interaction, "The original rolled conversion awaits Ancillary approval.")
            return
        text = (
            clean(data["conversion_prompt"])
            + "\nNew Identity "
            + clean(data["conversion_identity"])
        )
        fields = [
            Field("choice", "Your original Rebel Ancillary playbook", tuple(data["books"].items())),
        ]
    else:
        text = clean(data["prompt"])
        if not data["slots"]:
            await reply(interaction, "The original erasure awaits a supported eligible Identity.")
            return
        fields = [Field("choice", "Erase this actual Identity", tuple(data["slots"].items()))]

    async def submit(click: discord.Interaction, values: dict[str, Any]) -> str:
        raw = values.get("heat", "").strip()
        heat = None
        if step == "roll":
            if not data["no_heat"] and (not raw.isascii() or not raw.isdecimal() or len(raw) > 9):
                raise ValueError("Enter a whole amount of actual Heat")
            heat = 0 if data["no_heat"] else int(raw)
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(click),
            str(click.id),
            identity,
            data["revision"],
            step,
            heat=heat,
            choice=(values.get("choice") or (None,))[0],
            account=values.get("account", ""),
            new_identity=values.get("new_identity", ""),
        )
        return "The original Captured! choice is saved."

    form = NativeForm(interaction.user.id, TITLE, text, fields, submit)
    await reply(interaction, form.text(), form)
