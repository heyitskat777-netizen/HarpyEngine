"""Only humans with several original roles need an extra native role selector."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService


def marker_field(decision: dict[str, Any]) -> Field | None:
    values = decision.get("tag_markers", ())
    if len(values) < 2:
        return None
    return Field(
        "fields.marker",
        "Role marking this Tag (required only when marking)",
        tuple((x["token"], x["label"]) for x in values),
        0,
        1,
        required=False,
    )


def bind_answer(decision: dict[str, Any], answer: ChoiceAnswer) -> ChoiceAnswer:
    """A single default role still carries the actual resource hash from the reviewed UI."""
    if decision["kind"] != "tag_window" or answer.options != ("tag",):
        return answer
    values = decision.get("tag_markers", ())
    if len(values) == 1 and "marker" not in answer.fields:
        return answer.model_copy(update={"fields": answer.fields | dict(marker=values[0]["token"])})
    return answer


async def open_discussion(
    interaction: discord.Interaction, game: GameService, identity: str, *, reviewed: bool = False
) -> None:
    decision = await asyncio.to_thread(
        game.decision, viewer_from_interaction(interaction), identity
    )
    detail = decision["tag_marker_discussion"]
    if decision["kind"] == "tag_marker_selection":
        fields = [
            Field(
                "proposal",
                "Choose an actual source proposal for discussion",
                tuple((x["id"], x["label"]) for x in detail["proposals"]),
            )
        ]
        instructions = (
            "Coordinate one actual proposal. Every original table human then agrees or rejects."
        )
    else:
        proposal = next(x for x in detail["proposals"] if x["id"] == detail["candidate"])
        instructions = (
            clean(proposal["label"])
            + "\n"
            + clean(proposal["tag"])
            + "\n"
            + clean(proposal["account"])
        )
        if not reviewed:
            pages = DiscussionPages(interaction.user.id, game, identity, instructions)
            await reply(interaction, pages.text(), pages)
            return
        fields = [
            Field(
                "agreement",
                "Your actual response",
                (("yes", "Agree with this exact proposal"), ("no", "Reject; continue discussion")),
            )
        ]

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        answer = (
            ChoiceAnswer(options=(values["proposal"][0],))
            if decision["kind"] == "tag_marker_selection"
            else ChoiceAnswer(flag=values["agreement"][0] == "yes")
        )
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            decision["revision"],
            answer,
        )
        return "Your actual source-table response is saved. Reopen /choice resume."

    form = NativeForm(
        interaction.user.id, "Source-role Tag discussion", instructions, fields, submit
    )
    await reply(interaction, form.text(), form)


class DiscussionPages(discord.ui.View):
    def __init__(self, owner: int, game: GameService, identity: str, text: str):
        super().__init__(timeout=600)
        self.owner, self.game, self.identity = owner, game, identity
        self.pages = tuple(text[i : i + 1600] for i in range(0, len(text), 1600)) or (
            "Original source proposal.",
        )
        self.index = 0
        self.controls()

    def controls(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.respond.disabled = self.index != len(self.pages) - 1

    def text(self) -> str:
        return (
            f"**Original Tag proposal {self.index + 1}/{len(self.pages)}**\n"
            + self.pages[self.index]
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await reply(interaction, "This source response belongs to its original table human.")
        return False

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button["DiscussionPages"]
    ) -> None:
        self.index = max(0, self.index - 1)
        self.controls()
        await interaction.response.defer()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Next")
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button["DiscussionPages"]
    ) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.controls()
        await interaction.response.defer()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Respond to this exact proposal", style=discord.ButtonStyle.primary)
    async def respond(
        self, interaction: discord.Interaction, button: discord.ui.Button["DiscussionPages"]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_discussion(interaction, self.game, self.identity, reviewed=True)
