"""Private actual snapshot/restore preview, with reversion owned only by the AM."""

import asyncio
import io
import json
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_am_backup import BackupService


async def open_backup(
    interaction: discord.Interaction, service: BackupService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    saved = await asyncio.to_thread(service.get, viewer, identity)
    owner = int(saved["actor"]["entity"]) == viewer.user_id
    preview = await asyncio.to_thread(service.preview, viewer, identity) if owner else None
    attachment = discord.File(
        io.BytesIO(
            json.dumps(dict(saved_snapshot=saved, actual_restore=preview), indent=2).encode()
        ),
        filename="am-backup-" + identity + ".json",
    )
    kwargs: dict[str, Any] = dict(
        content="Original immutable Identity/memory backup and actual restore projection. "
        "Only the original AM can choose reversion; this OOC file restores nothing itself.",
        file=attachment,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
    if preview is None:
        return
    retained = "\n".join(
        f"Retain {x['current']} (saved {x['saved'] or 'no such extra'}): {x['reason']}"
        for x in preview["retained"]
    )
    identities = ", ".join(x["name"] for x in preview["identities"])

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if values["revert"] != ("yes",):
            return "No reversion was selected."
        result = await asyncio.to_thread(
            service.restore,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            preview["revision"],
        )
        differences = "; ".join(
            f"{x['current']} retained: {x['reason']}" for x in result["retained"]
        )
        return (
            "Actual AM Identity content and fictional memories reverted to this genuine backup. "
            "Current marks, resources, physical state and required work remain. "
            + (
                "Protected differences: " + differences
                if differences
                else "No protected differences."
            )
        )

    form = NativeForm(
        interaction.user.id,
        "Original AM: revert genuine backup",
        f"Saved memory horizon: revision {preview['captured_revision']}. "
        f"Actual resulting Identities: {identities}.\n{retained}\n"
        "Review the complete snapshot and actual result in the private attachment. "
        "Reversion forgets subsequent experiences and restores the saved fictional memory state. "
        "Current marks, Limiters, protected/Paired/source obligations, resources, body and "
        "mandatory work remain. No operator reapproval, Heat charge or RNG. "
        "Pending actions and scene locks must finish first.",
        [Field("revert", "Revert to this genuine backup now", (("yes", "Revert now"),))],
        submit,
    )
    await reply(interaction, form.text(), form)
