"""Native owned Dive selectors, full table question/proposal review and actual responses."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService

LABELS = {
    "call_reclassify_assets": "Call: move actual Assets between Girl and Frame",
    "void_and_unmark_all": "Gain Void; unmark unlocked Identities",
    "erase_identity_and_table_question": "Erase an Identity; ask the table",
    "nearby_npcs_gain_void": "Nearby actual NPCs gain Void",
    "table_replaces_identity": "The table replaces an Identity",
    "locked_cockpit_extraction_requires_frame_consent": "Subsumed: cockpit lock; vitals inactive",
}
MANIFESTATIONS = (
    ("brain", "Void of the brain"),
    ("bones", "Void of the bones"),
    ("flesh", "Void of the flesh"),
    ("abstract", "Void of the abstract"),
)


async def open_dive(
    interaction: discord.Interaction, game: GameService, identity: str, *, reviewed: bool = False
) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["dive"]
    kind = data["kind"]
    if kind in ("dive_table_answer", "dive_table_agreement") and not reviewed:
        if kind == "dive_table_answer":
            text = "The original Girl asks: " + detail["question"]
        else:
            value = detail["proposal"]
            text = (
                "Table Identity proposal revision "
                + str(detail["proposal_revision"])
                + ":\nReplace "
                + detail["identity_label"]
                + " with “"
                + value["replacement"]
                + "”.\n"
                + "Connection: "
                + value["account"]
            )
        view = DivePages(interaction.user.id, game, identity, text)
        await reply(interaction, view.text(), view)
        return
    fields: list[Field] = []
    instructions = (
        "Choose only your original owned Dive response. "
        "The scene stays held through actual effects."
    )
    if kind == "dive_select":
        fields = [
            Field(
                "option",
                "Choose one available printed effect",
                tuple((x, LABELS[x]) for x in detail["options"]),
            ),
            Field(
                "account",
                "Describe the painful connection"
                if detail["level"] == "low"
                else "Describe the actual connection",
                paragraph=True,
            ),
        ]
    elif kind == "dive_effect":
        option = detail["option"]
        if option == "call_reclassify_assets":
            assets = tuple(
                (x["id"], x["label"] + " (" + x["family"] + ")") for x in detail["assets"]
            )
            fields = [
                Field(
                    "moves",
                    "Move selected Assets to their other family",
                    assets,
                    minimum=0,
                    maximum=max(1, len(assets)),
                    required=False,
                ),
                Field(
                    "replaced",
                    "Only if above a cap: replace excess non-Void Assets",
                    tuple((x["id"], x["label"]) for x in detail["assets"] if not x["void"]),
                    minimum=0,
                    maximum=max(1, len(detail["assets"])),
                    required=False,
                ),
            ]
        elif option == "void_and_unmark_all":
            fields = [
                Field(
                    "asset",
                    "Choose your uncorrupted Asset",
                    tuple((x["id"], x["label"]) for x in detail["assets"]),
                ),
                Field("description", "Describe the actual Void alteration", paragraph=True),
            ]
        elif option in ("erase_identity_and_table_question", "table_replaces_identity"):
            fields = [
                Field(
                    "identity",
                    "Choose the ordinary unprotected Identity",
                    tuple((x["id"], x["label"]) for x in detail["identities"]),
                ),
                Field(
                    "text",
                    "Ask the table your question"
                    if option == "erase_identity_and_table_question"
                    else "Propose the new Identity",
                    paragraph=True,
                ),
            ]
        elif option == "nearby_npcs_gain_void":
            fields = [
                Field("npc_" + str(i), "Void: " + x["label"], MANIFESTATIONS)
                for i, x in enumerate(detail["npcs"])
            ]
            if not fields:
                await reply(
                    interaction,
                    "No original nearby NPC target remains. Recover this scene's actual context.",
                )
                return
        else:
            fields = [
                Field(
                    "confirm",
                    "Confirm actual own-cockpit subsumption",
                    (("yes", "Lock cockpit; vitals inactive; Frame consent required"),),
                )
            ]
    elif kind == "dive_table_answer":
        fields = [Field("text", "Your own answer to the reviewed question", paragraph=True)]
    elif kind == "dive_table_agreement":
        fields = [
            Field(
                "decision",
                "Your response to the exact reviewed proposal",
                (
                    ("yes", "Accept exactly this proposal"),
                    ("no", "Reject; ask for a revised proposal"),
                ),
            ),
            Field(
                "text",
                "Your comments or proposed revision (optional)",
                paragraph=True,
                required=False,
            ),
        ]
    else:
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work_id"])
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "dive_select":
            answer = ChoiceAnswer(options=(values["option"][0],), text=values["account"])
        elif kind == "dive_effect":
            option = detail["option"]
            if option == "call_reclassify_assets":
                answer = ChoiceAnswer(
                    options=tuple(values.get("moves", ())), denied=tuple(values.get("replaced", ()))
                )
            elif option == "void_and_unmark_all":
                answer = ChoiceAnswer(
                    fields=dict(asset=values["asset"][0]), text=values["description"]
                )
            elif option in ("erase_identity_and_table_question", "table_replaces_identity"):
                answer = ChoiceAnswer(
                    fields=dict(identity=values["identity"][0]), text=values["text"]
                )
            elif option == "nearby_npcs_gain_void":
                answer = ChoiceAnswer(
                    fields={
                        x["id"]: values["npc_" + str(i)][0] for i, x in enumerate(detail["npcs"])
                    }
                )
            else:
                answer = ChoiceAnswer(flag=True)
        elif kind == "dive_table_answer":
            answer = ChoiceAnswer(text=values["text"])
        else:
            answer = ChoiceAnswer(flag=values["decision"][0] == "yes", text=values.get("text", ""))
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return (
            "Your actual Dive response is saved. Play: "
            + str(result["state"])
            + ". Reopen /choice resume."
        )

    form = NativeForm(interaction.user.id, "Your Dive Deep response", instructions, fields, submit)
    await reply(interaction, form.text(), form)


class DivePages(discord.ui.View):
    def __init__(self, owner: int, game: GameService, identity: str, value: str):
        super().__init__(timeout=600)
        self.owner, self.game, self.identity = owner, game, identity
        escaped = clean(value)
        self.pages = tuple(escaped[i : i + 1600] for i in range(0, len(escaped), 1600)) or (
            "No source text.",
        )
        self.index = 0
        self.controls()

    def controls(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.respond.disabled = self.index != len(self.pages) - 1

    def text(self) -> str:
        return (
            f"**Original table response {self.index + 1}/{len(self.pages)}**\n"
            + self.pages[self.index]
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner:
            return True
        await reply(interaction, "This response belongs to its original table human.")
        return False

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button["DivePages"]
    ) -> None:
        self.index = max(0, self.index - 1)
        self.controls()
        await interaction.response.defer()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Next")
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button["DivePages"]
    ) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        self.controls()
        await interaction.response.defer()
        await reply(interaction, self.text(), self)

    @discord.ui.button(label="Respond to this exact source", style=discord.ButtonStyle.primary)
    async def respond(
        self, interaction: discord.Interaction, button: discord.ui.Button["DivePages"]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        await open_dive(interaction, self.game, self.identity, reviewed=True)
