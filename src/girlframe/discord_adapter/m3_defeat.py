"""Native owned Defeat forms; no Heat entry, manual resource IDs or automatic consent."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_choices import DEFEAT_HIGH, DEFEAT_LOW, DEFEAT_MID
from girlframe.services.m2_game import GameService

LABELS = {
    "new_girl_and_frame_void_assets_heat4": "New Girl and Frame Void Assets; Heat 4",
    "escape_cockpit_choose_location": "Escape the cockpit; say where you go",
    "pilot_rescue_deepen_bond": "Another Girl rescues you into her cockpit",
    "handler_rescue_swap_girl_play_on_waking": "Handler rescue; injured; swap a Play on waking",
    "lower_status": "Lower your Status",
    "another_girl_gives_tag": "Another Girl may give you a Tag",
    "post_mission_punishment": "Punishment after the mission",
    "death": "Die from your injuries",
    "lose_frame_choose_later": "Frame destroyed; replace next Off-Duty if alive",
    "change_girl_playbook": "Change your Girl playbook",
    "amnesia_reset_and_replace": "Reset Identities; replace one with Amnesiac",
    "handler_ruinous_alternative": "Ask the Handler for an equally ruinous alternative",
}


async def open_work(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    from girlframe.services.m3_defeat import start_work
    from girlframe.services.onboarding import WorkflowError

    channel = interaction.channel_id
    if channel is None:
        raise WorkflowError("Use the actual source battle scene channel for this Defeat.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await asyncio.to_thread(
            start_work,
            game,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            channel,
            values["account"],
        )
        return "Required Defeat reserved. Action: " + str(result["action_id"])

    form = NativeForm(
        interaction.user.id,
        "Required Defeat",
        "Begin only the actual source consequence in its original battle scene. "
        "Existing known rolls remain recoverable.",
        [Field("account", "Actual Defeat context", paragraph=True)],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_start(
    interaction: discord.Interaction, game: GameService, decision: dict[str, Any]
) -> None:
    import sqlalchemy as sa

    from girlframe.database import tables as t

    with game.store.engine.connect() as c:
        table = t.m2["m2_actions"]
        child = c.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.parent_id == decision["parent"],
                table.c.actor_id == str(interaction.user.id),
                table.c.state.not_in(("complete", "aborted")),
                sa.func.json_extract(table.c.body_json, "$.defeat").is_not(None),
            )
            .limit(1)
        )
        owned = (
            next(
                (x for x in game.pending(c, child) if x["actor_id"] == str(interaction.user.id)),
                None,
            )
            if child
            else None
        )
    if child:
        if owned:
            from girlframe.discord_adapter.m2_ui import open_choice

            await open_choice(interaction, game, owned["id"])
        else:
            await reply(
                interaction,
                "Your original Defeat is already reserved. "
                "Waiting for its saved roll or another owned response. Action: " + child,
            )
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        viewer = viewer_from_interaction(current)
        sheet = await asyncio.to_thread(game.sheet, viewer)
        result = await asyncio.to_thread(
            game.begin,
            viewer,
            str(current.id),
            decision["channel"],
            sheet["revision"],
            PlayInput(
                play="defeat",
                heat=0,
                context=values["account"],
                trigger_confirmed=True,
                parent=decision["parent"],
                source_work=decision["body"].get("work_id")
                if decision["kind"] in ("required_defeat", "battle_defeat")
                else None,
            ),
        )
        return "Defeat reserved with your actual undamaged Girl Asset modifier. Action: " + str(
            result["action_id"]
        )

    form = NativeForm(
        interaction.user.id,
        "Required Defeat",
        "The actual source requires Defeat. Your roll uses +1 per undamaged Girl Asset, "
        "without Heat. "
        "Known receipts are resumed rather than rerolled.",
        [Field("account", "Describe the actual Defeat", paragraph=True)],
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_decision(
    interaction: discord.Interaction,
    game: GameService,
    decision: dict[str, Any],
    *,
    reviewed_revision: int | None = None,
) -> None:
    kind = decision["kind"]
    fields = []
    level = decision["result"]["tier"]
    own = decision.get("own") or {}
    if kind == "defeat_select":
        allowed = DEFEAT_LOW if level == "low" else DEFEAT_MID if level == "mid" else DEFEAT_HIGH
        fields = [
            Field(
                "options",
                "Your printed consequences",
                tuple((x, LABELS[x]) for x in allowed),
                2 if level == "high" else 1,
                2 if level in ("low", "high") else 1,
            ),
            Field("account", "Describe the selected actual consequences", paragraph=True),
        ]
        if level == "mid":
            for family in ("girl", "frame"):
                fields.extend(
                    [
                        Field(
                            family + "_name",
                            family.title() + " Void Asset name (Void option)",
                            required=False,
                        ),
                        Field(
                            family + "_description",
                            family.title() + " Void alteration (Void option)",
                            paragraph=True,
                            required=False,
                        ),
                    ]
                )
                assets = tuple(
                    (x["id"], x["name"])
                    for x in own.get("assets", ())
                    if x["family"] == family and not x["void"] and x.get("intrinsic") is None
                )
                if assets:
                    fields.append(
                        Field(
                            family + "_replace",
                            "Replace only at the " + family + " Asset cap",
                            assets,
                            0,
                            1,
                            required=False,
                        )
                    )
        others = tuple(
            (str(uid), decision["labels"][str(uid)])
            for uid in decision["pilots"]
            if uid != decision["actor"]
        )
        if others and level in ("mid", "high"):
            key = "rescuer" if level == "mid" else "tag_giver"
            fields.append(
                Field(
                    key,
                    "Rescuer (rescue option)"
                    if level == "mid"
                    else "Invite Tag giver (Tag option)",
                    others,
                    0,
                    1,
                    required=False,
                )
            )
        if level == "low":
            fields.append(
                Field(
                    "girl_playbook",
                    "New Girl playbook (change option)",
                    tuple(
                        (key, key)
                        for key, value in CATALOG.items()
                        if value["family"] == "girl" and key != own.get("girl")
                    ),
                    0,
                    1,
                    required=False,
                )
            )
            fields.append(
                Field(
                    "amnesiac_slot",
                    "Starting slot for Amnesiac (amnesia option)",
                    tuple(
                        (str(i), str(i + 1) + ": " + name)
                        for i, name in enumerate(
                            CATALOG.get(own.get("girl", ""), {}).get("identities", ())
                        )
                    ),
                    0,
                    1,
                    required=False,
                )
            )
    elif kind == "defeat_tag_gift":
        fields = [
            Field(
                "options",
                "Your optional Tag",
                (("give", "Give a Tag"), ("decline", "Decline to give a Tag")),
            ),
            Field("account", "Tag label (only if giving)", required=False),
        ]
    elif kind == "defeat_alternative":
        detail = decision["defeat"]
        fields = [
            Field("account", "Describe and justify your equally ruinous offer", paragraph=True),
            Field(
                "permissions",
                "Permissions removed",
                tuple((str(x), str(x)) for x in range(detail["permissions"] + 1)),
            ),
            Field(
                "confirmed", "Your actual ruling", (("yes", "I confirm this is equally ruinous"),)
            ),
        ]
        for key in ("assets", "identities"):
            values = tuple((x["id"], x["name"]) for x in detail[key])
            if values:
                fields.append(
                    Field(
                        key, "Remove these ordinary " + key, values, 0, len(values), required=False
                    )
                )
        fields.append(Field("tag", "Inflicted Tag (optional)", required=False))
        fields.append(
            Field(
                "frame_context",
                "Context if removing the last usable Girl Asset",
                (
                    ("unspecified", "No last Girl Asset loss"),
                    ("inside", "Inside a Frame"),
                    ("outside", "Outside a Frame"),
                ),
            )
        )
        fields.append(
            Field(
                "helpless_foe",
                "Foe if the last usable Girl Asset is removed",
                (("none", "No resulting Helplessness"),)
                + tuple((x["token"], x["label"]) for x in detail["foes"]),
            )
        )
    else:
        fields = [
            Field(
                "accept",
                "Your response to the actual offer",
                (("yes", "Accept this offer"), ("no", "Decline; choose your result again")),
            )
        ]
    instructions = "Your actual owned decision. Nothing applies until Confirm."
    if kind == "defeat_accept_alternative":
        if reviewed_revision != decision["revision"]:
            view = OfferPages(game, decision["id"], interaction.user.id)
            await view.show(interaction)
            return
        instructions = "Respond to the exact saved offer shown on the preceding review pages."

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "defeat_alternative":
            answer = ChoiceAnswer(
                text=values["account"],
                number=int(values["permissions"][0]),
                flag=True,
                fields={key: ",".join(values.get(key, ())) for key in ("assets", "identities")}
                | {
                    "tag": values.get("tag", ""),
                    "frame_context": values["frame_context"][0],
                    "helpless_foe": values["helpless_foe"][0]
                    if values["helpless_foe"][0] != "none"
                    else "",
                },
            )
        elif kind == "defeat_accept_alternative":
            answer = ChoiceAnswer(flag=values["accept"][0] == "yes")
        else:
            extra = {}
            for key, value in values.items():
                if key in ("options", "account") or not value:
                    continue
                extra[key] = value[0] if isinstance(value, tuple) else value
            answer = ChoiceAnswer(
                options=tuple(values["options"]), text=values.get("account", ""), fields=extra
            )
        result = await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            decision["id"],
            decision["revision"],
            answer,
        )
        return (
            "Defeat decision saved: "
            + str(result["state"])
            + ". Reopen requests for actual follow-ups."
        )

    form = NativeForm(interaction.user.id, "Defeat consequence", instructions, fields, submit)
    await reply(interaction, form.text(), form)


class OfferPages(discord.ui.View):
    """Review the complete saved offer before the original recipient responds."""

    def __init__(self, game: GameService, identity: str, owner: int):
        super().__init__(timeout=600)
        self.game, self.identity, self.owner = game, identity, owner
        self.index = 0
        self.revision = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This offer belongs to its original recipient.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        data = await asyncio.to_thread(
            self.game.decision, viewer_from_interaction(interaction), self.identity
        )
        offer = data["defeat"]["offer"]
        if data["kind"] != "defeat_accept_alternative" or offer is None:
            from girlframe.services.onboarding import WorkflowError

            raise WorkflowError("Reopen your current original Defeat decision.")
        self.revision = data["revision"]
        text = (
            "**Exact Handler offer**\n"
            + clean(offer["account"])
            + "\nPermissions removed: "
            + str(offer["permissions_lost"])
            + "\nAssets removed: "
            + clean(", ".join(offer["asset_names"]) or "None")
            + "\nIdentities removed: "
            + clean(", ".join(offer["identity_names"]) or "None")
            + "\nInflicted Tag: "
            + clean(offer["tag"] or "None")
            + (
                "\nHelpless against: " + clean(offer["foe_label"])
                if offer.get("helpless_foe")
                else ""
            )
        )
        pages = [text[i : i + 1500] for i in range(0, len(text), 1500)]
        self.index = min(max(self.index, 0), len(pages) - 1)
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(pages) - 1
        self.respond.disabled = self.index != len(pages) - 1
        await reply(interaction, pages[self.index] + f"\nPage {self.index + 1}/{len(pages)}.", self)

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index -= 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index += 1
        await interaction.response.defer(ephemeral=True)
        await self.show(interaction)

    @discord.ui.button(label="Choose your response")
    async def respond(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        data = await asyncio.to_thread(
            self.game.decision, viewer_from_interaction(interaction), self.identity
        )
        await open_decision(interaction, self.game, data, reviewed_revision=self.revision)
