"""Native M2 Play and owned-response wizards; all state changes go through services."""

from typing import Any

import discord
from discord import app_commands

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.labels import entity_label
from girlframe.discord_adapter.ledger import clean
from girlframe.discord_adapter.m2_forms import Field, NativeForm, threaded
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.discord_adapter.onboarding import private_operation, reply
from girlframe.engine.m2 import (
    FLIRT_QUESTIONS,
    MANEUVERS,
    PLAY_IDS,
    QUESTIONS,
    TRAITS,
    ChoiceAnswer,
    PlayInput,
)
from girlframe.engine.m3_plays import HEAT_IDS
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m2_game import PUBLIC_FIELDS, GameService
from girlframe.services.onboarding import WorkflowError

YES = (("yes", "Yes"), ("no", "No"))


def menu(
    key: str, label: str, values: Any, minimum: int = 1, maximum: int = 1, required: bool = True
) -> Field:
    labels = {
        "foundation_destination": "Where should we go?",
        "foundation_avoid": "What should we avoid?",
        "enemy_activity": "What is the enemy doing?",
        "repair_rest": "Where can we rest and repair?",
        "civilian_danger": "Where are civilians at risk?",
        "orders": "What are our orders?",
        "hurt": "Who would you like me to hurt?",
        "be": "Who would you like me to be?",
        "hide": "What would you like me to hide?",
        "fears": "How can I ease your fears?",
        "name": "What name would you like me to use?",
        "intimacy": "Do you want to be intimate with me?",
    }
    return Field(
        key,
        label,
        tuple((str(x), labels.get(str(x), str(x).replace("_", " ").capitalize())) for x in values),
        minimum,
        maximum,
        required=required,
    )


def text(key: str, label: str, required: bool = True) -> Field:
    return Field(key, label, paragraph=True, required=required)


def entities(
    key: str,
    label: str,
    values: list[dict[str, Any]],
    minimum: int = 1,
    maximum: int = 1,
    required: bool = True,
) -> Field:
    return Field(
        key,
        label,
        tuple((x["id"], entity_label(x)) for x in values),
        minimum,
        maximum,
        required=required,
    )


def one(values: dict[str, Any], key: str, default: Any = None) -> Any:
    entry = values.get(key)
    return entry[0] if isinstance(entry, tuple) and entry else default


