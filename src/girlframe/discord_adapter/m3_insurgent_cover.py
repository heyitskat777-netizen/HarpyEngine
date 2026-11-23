"""Native private Cover Strain and actual evidence controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_insurgent_cover import CoverService


async def open_cover(
    interaction: discord.Interaction, service: CoverService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    stage = data["stage"]
    instructions = (
        f"Saved d6 {data['face']}. Printed row {data['effective_face']}."
        if data["face"] is not None
        else "Roll once for this actual Off-Duty start."
    )
    if stage == "die":
        fields = [Field("confirm", "Roll Cover Strain", (("yes", "Roll the d6"),))]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.roll,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return "Cover die saved. Reopen your Inbox to review the printed row."
    elif stage == "column" and data["targets"]:
        targets = {x["token"]: x for x in data["targets"]}
        fields = [
            Field(
                "holder",
                "Original Girl who finds evidence",
                tuple((token, x["name"]) for token, x in targets.items()),
            )
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            actor = ActorRef.model_validate(targets[values["holder"][0]]["ref"])
            await asyncio.to_thread(
                service.choose_evidence,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                actor,
            )
            return "The original Girl owns the next evidence decision."
    elif stage == "evidence" and data["owned_evidence"]:
        fields = [Field("account", "How you actually find the evidence", paragraph=True)]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.acquire,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "Your evidence can be used as a Handler Tag while you hold it."
    elif stage == "resolved" and data["owned_evidence"]:
        fields = [
            Field("confirm", "You no longer have the evidence", (("yes", "Record its loss"),))
        ]

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.lose,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
            )
            return "Evidence loss recorded. Its Tag can no longer be used."
    else:
        await reply(interaction, instructions + "\nCurrent Cover stage " + stage + ".")
        return
    form = NativeForm(viewer.user_id, "Cover Strain", instructions, fields, submit)
    await reply(interaction, form.text(), form)
