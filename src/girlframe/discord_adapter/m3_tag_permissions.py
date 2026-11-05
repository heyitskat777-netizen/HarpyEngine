"""Private original-locker consent, without automatic rejection or invented replies."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
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
            else "The original locker's consent is still required."
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


async def open_tag_permissions(
    interaction: discord.Interaction, service: PermissionService, actor: ActorRef, tag_id: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    rows = await asyncio.to_thread(service.for_tag, viewer, actor, tag_id)
    if not rows:
        await reply(interaction, "This actual Tag has no original-locker rejection restriction.")
        return
    if len(rows) == 1:
        await open_permission(interaction, service, rows[0]["id"])
        return
    from girlframe.discord_adapter.m3_punishments import Picker

    async def choose(current: discord.Interaction, value: str) -> None:
        await open_permission(current, service, value)

    await Picker(
        viewer.user_id,
        "Actual original-locker consent",
        tuple(
            (
                x["id"],
                x.get("locker_label", "Original locker")
                + (" — permission recorded" if x["allowed"] else " — consent required"),
            )
            for x in rows
        ),
        choose,
    ).show(interaction)
