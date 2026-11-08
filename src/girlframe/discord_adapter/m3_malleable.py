"""Original giver's private replacement and current-controller NPC evidence forms."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_malleable import MalleableService


async def open_malleable(
    interaction: discord.Interaction, service: MalleableService, identity: str | None = None
) -> None:
    viewer = viewer_from_interaction(interaction)
    channel = int(interaction.channel_id or 0)
    if identity is not None:
        data = await asyncio.to_thread(service.view, viewer, identity)
        if not data["replacements"]:
            await reply(interaction, "Your Malleable Tag: " + data["phase"] + ".")
            return

        async def force(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.force,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                values["replacement"][0],
                data["revision"],
            )
            return "Your qualified Tag became an actual Identity. The original Tag was consumed."

        form = NativeForm(
            viewer.user_id,
            "Force embrace: " + data["label"],
            "Choose the actual legal Identity replaced by your birth-qualified Tag. "
            "OOC pause remains available.",
            [
                Field(
                    "replacement",
                    "Actual Identity to replace",
                    tuple((x["id"], x["name"]) for x in data["replacements"]),
                )
            ],
            force,
        )
        await reply(interaction, form.text(), form)
        return
    data = await asyncio.to_thread(service.menu, viewer, channel)
    options = [("history:" + x["id"], x["label"]) for x in data["history"]]
    for npc in data["npcs"]:
        subject = ActorRef.model_validate(npc["ref"])
        active = next((x for x in data["alterations"] if x["subject"] == npc["ref"]), None)
        if npc["controller"] == viewer.user_id:
            options.append(
                (
                    ("end:" if active else "alter:") + subject.token,
                    ("End altered state: " if active else "Record altered state: ") + npc["label"],
                )
            )
        if data["can_give"]:
            options.append(("tag:" + subject.token, "Give actual Tag: " + npc["label"]))
    if not options:
        await reply(interaction, "No actual Malleable source or NPC evidence controls here.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        action, selected = values["action"][0].split(":", 1)
        if action == "history":
            await open_malleable(current, service, selected)
            return None
        npc = next(x for x in data["npcs"] if ActorRef.model_validate(x["ref"]).token == selected)
        subject = ActorRef.model_validate(npc["ref"])

        async def submit(response: discord.Interaction, answer: dict[str, Any]) -> str:
            actor = viewer_from_interaction(response)
            if action == "tag":
                applied = await asyncio.to_thread(
                    service.give_npc_tag,
                    actor,
                    str(response.id),
                    channel,
                    subject,
                    answer["account"],
                    data["revision"],
                )
                return "Your actual NPC Tag is saved." + (
                    " Its altered-state birth eligibility is saved." if applied["eligible"] else ""
                )
            if action == "end":
                active = next(x for x in data["alterations"] if x["subject"] == npc["ref"])
                await asyncio.to_thread(
                    service.end_npc_alteration,
                    actor,
                    str(response.id),
                    channel,
                    subject,
                    active["id"],
                    data["revision"],
                    answer["account"],
                )
                return "The actual NPC altered-state ending is saved."
            await asyncio.to_thread(
                service.record_npc_alteration,
                actor,
                str(response.id),
                channel,
                subject,
                data["revision"],
                answer["account"],
            )
            return "Your actual NPC altered-state evidence is saved."

        form = NativeForm(
            current.user.id,
            "Actual NPC Tag" if action == "tag" else "Actual NPC altered state",
            "Author the actual Tag as its original giver."
            if action == "tag"
            else "Supply the actual source fact as the current human controller. "
            "This records no automatic thoughts, dialogue or consent.",
            [
                Field(
                    "account",
                    "Actual Tag label" if action == "tag" else "Actual altered-state fact",
                    paragraph=action != "tag",
                )
            ],
            submit,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        viewer.user_id,
        "Malleable",
        "Actual altered-state evidence, birth-qualified Tags and your private giver controls.",
        [Field("action", "Your actual control", tuple(options))],
        choose,
    )
    await reply(interaction, form.text(), form)
