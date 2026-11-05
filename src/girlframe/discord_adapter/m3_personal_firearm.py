"""Actual reviewed Personal Firearm purchase and owned lost-pistol retrieval."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_personal_firearm import Kind
from girlframe.services.m3_personal_firearm import PersonalFirearmService


def replacement(entries: list[dict[str, Any]]) -> Field:
    return Field(
        "replace",
        "Replace an ordinary Girl Asset only at the cap",
        tuple([("none", "No replacement")] + [(x["id"], x["name"]) for x in entries]),
    )


async def open_acquisition(
    interaction: discord.Interaction,
    service: PersonalFirearmService,
    kind: Kind,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.acquisition_view, viewer, kind)

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        selected = values["replace"][0]
        result = await asyncio.to_thread(
            service.buy_firearm,
            viewer_from_interaction(current),
            str(current.id),
            ActorRef.model_validate(data["actor"]),
            data["source_sha256"],
            kind,
            values["account"],
            replace=None if selected == "none" else selected,
        )
        return "Personal Firearm acquired and actual pistol issued. Receipt: " + str(result["id"])

    form = NativeForm(
        viewer.user_id,
        "Acquire Personal Firearm",
        "Only an implemented, independently reviewed rule is selectable. "
        "This issues an actual ordinary Girl Asset and its lost-item return entitlement.",
        [
            replacement(data["girl_replacements"]),
            Field("account", "Describe actual acquisition", paragraph=True),
            Field(
                "payment",
                "Your explicit payment",
                (("yes", "Pay " + str(data["price"]) + " Permissions"),),
            ),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_return(
    interaction: discord.Interaction,
    service: PersonalFirearmService,
    identity: str,
) -> None:
    viewer = viewer_from_interaction(interaction)
    data = await asyncio.to_thread(service.return_get, viewer, identity)
    if data.get("deferred"):
        await reply(
            interaction,
            "Your earned lost-pistol return remains unspent. "
            + (
                "Its source-bound request moved to a new period; reopen your inbox."
                if data.get("transfer_work")
                else "Complete the original revocation condition and owned restoration first."
            ),
        )
        return
    if data["state"] == "resolved" or data["stale"]:
        await reply(
            interaction,
            "Original pistol return: "
            + data["state"]
            + ". "
            + (
                "Recover the original character before changing it."
                if data["stale"]
                else "Your owned decision is saved."
            ),
        )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        chosen = values["replace"][0]
        result = await asyncio.to_thread(
            service.claim,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            take=values["take"][0] == "yes",
            account=values["account"],
            expected=data["expected"],
            replace=None if chosen == "none" else chosen,
        )
        return (
            "Actual pistol issued."
            if result["taken"]
            else "You declined this retrieval opportunity."
        )

    form = NativeForm(
        viewer.user_id,
        "Retrieve your lost Personal Firearm",
        "Your original Girl completed a real eight-plus ordinary Off-Duty roll "
        "while the issued pistol was lost. Damage alone does not qualify. "
        "Retrieval adds one actual item and no Permission charge.",
        [
            Field(
                "take",
                "Your owned choice",
                (("yes", "Retrieve my pistol"), ("no", "Decline this opportunity")),
            ),
            replacement(data["replacements"]),
            Field("account", "Describe your actual decision", paragraph=True),
        ],
        submit,
    )
    await reply(interaction, form.text(), form)
