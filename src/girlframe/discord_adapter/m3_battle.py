"""Private battle declarations, actual adjudication and original-owner native choices."""

import asyncio
from typing import Any

import discord

from girlframe.discord_adapter.bot import viewer_from_interaction
from girlframe.discord_adapter.m2_forms import Field, NativeForm
from girlframe.discord_adapter.onboarding import reply
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration, Defense
from girlframe.services.m2_game import GameService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_battle_npc import NpcDamageService

LABELS = {
    "collateral_damage": "Reasonable collateral is destroyed",
    "handler_play": "Actual Handler Play",
    "damage_actor_asset": "Damage an attacker Asset",
    "make_play_against_actor": "Make my own Play against attacker",
    "actor_helpless": "Leave the attacker Helpless",
    "target_dies_with_handler_play": "Die anyway; optional Handler Play",
}


def _princess_prepared(parent: dict[str, Any] | None) -> PlayInput | None:
    if parent is None or parent["kind"] != "princess_sex_child":
        return None
    body = parent["body"]
    return PlayInput(
        play=body["play"],
        source_work=body["source_work"],
        parent=parent["parent"],
        target_actor=ActorRef.model_validate(body["target"]),
        context=body["context"],
        trigger_confirmed=True,
        heat=0,
    )


async def open_declaration(
    interaction: discord.Interaction,
    service: BattleService,
    *,
    parent: dict[str, Any] | None = None,
) -> None:
    channel = int(parent["channel"]) if parent else int(interaction.channel_id or 0)
    data = await asyncio.to_thread(
        service.preview,
        viewer_from_interaction(interaction),
        channel,
        required=_princess_prepared(parent),
    )
    own = [
        x
        for x in data["actors"]
        if x["owned"]
        and (
            x["ref"]["kind"] == "pilot"
            or x["ref"]["kind"] == "external_pilot"
            and x["girl"] == "harpy"
            and x["heat"] is not None
        )
    ]
    targets = [x for x in data["actors"] if x["ref"]["kind"] != "pilot" or not x["owned"]]
    if data.get("required_actor"):
        own = [x for x in own if x["ref"] == data["required_actor"]]
        targets = [x for x in data["actors"] if x["ref"] != data["required_actor"]]
    if parent is not None:
        if parent["body"].get("actor"):
            own = [x for x in own if x["ref"] == parent["body"]["actor"]]
        fixed_target = parent["body"].get("attacker") or parent["body"].get("target")
        if fixed_target:
            targets = [x for x in targets if x["ref"] == fixed_target]
    if not own or not targets:
        await reply(interaction, "Join your actual Pilot and opposing actor to this scene first.")
        return

    async def choose(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        actor = next(x for x in own if x["token"] == values["actor"][0])
        target = next(x for x in targets if x["token"] == values["target"][0])
        play = values["play"][0]

        async def declare(next_interaction: discord.Interaction, details: dict[str, Any]) -> str:
            proposal = Declaration(
                play=play,
                actor=ActorRef.model_validate(actor["ref"]),
                target=ActorRef.model_validate(target["ref"]),
                attacking_asset=details["asset"][0],
                target_asset=details["target_asset"][0] if play == "all_out_assault" else None,
                actor_sha256=actor["sha256"],
                target_sha256=target["sha256"],
                account=details["account"],
            )
            result = await asyncio.to_thread(
                service.propose,
                viewer_from_interaction(next_interaction),
                str(next_interaction.id),
                data["revision"],
                channel,
                proposal,
                parent=parent["parent"] if parent else None,
                **(
                    {"source_work": parent["body"]["source_work"]}
                    if parent
                    and parent["kind"]
                    in (
                        "red_queen_child",
                        "princess_sex_child",
                        "ankou_effect_child",
                        "changeling_interrupt",
                        "changeling_pause",
                    )
                    else {}
                ),
            )
            return "Actual declaration saved for opening/reach review: " + str(result["id"])

        strike_assets = actor["core_assets"] if play == "go_for_the_core" else actor["assets"]
        if not strike_assets:
            return "Choose a real owned Asset for this printed strike."
        fields = [
            Field(
                "asset",
                "Your actual Asset",
                tuple(
                    (x["id"], x["name"] + (" (damaged)" if x.get("damaged") else ""))
                    for x in strike_assets
                ),
            )
        ]
        if play == "all_out_assault":
            if not target["assets"]:
                return "All Out Assault needs an actual opposing Asset; this actor has none."
            fields.append(
                Field(
                    "target_asset",
                    "Actual opposing Asset",
                    tuple((x["id"], x["name"]) for x in target["assets"]),
                )
            )
        fields.append(Field("account", "Describe your opening and decisive action", paragraph=True))
        form = NativeForm(
            current.user.id,
            "Declare actual battle",
            "Choose the actual owned resources.",
            fields,
            declare,
        )
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        interaction.user.id,
        "Battle declaration",
        "Declare before consuming Heat or dice.",
        [
            Field("actor", "Your actual acting body", tuple((x["token"], x["name"]) for x in own)),
            Field(
                "play",
                "Choose your Play",
                (("all_out_assault", "Required All Out Assault"),)
                if parent and parent["kind"] in ("red_queen_child", "princess_sex_child")
                else (
                    ("all_out_assault", "All Out Assault"),
                    ("go_for_the_core", "Go For the Core"),
                ),
            ),
            Field(
                "target", "Actual opposing actor", tuple((x["token"], x["name"]) for x in targets)
            ),
        ],
        choose,
    )
    await reply(interaction, form.text(), form)


