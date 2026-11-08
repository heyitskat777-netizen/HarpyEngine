"""Owned original-body neural contact and unplug controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_frame_control import FrameControlService
from girlframe.services.onboarding import WorkflowError


async def open_neural_links(
    interaction: discord.Interaction,
    service: FrameControlService,
    caster: ActorRef,
    battery: ActorRef,
) -> None:
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> None:
        if current.channel_id is None:
            raise WorkflowError("Open the neural contact controls in its actual scene channel")
        result = await asyncio.to_thread(
            service.propose,
            viewer_from_interaction(current),
            str(current.id),
            current.channel_id,
            caster,
            battery,
            values["account"],
        )
        await open_connection(current, service, result["id"])

    form = NativeForm(
        interaction.user.id,
        "Establish actual neural contact",
        "Describe your neural jack, the exposed spinal cord and how you reach and connect to it. "
        "Your scene's judge will confirm these physical facts. Optional contact also requires "
        "the other person's confirmation; a restrained Core's access goes directly to the judge.",
        [Field("account", "Actual spinal contact and physical access", paragraph=True)],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_connection(
    interaction: discord.Interaction,
    service: FrameControlService,
    identity: str,
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    value = data["connection"]
    if data["can_act"]:

        async def decide(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.decide,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["allowed"][0] == "yes",
                values["account"],
            )
            return "Actual neural contact: " + str(result["phase"]) + "."

        form = NativeForm(
            interaction.user.id,
            "Original neural contact: " + value["phase"],
            "Confirm your body's optional contact, or the jack, exposure and physical reach "
            "if you are the source judge. Describe missing or contradictory facts when refusing.",
            [
                Field(
                    "allowed",
                    "Your actual source decision",
                    (
                        ("yes", "Confirm actual facts/contact"),
                        ("no", "Refuse or correct missing facts"),
                    ),
                ),
                Field("account", "Your actual response or factual review", paragraph=True),
            ],
            decide,
        )
        await reply(interaction, form.text(), form)
    elif data["can_unplug"]:

        async def unplug(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.unplug,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                values["account"],
            )
            return "Unplugged. The link's temporary mental Assets and finite control have ended."

        form = NativeForm(
            interaction.user.id,
            "Actual connected neural link",
            "Describe your actual performed unplug. This ends the link's temporary benefits. "
            "Cockpit and extraction permissions remain separate.",
            [Field("account", "Actual performed unplug", paragraph=True)],
            unplug,
        )
        await reply(interaction, form.text(), form)
    else:
        await reply(
            interaction,
            "Your original neural contact is "
            + value["phase"]
            + ". The actual source owner has the next decision.",
        )


async def open_control(
    interaction: discord.Interaction,
    service: FrameControlService,
    actor: ActorRef,
) -> None:
    data = await asyncio.to_thread(service.control, viewer_from_interaction(interaction), actor)
    if not data["can_relink"]:
        await reply(interaction, "Current Frame control: " + data["label"] + ".")
        return

    async def relink(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.relink,
            viewer_from_interaction(current),
            str(current.id),
            actor,
            data["revision"],
            values["account"],
        )
        return "Your actual neural relink and restored owned Frame control are recorded."

    form = NativeForm(
        interaction.user.id,
        "Resume owned Frame control",
        "Describe how your original body reestablishes its neural connection. Actual reach, "
        "cockpit permissions and the Frame's condition still apply.",
        [Field("account", "Actual owned neural relink", paragraph=True)],
        relink,
    )
    await reply(interaction, form.text(), form)
