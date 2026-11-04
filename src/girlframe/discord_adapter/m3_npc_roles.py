"""Private, owned NPC-role invitation reviews."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_npc_roles import NpcRoleService


async def open_invitation(
    interaction: discord.Interaction, service: NpcRoleService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] != "pending":
        await reply(interaction, "This NPC role invitation is " + data["state"] + ".")
        return
    recipient = data["recipient"] == viewer.user_id
    options = (
        (("accept", "Accept this NPC role"), ("decline", "Decline this role"))
        if recipient
        else (("withdraw", "Withdraw this introduction"),)
    )
    npc = data["npc"]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["game_revision"],
            values["decision"][0],
        )
        return "Role decision saved. Confirm scenes and other choices separately."

    form = NativeForm(
        viewer.user_id,
        "NPC role — " + npc["name"],
        "Playbooks: " + ", ".join(x.replace("_", " ") for x in npc["jobs"]) + "\n" + npc["detail"],
        [Field("decision", "Your decision", options)],
        submit,
    )
    await reply(interaction, form.text(), form)