async def open_context(
    interaction: discord.Interaction, service: BattleService, identity: str
) -> None:
    source = await asyncio.to_thread(
        service.context, viewer_from_interaction(interaction), identity
    )
    if source["channel"] is None:
        await reply(
            interaction,
            "This declaration's original scene has ended. "
            "Declare combat in a current joined scene.",
        )
        return
    if (source.get("princess_child") or {}).get("child"):
        from girlframe.discord_adapter.m2_ui import open_pending

        await open_pending(interaction, service.game)
        return
    data = await asyncio.to_thread(
        service.preview,
        viewer_from_interaction(interaction),
        source["channel"],
        required=_princess_prepared((source.get("princess_child") or {}).get("descriptor")),
    )
    value = next((x for x in data["contexts"] if x["id"] == identity), None)
    if value is None:
        await reply(
            interaction, "Open your actual source battle declaration in its original scene."
        )
        return
    if value["state"] == "confirmed":
        if (value.get("source_author") or value["owner"]) != interaction.user.id:
            await reply(
                interaction, "Opening and reach are confirmed for the original actor's owner."
            )
            return
        actor = next(x for x in data["actors"] if x["ref"] == value["declaration"]["actor"])
        role_service = None
        role_data = None
        princess_child = source.get("princess_child")
        if princess_child:
            resources = dict(
                heat=princess_child["heat"],
                identities=[
                    *princess_child["identities"],
                    *princess_child["additional_identities"],
                ],
                revision=princess_child["sheet_revision"],
            )
        elif actor["ref"]["kind"] == "external_pilot":
            from girlframe.services.m3_actor_plays import ActorPlayService

            role_service = ActorPlayService(service.game)
            role_data = await asyncio.to_thread(
                role_service.preview,
                viewer_from_interaction(interaction),
                data["channel"],
                ActorRef.model_validate(actor["ref"]),
            )
            resources = role_data["actor"]
        else:
            resources = await asyncio.to_thread(
                service.game.sheet, viewer_from_interaction(interaction)
            )
        identities = tuple((x["id"], x["name"]) for x in resources["identities"] if not x["marked"])
        from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
        from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
        from girlframe.services.m3_dampener import DampenerService

        dampener_controls = (
            []
            if princess_child
            else await dampener_fields(
                interaction, DampenerService(service.game), ActorRef.model_validate(actor["ref"])
            )
        )

        from girlframe.discord_adapter.m3_ankou_controls import pulse_fields, selected_pulse

        pulse_controls = (
            await pulse_fields(interaction, service.game)
            if not princess_child
            and actor["ref"]["kind"] == "pilot"
            and value["declaration"]["play"] == "all_out_assault"
            else []
        )

        async def start(current: discord.Interaction, values: dict[str, Any]) -> str:
            declared = value["declaration"]
            chosen = values["identity"][0]
            prepared = PlayInput(
                play=declared["play"],
                heat=int(values["heat"][0]),
                dampener_modifier=dampener_modifier(values),
                ankou_pulse=selected_pulse(values),
                identity=None if chosen == "none" else chosen,
                gain=int(values["gain"][0]),
                pair_share=int(values["pair_share"][0]),
                target_actor=ActorRef.model_validate(declared["target"]),
                attacking_asset=declared["attacking_asset"],
                target_asset=declared["target_asset"],
                battle_context=identity,
                context=princess_child["context"] if princess_child else declared["account"],
                trigger_confirmed=True,
                piloting=bool(actor["piloting"]),
                parent=value["source_action"],
                source_work=source.get("source_work"),
            )
            if role_service is not None and role_data is not None:
                judge = role_data["adjudicator"]["ref"]
                result = await asyncio.to_thread(
                    role_service.begin,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["channel"],
                    ActorRef.model_validate(actor["ref"]),
                    resources["source_sha256"],
                    ActorRef.model_validate(judge) if judge else None,
                    role_data["cast_revision"],
                    prepared,
                )
            else:
                result = await asyncio.to_thread(
                    service.game.begin,
                    viewer_from_interaction(current),
                    str(current.id),
                    data["channel"],
                    resources["revision"],
                    prepared,
                )
            return "Actual battle confirmed; scene chat is held before the one roll. Action " + str(
                result["action_id"]
            )

        form = NativeForm(
            interaction.user.id,
            "Start confirmed battle",
            "Opening and reach are source-confirmed.",
            [
                Field(
                    "identity",
                    "Optional owned Identity",
                    (("none", "Do not mark an Identity"),) + identities,
                ),
                Field("gain", "Identity Heat gained", tuple((str(x), str(x)) for x in range(6))),
                Field(
                    "pair_share",
                    "Paired Heat sent to Pair",
                    tuple((str(x), str(x)) for x in range(6)),
                ),
                Field(
                    "heat",
                    "Heat to spend",
                    tuple((str(x), str(x)) for x in range(resources["heat"] + 6)),
                ),
            ]
            + dampener_controls
            + pulse_controls,
            start,
        )
        await reply(interaction, form.text(), form)
        return
    if value["adjudicator"] != interaction.user.id:
        await reply(
            interaction, "Your actual declaration awaits the appointed adjudicator's review."
        )
        return
    yesno = (("yes", "Yes, established by the actual Conversation"), ("no", "No, not established"))

    defenses = await asyncio.to_thread(
        service.defenses, viewer_from_interaction(interaction), identity
    )

    async def confirm(current: discord.Interaction, values: dict[str, Any]) -> str:
        await asyncio.to_thread(
            service.confirm,
            viewer_from_interaction(current),
            str(current.id),
            data["revision"],
            identity,
            opening=values["opening"][0] == "yes",
            reach=values["reach"][0] == "yes",
            outside_permission=values["outside"][0] == "yes",
            indirect=values["indirect"][0] == "yes",
            evidence=values["evidence"],
            core_capability_confirmed=values.get("core_capability", ("no",))[0] == "yes",
            actor_outside_frame=values.get("actor_outside", ("unknown",))[0] == "yes"
            if "actor_outside" in values
            else None,
            target_outside_frame=values.get("target_outside", ("unknown",))[0] == "yes"
            if "target_outside" in values
            else None,
            defense=Defense.model_validate(
                next(x["value"] for x in defenses if x["id"] == values["defense"][0])
                | {"account": values.get("defense_account", "")}
            )
            if values.get("defense", ("none",))[0] != "none"
            else None,
            dormant_awakened=values.get("awakened", ("no",))[0] == "yes",
            dormant_close=values.get("close", ("no",))[0] == "yes",
        )
        return "Actual source battle facts confirmed before dice."

    review_fields = [
        Field("opening", "Actual opening exists", yesno),
        Field("reach", "Actual target is reachable", yesno),
        Field("outside", "Outside-Frame capability established", yesno),
        Field("indirect", "Actual indirect attack", yesno),
        Field("evidence", "Record the actual supporting facts", paragraph=True),
    ]
    target = next((x for x in data["actors"] if x["ref"] == value["declaration"]["target"]), None)
    for key, role in (
        ("actor", value["declaration"]["actor"]),
        ("target", value["declaration"]["target"]),
    ):
        body = next((x for x in data["actors"] if x["ref"] == role), None)
        if body is not None and body["rules"] == "handler_girl":
            review_fields.append(
                Field(key + "_outside", "Actual " + key + " Handler body is outside a Frame", yesno)
            )
    if defenses:
        review_fields.extend(
            [
                Field(
                    "defense",
                    "Preexisting NPC defense",
                    (("none", "No source-backed defense"),)
                    + tuple((x["id"], x["label"]) for x in defenses),
                ),
                Field(
                    "defense_account",
                    "How does that actual defense protect these vitals?",
                    paragraph=True,
                    required=False,
                ),
            ]
        )
    if target and target["gorgon_class"] == "dormant":
        review_fields.extend(
            [
                Field("awakened", "Attack actually forces this Dormant awake", yesno),
                Field("close", "If awakening: source attacker actually gets close", yesno),
            ]
        )
    if value["declaration"]["play"] == "go_for_the_core":
        review_fields.append(
            Field("core_capability", "Declared Asset can actually make this decisive strike", yesno)
        )
    form = NativeForm(
        interaction.user.id,
        "Review actual battle opening",
        value["declaration"]["account"],
        review_fields,
        confirm,
    )
    await reply(interaction, form.text(), form)


