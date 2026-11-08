"""Original Mentor naming and the Newgirl's separate existing cosmetic request."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_mentor import MentorService


async def open_mentor(
    interaction: discord.Interaction, service: MentorService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    if identity is not None:
        data = await asyncio.to_thread(service.view, viewer, identity)
        text = "Your original Mentor's fictional callsign choice: " + data["callsign"] + "."
        if not data["can_sync"]:
            await reply(interaction, text)
            return

        async def sync(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.store.queue_sync, viewer_from_interaction(current), str(current.id)
            )
            return (
                "Your existing owner-authorized cosmetic request is queued. "
                "Your fictional name is already canonical."
            )

        form = NativeForm(
            viewer.user_id,
            "Your Mentor's callsign choice",
            text + " Discord label sync is your separate existing owner action.",
            [
                Field(
                    "sync",
                    "Optional own cosmetic request",
                    (("queue", "Queue my current canonical Discord label"),),
                )
            ],
            sync,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.menu, viewer)
    options = [
        ("name:" + ActorRef.model_validate(x["ref"]).token, "Choose a callsign for " + x["label"])
        for x in data["learners"]
    ]
    options.extend(("history:" + x["id"], x["label"]) for x in data["history"])
    if not options:
        text = "No current original Mentor naming controls or private history."
        if data["own"]:
            text += (
                " Your actual Mentor is "
                + data["own"]["mentor"]
                + ". Your canonical callsign is "
                + data["own"]["callsign"]
                + "."
            )
        await reply(interaction, text)
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        kind, selected = values["action"][0].split(":", 1)
        if kind == "history":
            await open_mentor(current, service, selected)
            return None
        learner = ActorRef.model_validate(
            next(
                x["ref"]
                for x in data["learners"]
                if ActorRef.model_validate(x["ref"]).token == selected
            )
        )

        async def name(response: discord.Interaction, answer: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.name,
                viewer_from_interaction(response),
                str(response.id),
                learner,
                data["revision"],
                answer["callsign"],
            )
            return (
                "Your actual Mentor-authored fictional callsign is saved. "
                "The Newgirl owns any separate Discord cosmetic request."
            )

        form = NativeForm(
            current.user.id,
            "Actual Mentor callsign",
            "Choose the actual fictional callsign for your original Newgirl. "
            "This does not author their dialogue, attendance or platform preference.",
            [Field("callsign", "Your chosen callsign")],
            name,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Mentor daily controls",
        "Original-person names and actual OffDuty companion invitations "
        "use their existing owned scene controls.",
        [Field("action", "Your actual source control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
