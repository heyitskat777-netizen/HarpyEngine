"""Private Director context review and separately owned departures."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_director import DirectorService
from girlframe.services.onboarding import WorkflowError


def one(values: dict[str, Any], key: str) -> str | None:
    return next(iter(values.get(key, ())), None)


async def open_review(
    interaction: discord.Interaction, service: DirectorService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.get, viewer, identity)
    if data["state"] != "pending":
        await reply(interaction, "This Director presence has been reviewed.")
        return
    options: tuple[tuple[str, str], ...] = (("yes", "My Handler is in the Director's presence"),)
    if data["absence_available"]:
        options += (("no", "The completed scene establishes my absence"),)

    def build(values: dict[str, Any]) -> list[Field]:
        fields = [Field("present", "Your Handler's actual presence", options)]
        if one(values, "present") == "yes" and not data["overlapping"]:
            fields += [
                Field("identity1", "First ordinary Identity"),
                Field("identity2", "Second ordinary Identity"),
            ]
        fields.append(Field("account", "Your actual presence review", paragraph=True))
        return fields

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        present = one(values, "present")
        if present not in {x[0] for x in options}:
            raise WorkflowError("Choose your actual available presence review.")
        labels = (
            (values["identity1"], values["identity2"])
            if present == "yes" and not data["overlapping"]
            else ()
        )
        result = await asyncio.to_thread(
            service.review,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            present == "yes",
            labels,
            values["account"],
        )
        return (
            "Presence review saved. Your Girl-rules context is in requests."
            if result["mode"] == "configured"
            else "The actual completed scene establishes the Handler was absent."
        )

    form = DependentForm(
        viewer.user_id,
        "Director — Handler presence",
        "In the Director's presence, you use Girl rules and start with zero Heat and two "
        "chosen Identities. An overlapping Director grants no second starting set. "
        "Absence needs a completed scene with the actual Director and without you.",
        build,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_context(
    interaction: discord.Interaction, service: DirectorService, identity: str
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.context, viewer, identity)
    if not data["active"]:
        await reply(
            interaction, "This Director presence has ended. Its resource history is preserved."
        )
        return
    if "identities" in data:
        text = "**Handler — Girl rules**\nHeat: " + str(data["heat"]) + "\n"
        text += "\n".join(
            entity_label(x) + (" — marked" if x["marked"] else " — unmarked")
            for x in data["identities"]
        )
        text += (
            "\nOrdinary Handler powers remain paused until the Directors actually leave. "
            "Further Girl Play controls remain gated in this preview."
        )
        await reply(interaction, text)
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.leave,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            data["game_revision"],
            values["npc"][0],
            values["account"],
        )
        return "Your Director's actual departure is saved. Other Directors may still be present."

    form = NativeForm(
        viewer.user_id,
        "Director — current presence",
        "Stay present until you choose your own departure. "
        "Leaving changes rule authority without granting recovery.",
        [
            Field("npc", "Your Director who is leaving", data["directors"]),
            Field("account", "Actual departure", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