def choice_fields(decision: dict[str, Any]) -> list[Field]:
    kind = decision["kind"]
    own = decision["own"]
    result = decision["result"]
    level = result.get("tier")
    identities = (
        [
            x
            for x in own["identities"]
            if x["marked"] and x["id"] not in own.get("sedation_locked", ())
        ]
        if own
        else []
    )
    assets = [x for x in own["assets"] if not x["damaged"]] if own else []

    def unmark(n: int) -> Field:
        return entities("denied", "Unmark Identities (optional)", identities, 0, n, False)

    def flags(label: str) -> Field:
        return Field("flag", label, YES)

    fields = []
    if kind == "tag_window":
        fields = [
            menu("options", "Pass or propose one Tag", ("pass", "tag")),
            entities(
                "denied", "Relevant observed Tag (for Tag proposal)", decision["tags"], 0, 1, False
            ),
            menu("number", "Tag direction", ("-1", "1"), required=False),
            text("text", "Why is the Tag relevant?", False),
        ]
        if own and own["girl"] == "ALPHA":
            fields.append(
                menu(
                    "fields.status",
                    "Optional Dog Status modifier",
                    ("0", "-1", "1"),
                    required=False,
                )
            )
    elif kind == "tag_resolution":
        fields = [
            menu("options", "Resolve the repeated marked Tag", ("embrace", "reject")),
            entities(
                "denied",
                "Identity to replace when embracing",
                [x for x in own["identities"] if not x["protected"]],
                0,
                1,
                False,
            ),
        ]
    elif kind == "paired_tag":
        fields = [menu("options", "Make this the Paired Identity?", ("yes", "no"))]
    elif kind == "actor_keep":
        if level == "mid":
            fields = [
                menu("options", "Choose two positive traits", TRAITS, 2, 2),
                menu("denied", "Choose one distinct negative trait", TRAITS),
            ]
        elif level == "low":
            fields = [menu("options", "Choose one positive trait", TRAITS)]
        else:
            fields = [text("text", "Take a Tag: write its label")]
        if own["girl"] == "OLDGEN":
            fields.append(flags("Also choose experienced?"))
    elif kind == "handler_keep":
        fields = [flags("Is it enough?"), text("text", "Explain the outcome")]
    elif kind == "actor_sensors":
        count = {"low": 1, "mid": 2, "high": 3}[level]
        fields = [
            menu(
                "options",
                "Listed questions",
                QUESTIONS,
                1 if level == "low" else 0,
                count,
                level == "low",
            )
        ]
        if level != "low":
            fields.extend(
                text(
                    "fields.q" + str(i + 1), "Custom question " + str(i + 1) + " (optional)", False
                )
                for i in range(count)
            )
    elif kind == "handler_sensors":
        fields = [
            text("fields.a" + str(i + 1), "Answer " + str(i + 1))
            for i in range(len(result["questions"]))
        ]
        if level == "high" and result["off_list"]:
            fields.append(
                menu(
                    "options",
                    "Off-list consequence",
                    ("incomplete_information", "punishment_later"),
                )
            )
    elif kind == "actor_engage":
        count = {"low": 1, "mid": 2, "high": 3}[level]
        fields = [menu("options", "Choose maneuvers", MANEUVERS, count, count)]
        fields.extend(
            entities("fields." + m, "Asset for " + m + " (if selected)", assets, 0, 1, False)
            for m in MANEUVERS
        )
        if level != "mid":
            fields.append(entities("denied", "Damage an Asset you used", assets))
    elif kind == "actor_disobey":
        if level == "mid":
            fields = [
                menu("options", "Choose the refusal branch", ("tag_heat", "reject_tag", "follow")),
                text("text", "New Tag (Tag + Heat branch)", False),
                menu("number", "Heat gained (Tag branch)", ("1", "2"), required=False),
                entities("denied", "Tag to reject", decision["tags"], 0, 1, False),
                menu(
                    "member",
                    "Pilot to follow you",
                    [
                        str(x)
                        for x in decision.get("pilots", decision["participants"])
                        if x != decision["actor"]
                    ],
                    required=False,
                ),
            ]
        else:
            fields = [flags("Act immediately without thinking?")]
    elif kind == "handler_disobey":
        fields = [flags("Does the Handler find out?")]
    elif kind == "follow_disobey":
        fields = [flags("Follow immediately without thinking?")]
    elif kind == "actor_flirt":
        fields = [menu("options", "Ask the other player", FLIRT_QUESTIONS), unmark(2)]
        if level == "high":
            fields.extend(
                [
                    menu("fields.extra", "Choose how you go too far", ("escape", "handler", "owe")),
                    text("text", "Describe how you go too far"),
                ]
            )
    elif kind == "target_flirt":
        fields = [text("text", "Your answer"), unmark(1 if level == "low" else 2)]
        if level == "low":
            fields.append(menu("options", "Optional return question", FLIRT_QUESTIONS, 0, 1, False))
        elif result.get("question") == "intimacy":
            fields.append(flags("Explicitly agree to this interaction?"))
    elif kind == "actor_flirt_answer":
        fields = [text("text", "Your answer to the return question")]
    elif kind == "flirt_escape":
        fields = [
            menu("options", "Choose your response", ("helpless", "damage", "play")),
            entities("denied", "Asset to damage (damage branch)", assets, 0, 1, False),
        ]
    elif kind == "handler_brief":
        fields = [
            menu("options", "Choose the implemented Handler Play", ("brief",)),
            text("text", "Brief them on the situation"),
        ]
    elif kind == "flirt_owe_tag":
        fields = [text("text", "Give the actor a Tag")]
    elif kind == "order_response":
        fields = [
            menu(
                "options",
                "Respond to the direct order",
                ("obedient", "immediate", "hesitant", "mouthing_off", "gritted_teeth", "disobey"),
            )
        ]
    elif kind == "followthrough_confirm":
        fields = [
            flags("Did this fulfill what you requested?"),
            text("text", "Confirm or explain your response"),
        ]
    if kind == "actor_tag_selection":
        fields = [
            Field(
                "options",
                "Propose a Tag for scene discussion",
                tuple(
                    (x["id"], x["label"][:85] + " " + str(x["direction"]))
                    for x in decision["proposals"]
                ),
            )
        ]
    elif kind == "actor_tag_agreement":
        fields = [flags("Do you agree to this saved Tag proposal?")]
    if decision.get("actor_basic") and kind == "tag_window":
        fields.append(
            Field(
                "fields.as_actor",
                "Your actual role (for a Tag proposal)",
                tuple((x["token"], x["label"]) for x in decision["roles"]),
                required=False,
            )
        )
    if kind == "beneath_select":
        from girlframe.engine.m3_beneath import BASE, EXTRA

        extra = decision["beneath"]
        labels = {
            "tag": "Give her a Tag",
            "status": "Lower her Status",
            "bond": "Weaken one of her Bonds",
            "lock_tag": "Require your consent to reject a Tag",
            "pin": "Pin her; ask for her response",
            "punish": "Inflict a legal Punishment",
            "damage": "Damage one of her Assets",
        }
        choices = (
            BASE if level == "mid" else (*BASE, *EXTRA, *(() if level == "high" else ("damage",)))
        )
        fields = [
            Field(
                "options",
                "Choose printed effects",
                tuple((key, labels[key]) for key in (BASE if level == "high" else choices)),
                2 if level == "mid" else 1,
                2 if level == "mid" else 1,
            ),
            text("text", "Describe the actual confrontation"),
            text("fields.tag", "New Tag label (Tag effect only)", False),
        ]
        if level == "high":
            fields.insert(
                1,
                Field(
                    "beneath_extra",
                    "Choose one extra effect",
                    tuple((key, labels[key]) for key in EXTRA),
                ),
            )
        tags = tuple((x["id"], x["label"]) for x in extra["tags"])
        if level == "high":
            tags += (("new", "The Tag I give with this result"),)
        if tags and level != "mid":
            fields.append(
                Field(
                    "fields.locked_tag",
                    "Tag to lock (lock effect only)",
                    tags,
                    minimum=0,
                    required=False,
                )
            )
        if extra["orders"] and level != "mid":
            fields.append(
                Field(
                    "fields.order",
                    "Actual followed order (Punishment only)",
                    tuple((x["id"], x["label"]) for x in extra["orders"]),
                    minimum=0,
                    required=False,
                )
            )
    elif kind == "beneath_details":
        extra = decision["beneath"]
        if "bond" in extra["options"]:
            fields = [
                Field(
                    "fields.bond",
                    "Your actual Bond to weaken",
                    tuple((x["token"], x["label"]) for x in extra["bonds"]),
                )
            ]
        else:
            fields = [entities("denied", "Your actual Asset damaged by the counterattack", assets)]
    elif kind == "beneath_pin_response":
        fields = [
            menu("options", "Your own response", ("narrative", "play")),
            text("text", "Describe your response (or continue to a real Play)", False),
        ]
    if kind == "tag_resolution" and decision.get("rejection_blocked"):
        fields = [
            f
            if f.key != "options"
            else menu("options", "Tag rejection needs its setter's consent", ("embrace",))
            for f in fields
        ]
    return [f for f in fields if not (f.options == () and f.key in ("denied", "member"))]


