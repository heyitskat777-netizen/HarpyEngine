"""Private original-setter consent, without automatic rejection or invented replies."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_tag_permissions import PermissionService


async def open_permission(
    interaction: discord.Interaction, service: PermissionService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    text = "**Tag rejection permission**\nTag: " + clean(data["label"]) + "\n"
    if not data["can_consent"]:
        text += (
            "Consent is recorded. The affected player still chooses their own action."
            if data["allowed"]
            else "The original setter's consent is still required."
            if data["active"]
            else "The original Tag is no longer present."
        )
        if data["stale"]:
            text += " Recover the original character context before changing this permission."
        await reply(interaction, text)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.grant,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["source_sha256"],
            True,
        )
        return "Consent recorded. The Tag remains until its owner actually rejects or embraces it."

    form = NativeForm(
        viewer.user_id,
        "Your Tag rejection permission",
        text,
        [Field("confirm", "Your optional decision", (("yes", "Allow them to reject this Tag"),))],
        submit,
    )
    await reply(interaction, form.text(), form)
