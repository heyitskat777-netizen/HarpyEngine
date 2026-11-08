"""Native exact-resource controls for willing or source-adjudicated Frame exposure."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_frame_core import FrameCoreService


async def open_core(interaction: discord.Interaction, service: FrameCoreService) -> None:
    data = await asyncio.to_thread(
        service.preview, viewer_from_interaction(interaction), int(interaction.channel_id or 0)
    )
    if not data["targets"]:
        await reply(interaction, "No actual occupied Frame is available for your review here.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        target = next(x for x in data["targets"] if x["token"] == values["target"][0])

        async def submit(next_interaction: discord.Interaction, details: dict[str, Any]) -> str:
            willing = details["mode"][0] == "willing"
            opponent = None
            tag = None
            if not willing:
                opponent = next(
                    x for x in target["opponents"] if x["token"] == details["opponent"][0]
                )
                selected = details["tag"][0]
                if selected != "none":
                    owner, tag = selected.split("/", 1)
                    if owner != opponent["token"] or not any(
                        x["id"] == tag for x in opponent["tags"]
                    ):
                        return "Choose a Tag this exact enemy can mark in this scene."
            result = await asyncio.to_thread(
                service.battle.expose,
                viewer_from_interaction(next_interaction),
                str(next_interaction.id),
                data["revision"],
                ActorRef.model_validate(target["ref"]),
                details["account"],
                willing=willing,
                opponent=ActorRef.model_validate(opponent["ref"]) if opponent else None,
                tag=tag,
                scene=data["scene"],
            )
            return "Actual Frame Core exposure saved. Source: " + str(result["event"])

        modes: tuple[tuple[str, str], ...] = (
            (("willing", "I willingly expose my actual Frame Core"),) if target["willing"] else ()
        )
        if target["opponents"]:
            modes += (("conditions", "Adjudicate two actual exposure conditions"),)
        if not modes:
            return "Only its actual Pilot or current scene adjudicator can expose this Core."
        fields = [Field("mode", "How is this Frame exposed?", modes)]
        if target["opponents"]:
            fields.extend(
                [
                    Field(
                        "opponent",
                        "Actual enemy (for conditions)",
                        tuple(
                            (x["token"], x["name"] + (" (Intense Bond)" if x["intense"] else ""))
                            for x in target["opponents"]
                        ),
                    ),
                    Field(
                        "tag",
                        "Tag the selected enemy can mark",
                        (("none", "No Tag criterion"),)
                        + tuple(
                            (x["token"] + "/" + tag["id"], x["name"] + ": " + tag["name"])
                            for x in target["opponents"]
                            for tag in x["tags"]
                        ),
                    ),
                ]
            )
        fields.append(
            Field("account", "Describe the actual exposure and enemy knowledge", paragraph=True)
        )
        form = NativeForm(
            current.user.id,
            "Actual Frame Core facts",
            "Two actual conditions are required unless the Pilot willingly exposes it. "
            "Tag eligibility also needs a relevant fictional reason. "
            "Reviewing it does not mark the Tag. "
            + (
                "All Girl Assets damaged. "
                if target["girl_assets"]
                else "Girl Assets remain intact. "
            )
            + ("All Identities marked." if target["identities"] else "Unmarked Identities remain."),
            fields,
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        interaction.user.id,
        "Frame Core review",
        "Choose the actual present Frame.",
        [
            Field(
                "target",
                "Actual occupied Frame",
                tuple((x["token"], x["name"]) for x in data["targets"]),
            )
        ],
        choose,
    )
    await reply(interaction, form.text(), form)
