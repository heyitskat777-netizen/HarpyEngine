"""Real source owners choose existing Asset facts, target and Void rewriting separately."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_handler_girl_void import HandlerGirlVoidService
from girlframe.services.onboarding import WorkflowError


async def open_handler_girl_void(
    interaction: discord.Interaction, service: HandlerGirlVoidService, work: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), work)
    phase = data["phase"]
    if phase == "allure":
        await reply(
            interaction,
            "Your actual Girl Assets are all Void-altered. The allure remains; "
            "you have no assigned Frame. Another person's Frame is not your assigned Frame.",
        )
        return
    if not data["can_act"]:
        await reply(
            interaction,
            "This actual original-body consequence awaits its source owner, "
            "or has already been completed.",
        )
        return
    if phase == "facts":

        async def propose(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.propose,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                values["name"],
                values["description"],
                values["evidence"],
                damaged=values["damaged"][0] == "yes",
                weapon=values["weapon"][0] == "yes",
            )
            return (
                "Your actual existing-Asset facts await the original source judge's factual review."
            )

        fields = [
            Field("name", "Name an actual existing eligible Asset"),
            Field("description", "Describe its existing capability", paragraph=True),
            Field("evidence", "Explain how this original body already owns it", paragraph=True),
            Field(
                "damaged",
                "Its actual existing condition",
                (("no", "Intact"), ("yes", "Already damaged")),
            ),
            Field(
                "weapon",
                "Actual weapon property",
                (("no", "Not a weapon"), ("yes", "Already a weapon")),
            ),
        ]
        callback = propose
        instructions = (
            "The source requires an actual uncorrupted Girl Asset to rewrite. Describe real "
            "preexisting gear, cybernetics or an established capability of this original body. "
            "This confirms existing facts; it does not create new equipment, grant a paid ability, "
            "repair damage or give you a Frame. Unproved facts must be corrected; the forced "
            "Void consequence remains pending."
        )
    elif phase == "review":
        proposal = data["proposal"]

        async def review(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.review,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                allow=values["allow"][0] == "yes",
                account=values["account"],
            )
            return (
                "Your factual review is saved. The actual caster then chooses the existing Asset."
            )

        fields = [
            Field(
                "allow",
                "Do these actual preexisting facts hold?",
                (("yes", "Confirm these actual facts"), ("no", "Require corrected facts")),
            ),
            Field("account", "Actual factual review and evidence", paragraph=True),
        ]
        callback = review
        instructions = (
            "Review the proposed EXISTING Asset; this does not veto the forced Void.\n"
            + proposal["name"]
            + "\n"
            + proposal["description"]
            + "\nEvidence: "
            + proposal["evidence"]
        )
    elif phase == "asset":
        if not data["assets"]:
            raise WorkflowError(
                "Recover the actual current uncorrupted Asset list before selecting."
            )

        async def select(current: discord.Interaction, values: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.select,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                values["asset"][0],
            )
            return (
                "Your original source's Asset choice is saved. "
                "Its actual owner describes the Void change."
            )

        fields = [
            Field(
                "asset",
                "Which actual counterpart Asset gains Void?",
                tuple((x["id"], x["name"]) for x in data["assets"]),
            )
        ]
        callback = select
        instructions = (
            "Choose the actual Asset for your original committed interaction. "
            "Its owner writes how it changes."
        )
    else:
        if phase != "rewrite":
            raise WorkflowError("Resume this actual source-owned corruption phase.")

        async def rewrite(current: discord.Interaction, values: dict[str, Any]) -> str:
            result = await asyncio.to_thread(
                service.rewrite,
                viewer_from_interaction(current),
                str(current.id),
                work,
                data["revision"],
                values["description"],
            )
            return (
                "The actual Asset is Void-altered. The allure remains without an assigned Frame."
                if result["allure"]
                else "Your actual source-selected Asset is Void-altered."
            )

        fields = [
            Field(
                "description", "Describe your actual selected Asset's Void change", paragraph=True
            )
        ]
        callback = rewrite
        instructions = (
            "Your original counterpart chose this actual Asset. Describe its real Void alteration."
        )
    form = NativeForm(
        interaction.user.id, "Handler Girl: actual Void consequence", instructions, fields, callback
    )
    await reply(interaction, form.text(), form)
