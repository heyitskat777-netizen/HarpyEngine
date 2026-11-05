"""Actual original body/Frame controls, with no automatic recovery or transport."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_passengers import PassengerService


async def open_passenger(
    interaction: discord.Interaction, service: PassengerService, identity: str
) -> None:
    value = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    options: list[tuple[str, str]] = []
    if value["can_consent"]:
        options.extend(
            (("allow", "Frame permits extraction"), ("refuse", "Frame refuses extraction"))
        )
    if value["can_move"]:
        if value["patient_owner"] and not value["subsumed"] and value["vitals_active"]:
            options.append(("leave", "My actual guest body leaves"))
        if any(x["ref"] != value["patient"] for x in value["actors"]):
            options.append(("extract", "My present body extracts the guest"))
    if value["can_request_medical"]:
        options.append(("medical_request", "Report completed actual medical help"))
    if value["can_review_medical"]:
        options.append(("medical_confirm", "Confirm actual medical recovery"))
    if not options:
        await reply(
            interaction,
            "This original guest is "
            + value["state"]
            + ". Resolve the actual source choice/Frame voice first.",
        )
        return
    fields = [Field("operation", "Your actual physical action", tuple(options))]
    if value["actors"]:
        fields.append(
            Field(
                "actor",
                "Your actual present physical role",
                tuple((x["token"], x["label"]) for x in value["actors"]),
                required=False,
                minimum=0,
            )
        )
    fields.append(Field("account", "Describe only your own actual action", paragraph=True))

    async def submit(current: discord.Interaction, data: dict[str, Any]) -> str:
        operation = data["operation"][0]
        actor = next(
            (
                ActorRef.model_validate(x["ref"])
                for x in value["actors"]
                if x["token"] in data.get("actor", ())
            ),
            None,
        )
        await asyncio.to_thread(
            service.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            value["revision"],
            "consent" if operation in ("allow", "refuse") else operation,
            data["account"],
            actor=actor if operation in ("leave", "extract") else None,
            allowed=operation == "allow" if operation in ("allow", "refuse") else None,
        )
        return (
            "Saved the actual physical action. Inactive vital signs require actual "
            "medical help; Assets remain unchanged."
        )

    await NativeForm(
        interaction.user.id,
        "Actual cockpit guest",
        "Frame consent and real extraction are separate owned actions.",
        fields,
        submit,
    ).present(interaction)
