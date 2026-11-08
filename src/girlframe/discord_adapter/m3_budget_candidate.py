"""Native table process proposals and original Girl assessment controls."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_candidate import CandidateService


async def open_candidate(
    interaction: discord.Interaction, service: CandidateService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] == "process":
        choices = [("propose", "Propose or revise the shared process")]
        if data["process"] and not data["approved"]:
            choices.append(("agree", "Agree to this exact process"))
        fields = [Field("action", "Your table response", tuple(choices))]
    elif data["phase"] == "assessing" and data["assessor"]:
        fields = [
            Field(
                "action", "Your assigned assessment", (("assess", "Report my actual assessment"),)
            )
        ]
    else:
        await reply(interaction, "Waiting for the original table or assigned Girl's assessment.")
        return
    fields.append(Field("account", "Your process, response or actual assessment", paragraph=True))

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["action"][0],
            values["account"],
        )
        return "Your own Candidate response is saved."

    form = NativeForm(
        interaction.user.id,
        "Pilot Candidate assessment",
        "Current process: "
        + (data["process"] or "Awaiting the table's proposal.")
        + "\nRevisions need fresh agreement. The assigned Girl records the assessment. "
        "Character activation is a separate step.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)