def answer_values(values: dict[str, Any]) -> ChoiceAnswer:
    fields = {
        key[7:]: str(value[0] if isinstance(value, tuple) else value).strip()
        for key, value in values.items()
        if key.startswith("fields.") and value
    }
    options = tuple(values.get("options", ()))
    options += tuple(values.get("beneath_extra", ()))
    if options and options[0] in MANEUVERS:
        fields = {k: v for k, v in fields.items() if k in options}
    return ChoiceAnswer(
        options=options,
        denied=tuple(values.get("denied", ())),
        text=values.get("text", ""),
        fields=fields,
        flag=(one(values, "flag") == "yes") if one(values, "flag") is not None else None,
        number=int(one(values, "number")) if one(values, "number") is not None else None,
        member=int(one(values, "member")) if one(values, "member") is not None else None,
    )


async def open_choice(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    decision = await threaded(lambda: game.decision(viewer_from_interaction(interaction), identity))
    if decision["kind"] == "beneath_punishment":
        from girlframe.discord_adapter.m3_punishments import open_discipline
        from girlframe.services.m3_punishments import PunishmentService

        await open_discipline(
            interaction, PunishmentService(game.store), decision["body"]["work_id"]
        )
        return
    if decision["kind"] in ("escape_play", "order_disobey", "beneath_response_play"):
        await open_play(interaction, game, parent=decision)
        return
    fields = choice_fields(decision)
    if not fields:
        raise WorkflowError("UNSUPPORTED_RULE: this response requires staff review.")

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        result = await threaded(
            lambda: game.respond(
                viewer_from_interaction(current),
                str(current.id),
                identity,
                decision["revision"],
                answer_values(values),
            )
        )
        return (
            "Decision saved. Action: "
            + str(result["state"])
            + ". Reopen /choice resume for the next step."
        )

    instructions = (
        "Choose only your own response. Nothing is submitted until Confirm. "
        "Safety pause remains available."
    )
    if decision.get("beneath") and decision["kind"] == "beneath_select":
        instructions += (
            "\nEffects apply to "
            + clean(decision["beneath"]["affected_label"])
            + ". "
            + (
                "You choose the counterattack."
                if decision["beneath"]["level"] == "low"
                else "Choose your result's printed effects."
            )
        )
    if decision.get("actor_basic"):
        instructions += (
            "\nTag proposals and their relevance are shared with all scene participants. "
            "Pass without selecting a role or modifier."
        )
        if decision["kind"] == "tag_resolution":
            instructions += (
                " Embracing adds an Identity; choose a replacement only if you already have four. "
                "Rejecting requires an actual later action."
            )
        for proposal in decision.get("proposals", ()):
            instructions += (
                "\nProposal: "
                + clean(proposal["label"])
                + " "
                + str(proposal["direction"])
                + ". "
                + clean(proposal["account"])
            )
    if decision["kind"] == "handler_sensors":
        instructions += "\nQuestions: " + "; ".join(decision["result"]["questions"])
    if decision["kind"] == "target_flirt":
        instructions += "\nQuestion: " + str(
            decision["result"].get("question", "Why did you withdraw?")
        )
    if decision.get("order_text"):
        instructions += "\nDirect order: " + clean(decision["order_text"])
    if decision.get("context"):
        instructions += "\nProposed follow-through: " + clean(decision["context"])
    form = NativeForm(
        interaction.user.id,
        decision["kind"].replace("_", " ").title(),
        instructions,
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_play(
    interaction: discord.Interaction, game: GameService, *, parent: dict[str, Any] | None = None
) -> None:
    if parent is None and game.store.policy.m3_approval is not None:
        from girlframe.discord_adapter.m3_actor_plays import open_actor_play
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.services.m3_actors import ActorService
        from girlframe.services.m3_missions import MissionService

        roles = await threaded(
            lambda: ActorService(MissionService(game.store)).choices(
                viewer_from_interaction(interaction)
            )
        )
        actual = next((x for x in roles["actors"] if x["rules"] == "handler_girl"), None)
        if actual is not None:
            await open_actor_play(interaction, game, ActorRef.model_validate(actual["ref"]))
            return
    viewer = viewer_from_interaction(interaction)
    game.gate()
    sheet = await threaded(lambda: game.sheet(viewer))
    from girlframe.services.m3_refusal import view as refusal_preview

    refusal_modifiers = await threaded(lambda: refusal_preview(game, viewer))
    channel = parent["channel"] if parent else interaction.channel_id
    if channel is None:
        raise WorkflowError("Use a joined scene channel.")
    scene = await threaded(lambda: game.scene_info(viewer, channel))
    if not scene["joined"]:
        raise WorkflowError("Join this scene with /campaign scene_join first.")
    plays = ("disobey_orders",) if parent and parent["kind"] == "order_disobey" else PLAY_IDS
    approval = game.store.policy.m3_approval
    rulings = game.store.policy.owner_m3_rulings
    if (
        not parent
        and approval is not None
        and "plays" in approval.subsystems
        and rulings is not None
        and rulings.beneath_private_choices == "affected_owner"
    ):
        plays = (*plays, *HEAT_IDS)
    identities = [x for x in sheet["identities"] if not x["marked"]]
    fields = [
        menu("play", "Choose a Play", plays),
        Field(
            "target",
            "Target for Flirt or Put Someone Beneath You",
            tuple(
                (str(x), scene["labels"][str(x)]) for x in scene["pilots"] if x != viewer.user_id
            ),
            0,
            1,
            required=False,
        ),
        entities("identity", "Optional Identity to mark", identities, 0, 1, False),
        menu("gain", "Identity Heat gained", range(6)),
        menu("pair_share", "Paired Heat sent to Pair", range(6)),
        menu("heat", "Heat to spend", range(sheet["heat"] + 6)),
        Field("piloting", "Are you piloting your Frame?", YES),
        Field("witnessed", "Foundation member witnesses refusal?", YES),
        text("context", "Describe the trigger and intended action"),
        Field(
            "trigger",
            "Confirm the printed trigger applies",
            (("yes", "I confirm the trigger applies"),),
        ),
    ]

    # Target IDs are stable authenticated IDs, not editable claims of ownership.
    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        play = one(values, "play")
        identity = one(values, "identity")
        prepared = PlayInput(
            play=play,
            context=values["context"],
            trigger_confirmed=True,
            heat=int(one(values, "heat")),
            identity=identity,
            gain=int(one(values, "gain")),
            pair_share=int(one(values, "pair_share")),
            target=int(one(values, "target"))
            if play in ("flirt", *HEAT_IDS) and one(values, "target")
            else None,
            piloting=one(values, "piloting") == "yes",
            witnessed=one(values, "witnessed") == "yes",
            parent=parent["parent"] if parent else None,
            order_id=parent["body"].get("order_id") if parent else None,
        )
        result = await threaded(
            lambda: game.begin(
                viewer_from_interaction(current),
                str(current.id),
                channel,
                sheet["revision"],
                prepared,
            )
        )
        return (
            (
                "Play confirmed. The bot will lock scene chat before spending Heat "
                "or rolling. Open /choice resume to continue. Action `"
            )
            + str(result["action_id"])
            + "`."
        )

    form = NativeForm(
        viewer.user_id,
        "Prepare a Play",
        (
            "Choose resources, describe the trigger, then Confirm & Roll. No "
            "dice are sampled before the channel lock is acknowledged."
        )
        + (
            " Your next Disobey Orders roll has +"
            + str(sum(x["amount"] for x in refusal_modifiers))
            + " from control slips, separate from Heat and later Tags."
            if refusal_modifiers
            else ""
        ),
        [x for x in fields if not (x.key in ("target", "identity") and not x.options)],
        submit,
    )
    form.confirm.label = "Confirm & Roll"
    await reply(interaction, form.text(), form)


async def open_pending(interaction: discord.Interaction, game: GameService) -> None:
    rows = await threaded(lambda: game.choices(viewer_from_interaction(interaction)))
    from girlframe.services.m3_actor_plays import ActorPlayService

    saved = await threaded(
        lambda: ActorPlayService(game).saved(viewer_from_interaction(interaction))
    )
    from girlframe.services.m3_recovery import RecoveryService

    shared = await threaded(
        lambda: RecoveryService(game).saved(viewer_from_interaction(interaction))
    )
    if saved or shared:
        from girlframe.discord_adapter.m3_actor_plays import open_recovery
        from girlframe.discord_adapter.m3_punishments import Picker
        from girlframe.discord_adapter.m3_recovery import open_recovery as open_shared_recovery

        entries = {"recover:" + x["id"]: x for x in saved}
        shared_entries = {"shared:" + x["id"]: x for x in shared}
        options = tuple((x["id"], x["kind"].replace("_", " ").title()) for x in rows) + tuple(
            (key, "Recover your saved actual-role Play") for key in entries
        )
        options += tuple(
            (key, "Recover your saved " + x["play"].replace("_", " "))
            for key, x in shared_entries.items()
        )

        async def choose(current: discord.Interaction, token: str) -> None:
            if token in shared_entries:
                await open_shared_recovery(current, game, shared_entries[token])
            elif token in entries:
                await open_recovery(current, game, entries[token])
            else:
                await open_choice(current, game, token)

        await Picker(
            interaction.user.id, "**Your pending Plays and saved recovery**", options, choose
        ).show(interaction)
        return
    if not rows:
        await reply(
            interaction,
            (
                "No immediate Play responses need you. /character followthrough "
                "lists your future obligations."
            ),
        )
        return

    # A selector callback opens directly; unlike effects, viewing needs no extra confirmation.
    class ChoiceSelect(discord.ui.Select[discord.ui.View]):
        def __init__(self) -> None:
            super().__init__(
                placeholder="Choose a pending response",
                options=[
                    discord.SelectOption(
                        label=x["kind"].replace("_", " ").title(),
                        value=x["id"],
                        description="Action " + x["action_id"][:8],
                    )
                    for x in rows[:25]
                ],
            )

        async def callback(self, current: discord.Interaction) -> None:
            if current.user.id != interaction.user.id:
                await reply(current, "This queue belongs to another player.")
                return
            await current.response.defer(ephemeral=True)
            try:
                await open_choice(current, game, self.values[0])
            except WorkflowError as error:
                await reply(current, str(error))

    view = discord.ui.View(timeout=600)
    view.add_item(ChoiceSelect())
    await reply(
        interaction,
        (
            "**Your pending Plays**\nSelect a response. Saved choices survive "
            "restarts; /character requests also lists them."
        ),
        view,
    )


class SceneControls(discord.ui.View):
    def __init__(self, game: GameService):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="My pending choices", custom_id="m2:scene:choices", row=0)
    async def choices(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await open_pending(interaction, self.game)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(
        label="Safety pause", custom_id="m2:scene:pause", style=discord.ButtonStyle.danger, row=0
    )
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        from girlframe.services.ledger import CampaignLedger

        ledger = CampaignLedger(self.game.store)
        viewer = viewer_from_interaction(interaction)
        try:
            await threaded(
                lambda: ledger.safety(
                    viewer, str(interaction.id), ledger.status(viewer)["revision"], pause=True
                )
            )
            await reply(
                interaction,
                (
                    "Your OOC safety pause is saved. No reason or fictional penalty. "
                    "/safety resume clears your pause."
                ),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Latest action / recovery", custom_id="m2:scene:recovery", row=0)
    async def recovery(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            scene = await threaded(
                lambda: self.game.scene_info(
                    viewer_from_interaction(interaction), interaction.channel_id or 0
                )
            )
            if not scene["lock"]:
                await reply(interaction, "No saved lock in this scene.")
                return
            await reply(
                interaction,
                "Current scene action `"
                + scene["lock"]["action_id"]
                + "` · "
                + scene["lock"]["state"]
                + ". Staff: /campaign play_recovery. Saved choices: /choice resume.",
            )
        except WorkflowError as error:
            await reply(interaction, str(error))


class StatePages(discord.ui.View):
    def __init__(self, game: GameService, owner: int):
        super().__init__(timeout=600)
        self.game = game
        self.owner = owner
        self.index = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await reply(interaction, "This sheet belongs to another player.")
            return False
        return True

    async def show(self, interaction: discord.Interaction) -> None:
        sheet = await threaded(lambda: self.game.sheet(viewer_from_interaction(interaction)))
        lines = [
            "Callsign: " + sheet["callsign"],
            "Girl: " + sheet["girl"],
            "Frame: " + sheet["frame"],
            "Revision: " + str(sheet["revision"]),
            "Heat: " + str(sheet["heat"]),
            "Permissions: " + str(sheet["permissions"]),
        ]
        lines += [
            "Identity: " + entity_label(x) + (" [marked]" if x["marked"] else "")
            for x in sheet["identities"]
        ]
        lines += [
            "Asset: "
            + x["name"]
            + (" [damaged]" if x["damaged"] else "")
            + " — "
            + x["description"]
            for x in sheet["assets"]
        ]
        lines += [
            "Tag: " + x["label"] + (" [marked]" if x["marked"] else "") for x in sheet["tags"]
        ]
        lines += ["Helpless against: " + str(x) for x in sheet["helpless_against"]]
        obligations = await threaded(
            lambda: self.game.own_obligations(viewer_from_interaction(interaction))
        )
        lines += [
            "Pending obligation: " + x["kind"].replace("_", " ") + " — " + str(x["details"])
            for x in obligations
        ]
        pages = []
        current = ""
        for line in lines:
            for start in range(0, len(line), 1500):
                part = clean(line[start : start + 1500])
                if len(current) + len(part) > 1700:
                    pages.append(current)
                    current = ""
                current += part + "\n"
        if current:
            pages.append(current)
        self.index = min(max(self.index, 0), len(pages) - 1)
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index >= len(pages) - 1
        await reply(
            interaction,
            "**Current private character state**\n"
            + pages[self.index]
            + f"\nPage {self.index + 1}/{len(pages)} · Refresh reads current saved state.",
            self,
        )

    @discord.ui.button(label="Previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        self.index -= 1
        await interaction.response.defer()
        await self.show(interaction)

    @discord.ui.button(label="Next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        self.index += 1
        await interaction.response.defer()
        await self.show(interaction)

    @discord.ui.button(label="Refresh")
    async def refresh(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer()
        await self.show(interaction)


def register_game(tree: app_commands.CommandTree, guild_id: int, game: GameService) -> None:
    guild = discord.Object(id=guild_id)
    character = tree.get_command("character", guild=guild)
    campaign = tree.get_command("campaign", guild=guild)
    assert isinstance(character, app_commands.Group) and isinstance(campaign, app_commands.Group)

    @character.command(
        name="activate", description="Review public fields and confirm your M2 character activation"
    )
    async def activate(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            game.gate()
            review = await threaded(
                lambda: CreationReviewService(game.store).get(viewer_from_interaction(interaction))
            )

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                await threaded(
                    lambda: game.activate(
                        viewer_from_interaction(current),
                        str(current.id),
                        review.fingerprint,
                        tuple(values.get("public", ())),
                    )
                )
                return "Activated. /sheet shows saved state. Creation editors cannot reset it."

            fields = [
                menu(
                    "public",
                    "Optional public sheet fields",
                    sorted(PUBLIC_FIELDS),
                    0,
                    len(PUBLIC_FIELDS),
                    False,
                ),
                Field(
                    "ack",
                    "Confirm permanent activation",
                    (("yes", "Activate this reviewed character"),),
                ),
            ]
            form = NativeForm(
                interaction.user.id,
                "Activate " + review.sheet.activation_callsign,
                (
                    "Only selected fields become public. Saved resources cannot be "
                    "reset by activation. A current complete saved review is required."
                ),
                fields,
                submit,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @app_commands.command(
        name="play", description="Choose a supported Play and prepare your roll privately"
    )
    @app_commands.guild_only()
    async def play(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await open_play(interaction, game)
        except WorkflowError as error:
            await reply(interaction, str(error))

    choice = app_commands.Group(
        name="choice", description="Resume durable human Play decisions", guild_only=True
    )

    @choice.command(name="resume", description="Show all your pending Play responses")
    async def resume(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await open_pending(interaction, game)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @choice.command(name="show", description="View a saved action and its immutable receipt")
    async def show(interaction: discord.Interaction, action: str) -> None:
        def operation() -> str:
            data = game.inspect(viewer_from_interaction(interaction), action)
            lines = [str(data["play"]).replace("_", " ") + " · " + data["state"]]
            receipt = data["receipt"]
            if receipt:
                lines.append("Receipt " + receipt["id"] + " · " + expression(receipt))
            if data["result"]:
                for key, value in data["result"].items():
                    lines.append(str(key).replace("_", " ") + ": " + str(value))
            return clean("\n".join(lines))[:1900]

        await private_operation(interaction, operation)

    @campaign.command(
        name="scene_bind", description="Preview and bind a text channel as an M2 scene (staff)"
    )
    async def bind(interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            game.gate()
            game.store.administrator(viewer_from_interaction(interaction))
            if interaction.guild is None or channel.guild.id != guild_id:
                raise WorkflowError("Choose a channel in the configured guild.")
            from girlframe.discord_adapter.m2_gateway import DiscordGameGateway

            await DiscordGameGateway(interaction.guild, game).snapshot(channel.id, [])

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                await threaded(
                    lambda: game.bind_scene(
                        viewer_from_interaction(current), str(current.id), channel.id
                    )
                )
                return "Scene bound. All participants must /campaign scene_join in it."

            form = NativeForm(
                interaction.user.id,
                "Bind scene: " + channel.name,
                (
                    "Pending Plays will deny new ordinary chat and thread messages, "
                    "then restore only bot-owned permission bits. Administrator bypass "
                    "remains possible."
                ),
                [Field("ack", "Confirm this scene channel", (("yes", "Bind this channel"),))],
                submit,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="scene_join", description="Join the current bound scene as yourself")
    async def join(interaction: discord.Interaction) -> None:
        await private_operation(
            interaction,
            lambda: (
                "Scene joined: "
                + str(
                    game.join_scene(
                        viewer_from_interaction(interaction),
                        str(interaction.id),
                        interaction.channel_id or 0,
                    )["channel"]
                )
            ),
        )

    @campaign.command(
        name="scene_leave", description="Leave the current scene after its pending action resolves"
    )
    async def leave(interaction: discord.Interaction) -> None:
        await private_operation(
            interaction,
            lambda: (
                "Left scene: "
                + str(
                    game.leave_scene(
                        viewer_from_interaction(interaction),
                        str(interaction.id),
                        interaction.channel_id or 0,
                    )["channel"]
                )
            ),
        )

    @campaign.command(name="scene_close", description="Close this resolved scene (staff)")
    async def close(interaction: discord.Interaction) -> None:
        await private_operation(
            interaction,
            lambda: (
                "Scene closed: "
                + str(
                    game.close_scene(
                        viewer_from_interaction(interaction),
                        str(interaction.id),
                        interaction.channel_id or 0,
                    )["channel"]
                )
            ),
        )

    @campaign.command(
        name="order", description="Record a direct order for a lower-status Pilot in this scene"
    )
    async def order(
        interaction: discord.Interaction, member: discord.Member, instruction: str
    ) -> None:
        await private_operation(
            interaction,
            lambda: (
                "Order recorded. Scene lock and target response queued. Action `"
                + game.issue_order(
                    viewer_from_interaction(interaction),
                    str(interaction.id),
                    interaction.channel_id or 0,
                    member.id,
                    instruction,
                )["action_id"]
                + "`."
            ),
        )

    @campaign.command(
        name="play_recovery", description="Review and confirm staff recovery for a root Play"
    )
    @app_commands.choices(
        operation=[
            app_commands.Choice(name="Abort pending action; keep spent resources", value="abort"),
            app_commands.Choice(name="Reconcile and retry delivery / lock", value="retry"),
            app_commands.Choice(name="Restore completed / aborted lock", value="restore"),
        ]
    )
    async def recover(
        interaction: discord.Interaction, action: str, operation: app_commands.Choice[str]
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
            viewer = viewer_from_interaction(current)
            if operation.value == "abort":
                await threaded(lambda: game.abort(viewer, str(current.id), action))
            else:
                await threaded(
                    lambda: game.retry_recovery(
                        viewer, str(current.id), action, restore_only=operation.value == "restore"
                    )
                )
            return (
                "Staff recovery recorded. Permission conflicts still need review. "
                "Receipts and prior spends are preserved."
            )

        form = NativeForm(
            interaction.user.id,
            "Recover root Play",
            (
                "Abort never refunds committed resources. Explicit delivery retry "
                "may duplicate a Discord message with the same receipt; it never "
                "rolls again."
            ),
            [Field("ack", "Confirm " + operation.value, (("yes", "Confirm staff recovery"),))],
            submit,
        )
        await reply(interaction, form.text(), form)

    @character.command(
        name="followthrough", description="Review and fulfill your recorded future obligations"
    )
    async def followthrough(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            rows = await threaded(
                lambda: game.own_obligations(viewer_from_interaction(interaction))
            )
            supported = [x for x in rows if x["kind"] in ("flirt_followthrough", "reject_tag")]
            if not supported:
                await reply(
                    interaction,
                    "No implemented follow-through action is pending. Other saved obligations: "
                    + ", ".join(x["kind"] for x in rows),
                )
                return

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                result = await threaded(
                    lambda: game.fulfill(
                        viewer_from_interaction(current),
                        str(current.id),
                        current.channel_id or 0,
                        one(values, "obligation"),
                        values["text"],
                    )
                )
                return (
                    (
                        "Follow-through queued. Any Bond improvement waits for the other "
                        "player. Action `"
                    )
                    + str(result["action_id"])
                    + "`."
                )

            form = NativeForm(
                interaction.user.id,
                "Future obligations",
                (
                    "Describe the actual fictional follow-through. The scene is locked "
                    "before applying effects; no automatic consent or Bond improvement."
                ),
                [
                    Field(
                        "obligation",
                        "Choose obligation",
                        tuple(
                            (x["id"], x["kind"].replace("_", " ") + " · " + x["id"][:8])
                            for x in supported
                        ),
                    ),
                    text("text", "Describe what you do"),
                ],
                submit,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @character.command(name="state", description="Read your current private M2 sheet with paging")
    async def current_state(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await StatePages(game, interaction.user.id).show(interaction)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @character.command(
        name="recover", description="Take an actual moment alone to recover from Helplessness"
    )
    async def recover_character(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            game.gate()
            sheet = await threaded(lambda: game.sheet(viewer_from_interaction(interaction)))
            girls = [x for x in sheet["assets"] if x["family"] == "girl"]
            needs_asset = bool(girls) and all(x["damaged"] for x in girls)
            fields = [
                text("context", "Describe your moment alone"),
                Field(
                    "ack",
                    "Confirm the printed recovery trigger",
                    (("yes", "I have a moment alone to compose myself"),),
                ),
            ]
            if needs_asset:
                fields.append(entities("asset", "Choose a Girl Asset to undamage", girls))

            async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
                await threaded(
                    lambda: game.recover_helpless(
                        viewer_from_interaction(current),
                        str(current.id),
                        sheet["revision"],
                        values["context"],
                        one(values, "asset"),
                    )
                )
                return "Recovery saved. Your current sheet is available through /character state."

            form = NativeForm(
                interaction.user.id,
                "Recover from Helplessness",
                (
                    "Take an actual moment alone (book PDF 15). "
                    "This recovery cannot interrupt a pending Play."
                ),
                fields,
                submit,
            )
            await reply(interaction, form.text(), form)
        except WorkflowError as error:
            await reply(interaction, str(error))

    tree.add_command(play, guild=guild)
    tree.add_command(choice, guild=guild)
