"""Cleanup scene attendance and the selected Girl's private Void alteration."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_cleanup import CleanupService


async def open_cleanup(
    interaction: discord.Interaction, service: CleanupService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    fields = []
    if data["phase"] == "scene":
        choices = []
        if not data["attended"]:
            choices.append(("attend", "Record my real cleanup scene attendance"))
        if data["handler"] and data["all_attended"]:
            choices.append(("end", "The cleanup scene actually ended"))
        if not choices:
            await reply(
                interaction, "Waiting for the other cleanup participants or the Handler's ending."
            )
            return
        fields.append(Field("action", "Your cleanup response", tuple(choices)))
    elif data["phase"] == "rewrite" and data["own"]:
        if not data["assets"]:
            await reply(
                interaction, "Recover your original uncorrupted Assets before this Void alteration."
            )
            return
        fields.append(
            Field(
                "asset",
                "Your Asset to alter",
                tuple((x["id"], x["label"] + " · " + x["family"]) for x in data["assets"]),
            )
        )
        if data["storage"]:
            fields.append(
                Field(
                    "storage",
                    "Use your connected JANUS Void Storage?",
                    (
                        ("no", "Alter this Asset permanently"),
                        ("yes", "Store this alteration in the connected Harpy"),
                    ),
                )
            )
    elif data["phase"] == "threshold":
        await reply(
            interaction, "Finish the pending Void consequence in your requests inbox first."
        )
        return
    else:
        await reply(
            interaction, "Waiting for the selected Girl's alteration, or this cleanup is complete."
        )
        return
    fields.append(Field("account", "Your attendance or Void alteration", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["action"][0] if "action" in values else "rewrite",
            values["account"],
            values["asset"][0] if "asset" in values else None,
            values.get("storage", ("no",))[0] == "yes",
        )
        return "Your cleanup response is saved."

    form = NativeForm(
        interaction.user.id, "Past mission: cleanup duty", data["summary"], fields, submit
    )
    await reply(interaction, form.text(), form)