async def open_battle(interaction: discord.Interaction, game: GameService, identity: str) -> None:
    data = await asyncio.to_thread(game.decision, viewer_from_interaction(interaction), identity)
    detail = data["battle"]
    kind = data["kind"]
    if kind == "battle_aggressive_damage":
        from girlframe.discord_adapter.m3_gorgon_aggressive import open_aggressive
        from girlframe.services.m3_gorgon_aggressive import AggressiveService

        await open_aggressive(interaction, AggressiveService(game.store), detail["work_id"])
        return
    if kind == "battle_collateral":
        from girlframe.discord_adapter.m3_collateral import open_collateral
        from girlframe.services.m3_collateral import CollateralService

        await open_collateral(interaction, CollateralService(game.store), detail["work_id"])
        return
    if kind in ("battle_dormant_threshold", "battle_item_void_threshold"):
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), detail["work_id"])
        return
    if kind == "battle_dormant_void":
        from girlframe.discord_adapter.m3_battle_dormant import open_dormant
        from girlframe.services.m3_battle_dormant import DormantService

        await open_dormant(interaction, DormantService(game.store, game), detail["work_id"])
        return
    if kind in ("battle_director_damage", "battle_director_helpless"):
        from girlframe.discord_adapter.m3_battle_director import open_director
        from girlframe.services.m3_battle_director import DirectorService

        await open_director(interaction, DirectorService(game.store), detail["work_id"])
        return
    if kind == "battle_handler_damage":
        from girlframe.discord_adapter.m3_handler_consequences import open_consequence
        from girlframe.services.m3_handler_consequences import HandlerConsequenceService

        await open_consequence(
            interaction,
            HandlerConsequenceService(game.store),
            data["body"]["requirement"]["details"]["consequence"],
        )
        return
    if kind in ("battle_npc_damage", "battle_npc_optional_tag"):
        await open_npc_damage(interaction, NpcDamageService(game.store), detail["work_id"])
        return
    if kind == "battle_defeat":
        from girlframe.discord_adapter.m3_defeat import open_work

        await open_work(interaction, game, detail["work_id"])
        return
    if kind == "battle_handler_play":
        from girlframe.discord_adapter.m3_handler_plays import open_play
        from girlframe.services.m3_handler_plays import HandlerPlayService

        await open_play(interaction, HandlerPlayService(game.store), detail["grant_id"])
        return
    fields = []
    if kind == "battle_counter_play":
        own = detail.get("own_plays", [])
        if own:

            async def perform(current: discord.Interaction, values: dict[str, Any]) -> str:
                selected = values["play"][0]
                fields = {"play": selected}
                if selected == "warp_evolve":
                    fields.update(
                        name=values.get("name", ""), description=values.get("description", "")
                    )
                await asyncio.to_thread(
                    game.respond,
                    viewer_from_interaction(current),
                    str(current.id),
                    identity,
                    data["revision"],
                    ChoiceAnswer(fields=fields, text=values["account"]),
                )
                return "Your actual owned source Play has been performed."

            form = NativeForm(
                interaction.user.id,
                "Your source counter Play",
                "Perform the actual printed move against the original attacker.",
                [
                    Field(
                        "play", "Your actual owned Play", tuple((x["id"], x["label"]) for x in own)
                    ),
                    Field("account", "Describe what you actually do or say", paragraph=True),
                    Field("name", "New Asset name, only if evolving", required=False),
                    Field(
                        "description",
                        "New Asset details, only if evolving",
                        paragraph=True,
                        required=False,
                    ),
                ],
                perform,
            )
            await reply(interaction, form.text(), form)
            return
        parent = data | dict(action_id=data["parent"], actor=detail["counter_actor"])

        async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
            if values["type"][0] == "combat":
                await open_declaration(current, BattleService(game.store), parent=parent)
            else:
                from girlframe.discord_adapter.m2_ui import open_play

                await open_play(current, game, parent=parent)
            return None

        choices: tuple[tuple[str, str], ...] = (("basic", "Make an actual basic Play"),)
        if detail["counter_actor"]["kind"] == "pilot":
            choices += (("combat", "Declare an actual combat Play"),)
        form = NativeForm(
            interaction.user.id,
            "Choose your actual counter",
            "The original battle remains held through this actual child.",
            [Field("type", "Source-owned counter", choices)],
            select,
        )
        await reply(interaction, form.text(), form)
        return
    if kind == "battle_assault_table":
        fields = [
            Field(
                "decision",
                "Does opposing Asset have a vast advantage?",
                (("yes", "I agree it has a vast advantage"), ("no", "I do not agree")),
            ),
            Field("account", "Your actual reasoning", paragraph=True),
        ]
    elif kind == "battle_handler":
        fields = [
            Field(
                "options",
                "Choose one or two actual consequences",
                tuple((x, LABELS[x]) for x in detail["options"]),
                maximum=2,
            ),
            Field("account", "Actual collateral, if selected", paragraph=True, required=False),
        ]
    elif kind == "battle_counter":
        fields = [
            Field(
                "options",
                "Your optional counters",
                (("pass", "Explicitly decline all counters"),)
                + tuple((x, LABELS[x]) for x in detail["options"]),
                maximum=detail["maximum"],
            )
        ]
    elif kind in ("battle_low_damage", "battle_actor_damage", "battle_target_damage"):
        fields = [
            Field(
                "asset",
                "Actual undamaged Asset",
                tuple((x["id"], x["name"]) for x in detail["assets"]),
            )
        ]
    else:
        await reply(interaction, "Resume this actual source child Play through its saved controls.")
        return

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        if kind == "battle_assault_table":
            answer = ChoiceAnswer(flag=values["decision"][0] == "yes", text=values["account"])
        elif kind == "battle_handler":
            answer = ChoiceAnswer(options=values["options"], text=values.get("account", ""))
        elif kind == "battle_counter":
            answer = (
                ChoiceAnswer(flag=False)
                if values["options"] == ("pass",)
                else ChoiceAnswer(options=values["options"])
            )
        else:
            answer = ChoiceAnswer(fields={"asset": values["asset"][0]})
        await asyncio.to_thread(
            game.respond,
            viewer_from_interaction(current),
            str(current.id),
            identity,
            data["revision"],
            answer,
        )
        return "Actual owned battle choice saved; required effects keep this scene held."

    form = NativeForm(
        interaction.user.id,
        "Battle: your actual choice",
        "Only the printed source owner may answer.",
        fields,
        submit,
    )
    await reply(interaction, form.text(), form)


