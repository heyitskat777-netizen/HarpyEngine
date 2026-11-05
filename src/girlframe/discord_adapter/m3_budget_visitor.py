"""Actual NPC-authored demands and original-player reparation responses."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field
from girlframe.discord_adapter.m3_strain_effects import DependentForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.services.m3_budget_visitor import VisitorService


class VisitForm(DependentForm):
    def __init__(self, *args: Any, records: list[dict[str, Any]], **kwargs: Any):
        self.records = records
        super().__init__(*args, **kwargs)

    @discord.ui.button(label="Read selected demand", row=4)
    async def read_demand(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        identity = self.values.get("target", ("",))[0]
        record = next((x for x in self.records if x["id"] == identity), None)
        if record is None:
            await reply(interaction, "Select a reparation demand first.")
            return
        embeds = [
            discord.Embed(title=label, description=clean(record[key]))
            for key, label in (
                ("offense", "Reported offense"),
                ("demand", "Exact demand"),
                ("response", "Player's reported response"),
            )
            if record.get(key)
        ]
        await interaction.response.send_message(
            embeds=embeds, ephemeral=True, allowed_mentions=discord.AllowedMentions.none()
        )


async def open_visit(
    interaction: discord.Interaction, service: VisitorService, identity: str
) -> None:
    data = await asyncio.to_thread(service.view, viewer_from_interaction(interaction), identity)
    pending = [x for x in data["demands"] if not x["settlement"]]
    actions: list[tuple[str, str]] = []
    if data["controller"]:
        if data["phase"] == "active":
            actions.extend(
                (
                    ("demand", "Observed offense: author a reparation demand"),
                    ("end", "The actual visit ended"),
                )
            )
        if any(x["response"] for x in pending):
            actions.append(("settle", "Confirm an actual response satisfies its demand"))
    elif pending:
        actions.append(("respond", "Describe my actual response to a demand"))
    if not actions:
        await reply(
            interaction, "There is no response due from you. This visit's records remain saved."
        )
        return

    def build(values: dict[str, Any]) -> list[Field]:
        action = values.get("action", (actions[0][0],))[0]
        fields = [Field("action", "Your owned response", tuple(actions))]
        if action == "demand":
            fields.extend(
                (
                    Field(
                        "target",
                        "Actual original Girl who offended this NPC",
                        tuple((x["id"], x["name"]) for x in data["people"]),
                    ),
                    Field("demand", "Exact reparations this NPC demands", paragraph=True),
                )
            )
        elif action in ("respond", "settle"):
            options = tuple(
                (x["id"], x["demand"][:100])
                for x in pending
                if action == "respond" or x["response"]
            )
            fields.append(Field("target", "Original reparation demand", options))
        fields.append(
            Field(
                "account",
                "Actual offense, performed response, settlement or ending",
                paragraph=True,
            )
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
            target=values.get("target", ("",))[0],
            demand=values.get("demand", ""),
        )
        return "Your visit response is saved."

    form = VisitForm(
        interaction.user.id,
        "Higher-up: " + data["visitor"][:60],
        "Choose a response. Read the selected demand before responding. "
        "Apply any resource changes through their usual commands first. "
        "Outstanding demands remain after the visit ends.",
        build,
        submit,
        records=pending,
    )
    await reply(interaction, form.text(), form)
