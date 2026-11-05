"""Private original-person contact requests; the NPC supplies its own confirmation."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_rebel_contact import ContactService


class ContactForm(DependentForm):
    def __init__(self, *args: Any, service: ContactService, identity: str, **kwargs: Any):
        self.service, self.identity = service, identity
        super().__init__(*args, **kwargs)

    @discord.ui.button(label="Read private route and response", row=4)
    async def read_details(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        data = await asyncio.to_thread(
            self.service.view, viewer_from_interaction(interaction), self.identity
        )
        embeds = [
            discord.Embed(title=label, description=clean(data[key]))
            for key, label in (
                ("method", "Proposed repeatable route"),
                ("response", "NPC's actual response"),
            )
            if data.get(key)
        ]
        if not embeds:
            await reply(interaction, "No route has been proposed yet.")
            return
        await interaction.response.send_message(
            embeds=embeds, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


async def open_contact(
    interaction: discord.Interaction, service: ContactService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    if data["phase"] == "complete":
        await reply(
            interaction,
            "**Your established NPC contact — "
            + clean(data["npc"])
            + "**\n"
            + clean(data["method"]),
        )
        return
    actions: list[tuple[str, str]] = []
    if data["girl"]:
        if data["choices"]:
            actions.append(("claim", "Describe my actual regular contact method"))
        if data["phase"] != "choose":
            actions.append(("withdraw", "Withdraw my proposed route"))
    if data["controller"] and data["phase"] == "confirm":
        actions.extend(
            (
                ("confirm", "As this NPC, confirm the established route"),
                ("revise", "As this NPC, request a workable route"),
            )
        )
    if not actions:
        await reply(
            interaction,
            "Introduce an actual known NPC from this city before proposing a route.",
        )
        return

    def build(values: dict[str, Any]) -> list[Field]:
        action = values.get("action", (actions[0][0],))[0]
        fields = [Field("action", "Your own character's response", tuple(actions))]
        if action == "claim":
            fields.append(
                Field(
                    "npc", "Actual known NPC", tuple((x["id"], x["name"]) for x in data["choices"])
                )
            )
        fields.append(
            Field("account", "Actual repeatable route, correction or confirmation", paragraph=True)
        )
        return fields

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.act,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            values["action"][0],
            values["account"],
            npc=values.get("npc", ("",))[0],
        )
        return "Your private contact response is saved."

    context = "The original Girl supplies her method; the actual NPC's controller confirms it."
    if data["method"]:
        context += "\n" + clean(data["method"])
    if data["phase"] == "revise":
        context += "\nThe NPC requested a revision; reopen the proposal with a workable method."
    form = ContactForm(
        interaction.user.id,
        "Secret regular NPC contact",
        context,
        build,
        submit,
        service=service,
        identity=identity,
    )
    await reply(interaction, form.text(), form)