async def open_npc_damage(
    interaction: discord.Interaction, service: NpcDamageService, identity: str
) -> None:
    data = await asyncio.to_thread(service.get, viewer_from_interaction(interaction), identity)
    if data["state"] == "resolved":
        await reply(interaction, "This actual NPC consequence is resolved.")
        return
    if data["phase"] == "waiting_void":
        await reply(
            interaction,
            "The actual item transfer awaits its source Void consequences in your requests inbox.",
        )
        return
    if data["phase"] == "optional_tag":
        if not data["can_respond"]:
            await reply(
                interaction,
                "Your actual consequence is saved and awaits "
                "the source Handler's optional Tag choice.",
            )
            return

        async def tag(current: discord.Interaction, values: dict[str, Any]) -> str:
            value = values.get("tag", "") if values["decision"][0] == "yes" else None
            await asyncio.to_thread(
                service.optional_tag,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                value,
            )
            return "The Handler's actual optional Tag decision is saved."

        form = NativeForm(
            interaction.user.id,
            "NPC: optional Handler Tag",
            data["target"],
            [
                Field(
                    "decision",
                    "Your actual Tag choice",
                    (("no", "Do not give a Tag"), ("yes", "Give an appropriate Tag")),
                ),
                Field("tag", "Tag, only if giving one", required=False),
            ],
            tag,
        )
        await reply(interaction, form.text(), form)
        return
    options = [
        ("injure_tag", "Gravely injure and give a Tag"),
        ("move", "Force an actual move"),
        ("advantage", "Gain an actual Conversation advantage"),
        ("kill", "Kill this actual NPC"),
    ]
    if not data.get("can_harm", True):
        options = [x for x in options if x[0] not in ("injure_tag", "kill")]
    if data["can_take"] and data["items"]:
        options.append(("take_item", "Take an actual held object"))

    async def select(current: discord.Interaction, values: dict[str, Any]) -> str | None:
        effect = values["effect"][0]
        fields = [Field("account", "Describe the actual consequence", paragraph=True)]
        if effect == "injure_tag":
            fields.append(Field("tag", "The actual injury Tag"))
        if effect == "take_item":
            fields.append(
                Field(
                    "item",
                    "Actual held object",
                    tuple((x["id"], x["label"]) for x in data["items"]),
                )
            )
            if data["replacements"]:
                fields.append(
                    Field(
                        "replace",
                        "Owned Asset to replace only at the cap",
                        (("none", "No mechanical replacement needed"),)
                        + tuple((x["id"], x["name"]) for x in data["replacements"]),
                    )
                )
        if effect == "move":
            fields.append(
                Field(
                    "location",
                    "Actual destination",
                    tuple((x["id"], x["name"]) for x in data["locations"]),
                )
            )

        async def apply(current: discord.Interaction, details: dict[str, Any]) -> str:
            await asyncio.to_thread(
                service.respond,
                viewer_from_interaction(current),
                str(current.id),
                identity,
                data["revision"],
                effect,
                details["account"],
                tag=details.get("tag", ""),
                item=details["item"][0] if "item" in details else "",
                location=details["location"][0] if "location" in details else "",
                replace=details["replace"][0]
                if "replace" in details and details["replace"][0] != "none"
                else None,
            )
            return "Actual NPC consequence saved."

        form = NativeForm(current.user.id, "NPC consequence details", data["target"], fields, apply)
        await reply(current, form.text(), form)
        return None

    form = NativeForm(
        interaction.user.id,
        "NPC Asset consequence",
        data["target"],
        [Field("effect", "Actual attacker's choice", tuple(options))],
        select,
    )
    await reply(interaction, form.text(), form)
