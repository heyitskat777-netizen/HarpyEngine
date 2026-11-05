"""Private restoration condition, original inflictor confirmation and owned resource choice."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_privileges import PrivilegeService


async def open_privilege(
    interaction: discord.Interaction,
    service: PrivilegeService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    text = (
        "**Temporarily revoked Requisition**\n"
        + clean(data["label"])
        + "\nRestoration condition: "
        + clean(data["condition"])
    )
    fields = []
    if data["can_allow"]:
        fields = [
            Field("evidence", "How has the restoration condition been met?", paragraph=True),
            Field("confirm", "Your decision", (("yes", "Allow the original owner to restore"),)),
        ]
    elif data["can_restore"]:
        fields = [Field("evidence", "Describe the actual restoration", paragraph=True)]
        if data["replacements"]:
            fields.append(
                Field(
                    "replace",
                    "Replace an Asset only if at the cap",
                    tuple(
                        [("none", "No replacement")]
                        + [(x["id"], x["name"]) for x in data["replacements"]]
                    ),
                )
            )
        fields.append(Field("confirm", "Your decision", (("yes", "Restore this Requisition"),)))
    else:
        await reply(
            interaction,
            text
            + (
                "\nRestored."
                if not data["pending"]
                else "\nRecover the original character context."
                if data["stale"]
                else "\nWaiting for the original participant's decision."
            ),
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        replace = values.get("replace", ("none",))[0]
        result = await asyncio.to_thread(
            service.change,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["expected"],
            data["game_revision"],
            allow=data["can_allow"],
            evidence=values["evidence"],
            replace=None if replace == "none" else replace,
        )
        return (
            "Requisition restored."
            if result["restored"]
            else "Restoration allowed. Its original owner can now restore it from requests."
        )

    form = NativeForm(viewer.user_id, "Restore a Requisition", text, fields, submit)
    await reply(interaction, form.text(), form)
