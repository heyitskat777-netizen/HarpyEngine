"""Native M2 Play and owned-response wizards; all state changes go through services."""

from typing import Any, Literal, cast

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
from girlframe.engine.m3_girl_runtime_state import has_rule, keep_automatic
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
        "kicked_care": "How do you want to care for me?",
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
    if decision.get("clone_flirt"):
        from girlframe.discord_adapter.m3_clone_am import choice_fields as clone_fields

        return clone_fields(decision)
    kind = decision["kind"]
    own = decision["own"]
    result = decision["result"]
    level = result.get("tier")
    identities = (
        [
            x
            for x in own["identities"]
            + own.get("additional_identities", [])
            + own.get("marked_maxims", [])
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
        partner_tags = decision.get("gender_man_tags", ())
        options = ("pass", "tag", "gender_man") if partner_tags else ("pass", "tag")
        visible_tags = list(decision["tags"]) + [
            dict(id="gender-partner:" + x["id"], name="Partner: " + x["label"])
            for x in partner_tags
        ]
        fields = [
            menu("options", "Pass or propose one Tag", options),
            entities(
                "denied", "Relevant observed Tag (for Tag proposal)", visible_tags, 0, 1, False
            ),
            menu(
                "number",
                "Ordinary Tag direction (empty for partner rule)"
                if partner_tags
                else "Tag direction",
                ("-1", "1"),
                required=False,
            ),
            text(
                "text",
                "Ordinary Tag relevance (empty for partner rule)"
                if partner_tags
                else "Why is the Tag relevant?",
                False,
            ),
        ]
        if (
            own
            and own.get("owner") == decision["actor"]
            and not own.get("status_marked")
            and has_rule(own, "girl.alpha.nothing-more-than-a-hound", "ALPHA")
        ):
            fields.append(
                menu(
                    "fields.status",
                    "Optional Dog Status modifier",
                    ("0", "-1", "1"),
                    required=False,
                )
            )
        from girlframe.discord_adapter.m3_tag_markers import marker_field

        source_marker = marker_field(decision)
        if source_marker is not None:
            fields.append(source_marker)
    elif kind == "control_ritual_create":
        fields = [
            flags("Develop my Control Ritual?"),
            text("text", "Describe my Control Ritual (up to 120 characters)", False),
        ]
    elif kind == "tag_resolution" and decision.get("cute_uniform_tag"):
        fields = [
            menu("options", "Your uniform response", ("reject", "embrace", "embrace_asset")),
            entities(
                "denied",
                "Ordinary Identity replaced for Identity embrace",
                [x for x in own["identities"] if not x["protected"]],
                0,
                1,
                False,
            ),
            Field(
                "fields.replace",
                "Girl Asset replaced only if at capacity",
                tuple((x["id"], x["name"]) for x in decision["cute_uniform_replacements"]),
                0,
                1,
                required=False,
            ),
        ]
    elif kind == "gender_partner_tag_resolution":
        fields = [
            menu("options", "Resolve your repeated marked Tag", ("embrace", "reject")),
            entities(
                "denied",
                "Identity replaced only at capacity",
                [x for x in own["identities"] if not x["protected"]],
                0,
                1,
                False,
            ),
        ]
    elif kind == "gender_animal_tag":
        fields = [text("text", "Give the non-Animal partner an ordinary Tag")]
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
        harpy_mode = bool(own and own.get("harpy"))
        traits = tuple("beautiful" if x == "sexy" else x for x in TRAITS) if harpy_mode else TRAITS
        automatic = set(keep_automatic(own))
        retained = set(own.get("retained_plays", ())) if own else set()
        if harpy_mode:
            if "girl.princess.objectively-beautiful" in retained:
                automatic.add("beautiful")
            if "girl.alpha.itching-for-a-fight" in retained:
                automatic.add("vicious")
        if level == "mid":
            fields = [
                menu("options", "Choose two positive traits", traits, 2, 2),
                menu(
                    "denied",
                    "Choose one distinct negative trait",
                    tuple(x for x in traits if x not in automatic),
                ),
            ]
        elif level == "low":
            fields = [menu("options", "Choose one positive trait", traits)]
        else:
            fields = [text("text", "Take a Tag: write its label")]
        if decision.get("cute_uniforms"):
            fields.append(
                Field(
                    "fields.cute_uniform",
                    "Also choose while wearing the uniform",
                    (("helpless_adorable", "I seem helpless and adorable"),),
                )
            )
        if has_rule(own, "girl.oldgen.elder-bitch", "OLDGEN") or (
            harpy_mode and "girl.oldgen.elder-bitch" in retained
        ):
            fields.append(flags("Also choose experienced?"))
        if decision.get("enforcer_keep", {}).get("available"):
            for key, label in (
                ("pavlov_good_soldier", "Also choose Good soldier"),
                ("pavlov_bliss", "Also choose Feels as good as sex"),
            ):
                fields.append(
                    Field("fields." + key, label, (("yes", "Yes"),), minimum=0, required=False)
                )
    elif kind == "handler_keep":
        fields = [flags("Is it enough?"), text("text", "Explain the outcome")]
    elif kind == "harpy_sensor_answers":
        fields = [
            text("text", "Answer every question honestly"),
            flags("These answers are honest and complete?"),
        ]
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
                menu(
                    "options",
                    "Choose the refusal branch",
                    ("tag_heat", "reject_tag", "follow")
                    + (("remove_broken",) if decision.get("alpha_remove_broken") else ()),
                ),
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
        fields = [
            menu(
                "options", "Ask the other player", decision.get("flirt_questions", FLIRT_QUESTIONS)
            ),
            unmark(2),
        ]
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
                tuple(
                    x
                    for x in (
                        "obedient",
                        "immediate",
                        "hesitant",
                        "mouthing_off",
                        "gritted_teeth",
                        "disobey",
                    )
                    if x != "disobey" or decision.get("am_can_refuse", True)
                ),
            )
        ]
        if decision.get("gender_spoken_no"):
            fields.extend(
                [
                    Field(
                        "fields.spoken_no",
                        "Did you actually say No in character?",
                        YES,
                        0,
                        1,
                        required=False,
                    ),
                    text("text", "Your actual spoken words (if recording No)", False),
                ]
            )
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
    if decision["kind"].startswith("vat_doll_"):
        from girlframe.discord_adapter.m3_vatgrown import open_choice as open_doll_choice

        await open_doll_choice(interaction, game, decision)
        return
    if decision["kind"].startswith("oldgen_sex_"):
        from girlframe.discord_adapter.m3_oldgen_sex import open_choice as open_oldgen_sex_choice

        await open_oldgen_sex_choice(interaction, game, decision)
        return
    if decision["kind"].startswith("oldgen_"):
        from girlframe.discord_adapter.m3_oldgen import open_choice as open_oldgen_choice

        await open_oldgen_choice(interaction, game, decision)
        return
    if decision["kind"].startswith("stim_sex_"):
        from girlframe.discord_adapter.m3_stim_sex import open_choice as open_stim_choice

        await open_stim_choice(interaction, game, decision)
        return
    if decision.get("ankou_feedback") is not None:
        from girlframe.discord_adapter.m3_ankou_feedback import open_choice as open_ankou_choice

        await open_ankou_choice(interaction, game, identity)
        return
    if decision.get("princess_sex") is not None:
        from girlframe.discord_adapter.m3_princess_sex import open_choice as open_princess_choice

        await open_princess_choice(interaction, game, identity)
        return
    if decision["kind"] in ("dose_up_components", "dose_up_target_low"):
        from girlframe.discord_adapter.m3_dose_up import open_choice as open_dose_choice

        await open_dose_choice(interaction, game, decision)
        return
    if decision["kind"] == "reign_group_tag_resolution":
        from girlframe.discord_adapter.m3_reign_terror import open_resolution
        from girlframe.services.m3_reign_terror import ReignTerrorService

        await open_resolution(interaction, ReignTerrorService(game.store), identity)
        return
    if decision["kind"] == "sidearm_reconsider":
        from girlframe.discord_adapter.m3_hidden_sidearm import open_response
        from girlframe.services.m3_hidden_sidearm import HiddenSidearmService

        await open_response(interaction, HiddenSidearmService(game.store), identity)
        return
    if decision["kind"] in (
        "secretary_gunpoint",
        "secretary_response_play",
        "secretary_gunpoint_resolution",
    ):
        from girlframe.discord_adapter.m3_secretary import open_gunpoint
        from girlframe.services.m3_secretary import SecretaryService

        await open_gunpoint(interaction, SecretaryService(game.store), identity)
        return
    if decision.get("leviathan"):
        from girlframe.discord_adapter.m3_leviathan_obsession import (
            open_choice as open_influence_choice,
        )
        from girlframe.services.m3_leviathan_obsession import ObsessionService

        await open_influence_choice(interaction, ObsessionService(game), identity)
        return
    if decision.get("gorgon_play"):
        from girlframe.discord_adapter.m3_gorgon_runtime import open_choice as open_gorgon_choice

        await open_gorgon_choice(interaction, game, identity)
        return
    if decision.get("am_code") is not None:
        from girlframe.discord_adapter.m3_am_code import open_choice as open_code_choice

        await open_code_choice(interaction, game, identity)
        return
    if decision.get("am_scrutinized") is not None:
        from girlframe.discord_adapter.m3_am import open_choice as open_am_choice

        await open_am_choice(interaction, game, identity)
        return
    if decision.get("alpha_sex") is not None:
        from girlframe.discord_adapter.m3_alpha_sex import (
            open_alpha_choice as open_alpha_sex_choice,
        )

        await open_alpha_sex_choice(interaction, game, identity)
        return
    if decision.get("alpha") is not None:
        from girlframe.discord_adapter.m3_alpha import open_alpha_choice

        await open_alpha_choice(interaction, game, identity)
        return
    if decision.get("janus") is not None:
        from girlframe.discord_adapter.m3_janus_play import open_battery_choice

        await open_battery_choice(interaction, game, identity)
        return
    if decision.get("snoop") is not None:
        from girlframe.discord_adapter.m3_enforcer_snoop import open_snoop

        await open_snoop(interaction, game, identity)
        return
    if decision.get("sprite_intercept"):
        from girlframe.discord_adapter.m3_sprite import open_sprite
        from girlframe.services.m3_sprite import SpriteService

        await open_sprite(interaction, SpriteService(game.store), decision["work_id"])
        return
    if decision.get("virus_purge"):
        from girlframe.discord_adapter.m3_compliance_virus import open_purge
        from girlframe.services.m3_compliance_virus import VirusService

        await open_purge(interaction, VirusService(game), decision["work_id"])
        return
    if decision.get("virus_order"):
        from girlframe.discord_adapter.m3_compliance_virus import open_order

        await open_order(interaction, game, decision)
        return
    if decision.get("virus_disobey") and decision["kind"].startswith("virus_disobey_"):
        from girlframe.discord_adapter.m3_compliance_virus import open_disobey_choice

        await open_disobey_choice(interaction, game, decision)
        return
    if decision.get("harpy_defeat"):
        from girlframe.discord_adapter.m3_harpy_defeat import open_choice as open_harpy_choice
        from girlframe.services.m3_harpy_defeat import HarpyDefeatService

        await open_harpy_choice(interaction, HarpyDefeatService(game.store, game), identity)
        return
    if decision["kind"] in ("battle_dormant_void", "battle_dormant_dive"):
        from girlframe.discord_adapter.m3_battle_dormant import open_dormant
        from girlframe.services.m3_battle_dormant import DormantService

        await open_dormant(
            interaction, DormantService(game.store, game), decision["body"]["work_id"]
        )
        return
    if decision["kind"] == "battle_dormant_threshold":
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), decision["body"]["work_id"])
        return
    if decision["kind"] in (
        "enforcer_firepower",
        "enforcer_firepower_context",
        "enforcer_firepower_confirm",
    ):
        from girlframe.discord_adapter.m3_enforcer_firepower import open_firepower

        await open_firepower(interaction, game, identity)
        return
    if decision["kind"] in ("harpy_off_duty_hide", "harpy_off_duty_route"):
        from girlframe.discord_adapter.m3_harpy_rest import open_rest

        await open_rest(interaction, game, identity)
        return
    if decision.get("mockingbird_play") is not None:
        from girlframe.discord_adapter.m3_mockingbird_plays import open_choice as open_mock_play

        await open_mock_play(interaction, game, identity)
        return
    if decision["kind"].startswith("mockingbird_") and decision.get("mockingbird") is not None:
        from girlframe.discord_adapter.m3_mockingbird import open_mockingbird

        await open_mockingbird(interaction, game, identity)
        return
    if decision["kind"] == "enforcer_master_dog":
        from girlframe.discord_adapter.m3_enforcer_requisitions import open_master

        await open_master(interaction, game, identity)
        return
    if decision["kind"] == "budget_asset_calamity":
        from girlframe.discord_adapter.m3_budget_sabotage import open_calamity

        await open_calamity(interaction, game, identity)
        return
    if decision["kind"].startswith("engage_") and decision.get("engage") is not None:
        from girlframe.discord_adapter.m3_engage import open_engage

        await open_engage(interaction, game, identity)
        return
    if decision["kind"].startswith("battle_") and decision.get("battle") is not None:
        from girlframe.discord_adapter.m3_battle import open_battle

        await open_battle(interaction, game, identity)
        return
    if decision["kind"] == "handler_brief" and decision["body"].get("handler_grant"):
        from girlframe.discord_adapter.m3_handler_plays import open_play as open_handler_play
        from girlframe.services.m3_handler_plays import HandlerPlayService

        await open_handler_play(
            interaction, HandlerPlayService(game.store), decision["body"]["handler_grant"]
        )
        return
    if decision["kind"].startswith("enforcer_") and decision.get("enforcement") is not None:
        from girlframe.discord_adapter.m3_enforcement_initiative import open_enforcer_choice

        await open_enforcer_choice(interaction, game, identity)
        return
    if decision.get("doctor") is not None:
        from girlframe.discord_adapter.m3_doctor import open_choice as open_doctor_choice
        from girlframe.services.m3_doctor import DoctorService

        await open_doctor_choice(interaction, DoctorService(game), identity)
        return
    if decision["kind"] in ("tag_marker_selection", "tag_marker_agreement"):
        from girlframe.discord_adapter.m3_tag_markers import open_discussion

        await open_discussion(interaction, game, identity)
        return
    if decision["kind"] == "manual_adjudication":
        from girlframe.discord_adapter.m3_adjudication import open_adjudication
        from girlframe.services.m3_adjudication import AdjudicationService

        await open_adjudication(interaction, AdjudicationService(game.store), identity)
        return
    if decision["kind"] in ("defeat_void_threshold", "dive_void_threshold", "void_keep_threshold"):
        from girlframe.discord_adapter.m3_void import open_void
        from girlframe.services.m3_void import VoidService

        await open_void(interaction, VoidService(game.store), decision["body"]["work_id"])
        return
    if decision["kind"].startswith("dive_") and decision.get("dive") is not None:
        from girlframe.discord_adapter.m3_dive import open_dive

        await open_dive(interaction, game, identity)
        return
    if decision["kind"] in ("beneath_defeat", "required_defeat"):
        from girlframe.discord_adapter.m3_defeat import open_start

        await open_start(interaction, game, decision)
        return
    if decision["kind"].startswith("defeat_") and decision.get("defeat") is not None:
        from girlframe.discord_adapter.m3_defeat import open_decision

        await open_decision(interaction, game, decision)
        return
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
        from girlframe.discord_adapter.m3_tag_markers import bind_answer

        submitted = answer_values(values)
        if submitted.options == ("gender_man",):
            submitted = submitted.model_copy(
                update={
                    "denied": tuple(x.removeprefix("gender-partner:") for x in submitted.denied)
                }
            )
        result = await threaded(
            lambda: game.respond(
                viewer_from_interaction(current),
                str(current.id),
                identity,
                decision["revision"],
                bind_answer(decision, submitted),
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
    if decision["kind"] == "tag_window" and decision.get("gender_man_tags"):
        instructions += (
            "\nThe partner-Tag option uses this roll's one Tag proposal "
            "and can raise its final Sex result to 11+."
        )
    if decision["kind"] == "tag_window" and decision.get("reign_enemy_tag_ids"):
        instructions += (
            "\nUnderfunded Tags belong to the opposed Rebel Girl. "
            "Use the ordinary one-Tag proposal; its controller owns repeated-mark resolution."
        )
    if decision["kind"] == "tag_window" and any(
        tag["id"].startswith("bomb-collar:") for tag in decision.get("tags", ())
    ):
        instructions += "\nA bomb collar can be marked as a Tag but cannot be embraced or rejected."
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
    if decision.get("actor_basic") and decision["kind"] in (
        "tag_window",
        "tag_resolution",
        "actor_tag_selection",
        "actor_tag_agreement",
    ):
        instructions += (
            "\nTag proposals and their relevance are shared with all scene participants. "
            "Pass without selecting a role or modifier."
        )
        if decision["kind"] == "tag_resolution":
            instructions += (
                " Embracing replaces this copy's sole Identity. "
                if decision.get("copy_identity_cap") == 1
                else " Embracing adds an Identity; choose a replacement only "
                "if you already have four. "
            )
            instructions += "Rejecting requires an actual later action."
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
    if decision["kind"] == "harpy_sensor_answers":
        instructions += "\nAnswer these questions honestly: " + clean(
            decision["result"]["questions"]
        )
    if decision["kind"] == "target_flirt":
        instructions += "\nQuestion: " + str(
            decision["result"].get("question_text")
            or decision["result"].get("question", "Why did you withdraw?")
        )
    if decision.get("cute_uniforms"):
        instructions += (
            "\nThe uniform also makes you seem helpless and adorable; "
            "this does not make you physically Helpless."
        )
    if decision["kind"] == "handler_keep" and decision["result"].get("forced_presentations"):
        instructions += "\nAdditional appearance: " + "; ".join(
            clean(x["presentation"]) for x in decision["result"]["forced_presentations"]
        )
    if decision.get("nightmare_core"):
        instructions += (
            "\nYou are always terrifying enough. "
            "Other traits and the Handler's overall ruling apply."
        )
    if decision.get("npc_order_issuer"):
        instructions += "\nActual NPC issuer: " + clean(decision["npc_order_issuer"])
    if decision.get("order_text"):
        instructions += "\nDirect order: " + clean(decision["order_text"])
    if decision.get("context") and decision["kind"] != "harpy_sensor_answers":
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
    interaction: discord.Interaction,
    game: GameService,
    *,
    parent: dict[str, Any] | None = None,
    _pilot: bool = False,
) -> None:
    if not _pilot and game.store.policy.m3_approval is not None:
        from girlframe.discord_adapter.m3_actor_plays import open_actor_play
        from girlframe.discord_adapter.m3_punishments import Picker
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.services.m3_actors import ActorService
        from girlframe.services.m3_missions import MissionService

        roles = await threaded(
            lambda: ActorService(MissionService(game.store)).choices(
                viewer_from_interaction(interaction)
            )
        )
        actual = [
            x
            for x in roles["actors"]
            if x["rules"] == "handler_girl"
            or x.get("girl") == "harpy"
            and x.get("heat") is not None
        ]
        if parent is not None:
            if parent["kind"] != "battle_counter_play":
                actual = []
            elif parent.get("actor"):
                actual = [x for x in actual if x["ref"] == parent["actor"]]
        pilots = [x for x in roles["actors"] if x["kind"] == "pilot"]
        if parent and parent["kind"] == "battle_counter_play" and parent.get("actor"):
            pilots = [x for x in pilots if x["ref"] == parent["actor"]]
        if actual and not pilots and len(actual) == 1:
            await open_actor_play(
                interaction, game, ActorRef.model_validate(actual[0]["ref"]), parent=parent
            )
            return
        if actual:
            by_token = {x["token"]: x for x in actual}
            options = tuple((x["token"], x["label"]) for x in actual)
            if pilots:
                options += (("pilot", "Your Girl and Frame"),)

            async def choose_role(current: discord.Interaction, selected: str) -> None:
                if selected == "pilot":
                    await open_play(current, game, parent=parent, _pilot=True)
                else:
                    await open_actor_play(
                        current,
                        game,
                        ActorRef.model_validate(by_token[selected]["ref"]),
                        parent=parent,
                    )

            await Picker(
                interaction.user.id, "**Which character is acting?**", options, choose_role
            ).show(interaction)
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
    plays: tuple[str, ...] = (
        ("disobey_orders",) if parent and parent["kind"] == "order_disobey" else PLAY_IDS
    )
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
    enforcement_targets: dict[str, Any] = {}
    plays = tuple(
        x
        for x in plays
        if x
        not in (
            "enforcement_initiative",
            "nanobot_injection",
            "all_out_assault",
            "go_for_the_core",
            "mockingbird_person",
            "mockingbird_sex",
            "snoop",
            "alpha_sex",
            "am_scrutinized",
            "am_just_code",
            "dose_up",
            "princess_sex",
            "stim_sex",
            "old_dog_new_pups",
            "oldgen_sex",
            "unassuming_doll",
        )
    )
    if parent and parent["kind"] == "am_code_prepare":
        plays = ("am_just_code",)
    if parent and parent["kind"] == "am_prepare":
        plays = ("am_scrutinized",)
    if (
        not parent
        and approval is not None
        and "plays" in approval.subsystems
        and "enforcement_initiative" in HEAT_IDS
    ):
        from girlframe.services.m3_enforcement_initiative import preview as enforcement_preview

        enforcement = await threaded(lambda: enforcement_preview(game, viewer, channel))
        if enforcement["available"]:
            plays = (*plays, "enforcement_initiative")
            enforcement_targets = {x["token"]: x for x in enforcement["targets"]}
    engage_targets: dict[str, Any] = {}
    if approval is not None and "plays" in approval.subsystems and "engage" in plays:
        from girlframe.services.m3_battle import BattleService

        battlefield = await threaded(lambda: BattleService(game.store).preview(viewer, channel))
        engage_targets = {x["token"]: x for x in battlefield["actors"] if not x["owned"]}
    snoop_targets: dict[str, Any] = {}
    if approval is not None and "plays" in approval.subsystems and "snoop" in HEAT_IDS:
        from girlframe.services.m3_enforcer_snoop import preview as snoop_preview

        snooping = await threaded(lambda: snoop_preview(game, viewer, channel))
        if snooping["available"]:
            plays = (*plays, "snoop")
            snoop_targets = {x["token"]: x for x in snooping["targets"]}
    alpha_targets = {}
    if approval is not None and "plays" in approval.subsystems:
        from girlframe.services.m3_alpha import preview as alpha_preview

        alpha = await threaded(lambda: alpha_preview(game, viewer, channel))
        if alpha["available"]:
            plays = (*plays, "brutalize")
            alpha_targets = {x["token"]: x for x in alpha["targets"]}
    alpha_sex_sources = {}
    if not parent and approval is not None and "plays" in approval.subsystems:
        from girlframe.services.m3_alpha_sex import preview as alpha_sex_preview

        accepted_sex = await threaded(lambda: alpha_sex_preview(game, viewer, channel))
        if accepted_sex["available"]:
            plays = (*plays, "alpha_sex")
            alpha_sex_sources = {x["id"]: x for x in accepted_sex["sessions"]}
    identities = [
        x for x in sheet["identities"] + sheet.get("additional_identities", []) if not x["marked"]
    ]
    from girlframe.discord_adapter.m3_dampener import fields as dampener_fields
    from girlframe.discord_adapter.m3_dampener import modifier as dampener_modifier
    from girlframe.services.m3_dampener import DampenerService

    dampener_controls = await dampener_fields(interaction, DampenerService(game))
    from girlframe.discord_adapter.m3_kicked_puppy import damaged_basis
    from girlframe.discord_adapter.m3_kicked_puppy import fields as kicked_fields
    from girlframe.services.m3_kicked_puppy import KickedPuppyService

    kicked_controls = await kicked_fields(interaction, KickedPuppyService(game))
    from girlframe.discord_adapter.m3_nightmare import keep_info as nightmare_info
    from girlframe.services.m3_nightmare import NightmareService

    nightmare = await nightmare_info(interaction, NightmareService(game))
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
        menu(
            "heat",
            "Heat for other Plays; Nightmare Keep uses 0" if nightmare else "Heat to spend",
            range(
                sheet["heat"]
                + (
                    8
                    if has_rule(sheet, "girl.stim-blissed.disposable-psyche", "STIM-BLISSED")
                    else 6
                )
            ),
        ),
        Field("piloting", "Are you piloting your Frame?", YES),
        Field("witnessed", "Foundation member witnesses refusal?", YES),
        text("context", "Describe the trigger and intended action"),
        Field(
            "trigger",
            "Confirm the printed trigger applies",
            (("yes", "I confirm the trigger applies"),),
        ),
    ]
    if has_rule(sheet, "girl.stim-blissed.disposable-psyche", "STIM-BLISSED"):
        fields.append(
            Field(
                "disposable_heat",
                "Optional Identity disposal: additional Heat",
                (
                    ("0", "Keep marked Identity"),
                    ("3", "Remove it: +3 Heat"),
                    ("4", "Remove it: +4 Heat"),
                ),
            )
        )
    fields.extend(dampener_controls)
    fields.extend(kicked_controls)

    if approval is not None and "plays" in approval.subsystems and "keep_your_head" in plays:
        from girlframe.services.m3_enforcer_requisitions import pavlov_available

        if await threaded(lambda: pavlov_available(game, viewer)):
            fields.extend(
                [
                    Field(
                        "obeying_orders",
                        "Keep only: invoke Pavlov while obeying orders?",
                        YES,
                        minimum=0,
                        required=False,
                    ),
                    text("order_account", "Keep only: describe your actual obedience", False),
                ]
            )

    if enforcement_targets:
        fields.insert(
            2,
            Field(
                "enforcer_target",
                "Actual Enforcement Initiative target",
                tuple((token, item["label"]) for token, item in enforcement_targets.items()),
                minimum=0,
                required=False,
            ),
        )

    if engage_targets:
        fields.insert(
            2,
            Field(
                "engage_target",
                "Actual opposing battlefield actor for Engage",
                tuple((token, item["name"]) for token, item in engage_targets.items()),
                minimum=0,
                required=False,
            ),
        )

    if snoop_targets:
        fields.insert(
            2,
            Field(
                "snoop_target",
                "Whose things are you actually going through?",
                tuple((token, item["label"]) for token, item in snoop_targets.items()),
                minimum=0,
                required=False,
            ),
        )

    if alpha_targets:
        fields.insert(
            2,
            Field(
                "alpha_target",
                "Actual Brutalize target",
                tuple((token, x["label"]) for token, x in alpha_targets.items()),
                minimum=0,
                required=False,
            ),
        )

    # Target IDs are stable authenticated IDs, not editable claims of ownership.
    if alpha_sex_sources:
        fields.insert(
            2,
            Field(
                "alpha_sex_source",
                "Accepted original Alpha interaction",
                tuple((identity, x["label"]) for identity, x in alpha_sex_sources.items()),
                minimum=0,
                required=False,
            ),
        )

    async def submit(current: discord.Interaction, values: dict[str, Any]) -> str:
        play = one(values, "play")
        identity = one(values, "identity")
        target_actor = None
        if play == "enforcement_initiative":
            from girlframe.engine.m3_actor_state import ActorRef

            selected = one(values, "enforcer_target")
            if selected is None or selected not in enforcement_targets:
                raise WorkflowError("Choose the actual original Enforcement Initiative target.")
            target_actor = ActorRef.model_validate(enforcement_targets[selected]["ref"])
        if play == "engage" and approval is not None and "plays" in approval.subsystems:
            from girlframe.engine.m3_actor_state import ActorRef

            selected = one(values, "engage_target")
            if selected is None or selected not in engage_targets:
                raise WorkflowError("Choose the actual opposing battlefield actor for Engage.")
            target_actor = ActorRef.model_validate(engage_targets[selected]["ref"])
        if play == "brutalize":
            from girlframe.engine.m3_actor_state import ActorRef

            selected = one(values, "alpha_target")
            if selected not in alpha_targets:
                raise WorkflowError("Choose an actual original Brutalize target")
            target_actor = ActorRef.model_validate(alpha_targets[selected]["ref"])
        if play == "snoop":
            from girlframe.engine.m3_actor_state import ActorRef

            selected = one(values, "snoop_target")
            if selected is None or selected not in snoop_targets:
                raise WorkflowError("Choose the actual known original Snoop target")
            target_actor = ActorRef.model_validate(snoop_targets[selected]["ref"])
        sex_source = None
        if play == "alpha_sex":
            selected = one(values, "alpha_sex_source")
            if selected not in alpha_sex_sources:
                raise WorkflowError("Confirm an actual voluntary source in /campaign alpha first")
            from girlframe.engine.m3_actor_state import ActorRef

            target_actor = ActorRef.model_validate(alpha_sex_sources[selected]["ref"])
            sex_source = selected
        code_source = None
        if play == "am_just_code":
            from girlframe.engine.m3_actor_state import ActorRef

            if not parent or parent["kind"] != "am_code_prepare":
                raise WorkflowError("Use your actual confirmed circuit-maintenance preparation")
            code_source = parent["body"]["maintenance"]
            target_actor = ActorRef.model_validate(parent["body"]["target"])
        am_source = None
        if play == "am_scrutinized":
            from girlframe.engine.m3_actor_state import ActorRef

            if not parent or parent["kind"] != "am_prepare":
                raise WorkflowError("Use your actual confirmed AM discovery preparation")
            am_source = parent["body"]["discovery"]
            target_actor = ActorRef.model_validate(parent["body"]["target"])
        prepared = PlayInput(
            play=play,
            context=values["context"],
            trigger_confirmed=True,
            target_actor=target_actor,
            obeying_orders=play == "keep_your_head" and one(values, "obeying_orders") == "yes",
            order_account=values.get("order_account", "") if play == "keep_your_head" else "",
            heat=0 if play == "keep_your_head" and nightmare else int(one(values, "heat")),
            dampener_modifier=dampener_modifier(values),
            kicked_puppy_basis=damaged_basis(values),
            identity=identity,
            gain=int(one(values, "gain")),
            pair_share=int(one(values, "pair_share")),
            disposable_heat=cast(Literal[0, 3, 4], int(one(values, "disposable_heat") or "0")),
            target=int(one(values, "target"))
            if play in ("flirt", "put_someone_beneath_you") and one(values, "target")
            else None,
            piloting=one(values, "piloting") == "yes",
            witnessed=one(values, "witnessed") == "yes",
            parent=parent["parent"] if parent else None,
            order_id=parent["body"].get("order_id") if parent else None,
            source_work=code_source or am_source or sex_source,
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
            " Nightmare Core: Keep Your Head uses Void Assets and spends no Heat."
            if nightmare
            else ""
        )
        + (
            " "
            + scene["memory"]["label"]
            + ". Saved present scene: "
            + scene["memory"]["present_scene"]
            + ". "
            + scene["memory"]["instruction"]
            if scene.get("memory")
            else ""
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
        approval = game.store.policy.m3_approval
        if not approval or "plays" not in approval.subsystems:
            self.remove_item(self.handler_tag)
            self.remove_item(self.mockingbird)
            self.remove_item(self.doctor)
        if not approval or not {"plays", "world"} <= set(approval.subsystems):
            self.remove_item(self.gorgon)
        if not (
            approval
            and "plays" in approval.subsystems
            and "all_out_assault" in HEAT_IDS
            and "go_for_the_core" in HEAT_IDS
        ):
            self.remove_item(self.battle)

    @discord.ui.button(label="Gorgon Plays", custom_id="m3:scene:gorgon", row=1)
    async def gorgon(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_gorgon_play import open_gorgon_play

            await open_gorgon_play(interaction, self.game)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="DoctorDoctor", custom_id="m3:scene:doctor", row=1)
    async def doctor(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_doctor import open_doctor
            from girlframe.services.m3_doctor import DoctorService

            await open_doctor(interaction, DoctorService(self.game))
        except (WorkflowError, ValueError) as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Mockingbird Plays", custom_id="m3:scene:mockingbird", row=1)
    async def mockingbird(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_mockingbird_plays import open_book
            from girlframe.engine.m3_actor_state import ActorRef

            viewer = viewer_from_interaction(interaction)
            sheet = await threaded(lambda: self.game.sheet(viewer))
            if sheet["character_id"] is None:
                raise WorkflowError("Bind the original canonical character before using its book")
            await open_book(
                interaction,
                self.game,
                actor_ref=ActorRef(
                    kind="pilot", entity=str(viewer.user_id), incarnation=sheet["character_id"]
                ),
            )
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Use a Handler Tag", custom_id="m3:scene:handler_tag", row=1)
    async def handler_tag(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_handler_tags import open_handler_tags

            await open_handler_tags(interaction, self.game)
        except WorkflowError as error:
            await reply(interaction, str(error))

    @discord.ui.button(label="Declare combat", custom_id="m3:scene:battle", row=0)
    async def battle(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_battle import open_declaration
            from girlframe.services.m3_battle import BattleService

            await open_declaration(interaction, BattleService(self.game.store))
        except WorkflowError as error:
            await reply(interaction, str(error))

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
                context = scene.get("memory")
                await reply(
                    interaction,
                    "No saved lock in this scene."
                    + (" " + context["label"] + ". " + context["instruction"] if context else ""),
                )
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
            "Clone Identity: " + entity_label(x) + (" [marked]" if x["marked"] else "")
            for x in sheet.get("additional_identities", [])
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
        if await threaded(lambda: self.game.helpless_status(viewer_from_interaction(interaction))):
            lines.append("Helpless: recover through /character recover after a moment alone.")
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

    @app_commands.command(
        name="battle", description="Declare actual combatants, Assets and opening before rolling"
    )
    @app_commands.guild_only()
    async def battle(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_battle import open_declaration
            from girlframe.services.m3_battle import BattleService

            await open_declaration(interaction, BattleService(game.store))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @app_commands.command(
        name="frame_core", description="Review an actual present Frame Core exposure"
    )
    @app_commands.guild_only()
    async def frame_core(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from girlframe.discord_adapter.m3_frame_core import open_core
            from girlframe.services.m3_battle import BattleService
            from girlframe.services.m3_frame_core import FrameCoreService

            await open_core(interaction, FrameCoreService(BattleService(game.store)))
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

    @campaign.command(name="am", description="Owned AM discovery, Limiter and secret controls")
    async def am_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_am import open_am
        from girlframe.services.m3_am_scrutinized import ScrutinyService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_am(interaction, ScrutinyService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="alpha", description="Owned Alpha source interactions and scent tracking"
    )
    async def alpha_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_alpha_sex import open_alpha
        from girlframe.services.m3_alpha_sex import SexService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_alpha(interaction, SexService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="princess", description="Voluntary Princess source and private saved choices"
    )
    async def princess_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_princess_sex import open_princess
        from girlframe.services.m3_princess_sex import SexService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_princess(interaction, SexService(game))
        except WorkflowError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @campaign.command(
        name="mentor", description="Original Mentor callsign and owned cosmetic controls"
    )
    async def mentor_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_mentor import open_mentor
        from girlframe.services.m3_mentor import MentorService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_mentor(interaction, MentorService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="trainee", description="Actual teaching and source-owned Mentor duty")
    async def trainee_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_trainee import open_trainee
        from girlframe.services.m3_trainee import TraineeService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_trainee(interaction, TraineeService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="vatgrown", description="Actual Unassuming Doll source and saved effects"
    )
    async def vatgrown_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_vatgrown import open_vatgrown
        from girlframe.services.m3_vatgrown import DollService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_vatgrown(interaction, DollService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="oldgen_sex", description="Voluntary Oldgen source and private saved choices"
    )
    async def oldgen_sex_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_oldgen_sex import open_oldgen_sex
        from girlframe.services.m3_oldgen_sex import OldgenSexService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_oldgen_sex(interaction, OldgenSexService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="oldgen", description="Owned maxims and actual Old Dog advice")
    async def oldgen_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_oldgen import open_oldgen
        from girlframe.services.m3_oldgen import OldgenService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_oldgen(interaction, OldgenService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="malleable", description="Qualified Tags and NPC altered-state controls")
    async def malleable_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_malleable import open_malleable
        from girlframe.services.m3_malleable import MalleableService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_malleable(interaction, MalleableService(game.store, game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="stim", description="Voluntary Stim source, drugs and saved effects")
    async def stim_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_stim_sex import open_stim
        from girlframe.services.m3_stim_sex import SexService as StimSexService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_stim(interaction, StimSexService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(name="ankou", description="Owned Feedback choices and saved source history")
    async def ankou_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_ankou_feedback import open_feedback
        from girlframe.services.m3_ankou_feedback import FeedbackService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_feedback(interaction, FeedbackService(game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="psyche", description="Owned Disposable Psyche choices and private history"
    )
    async def psyche_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_disposable_psyche import open_psyche
        from girlframe.services.m3_disposable_psyche import PsycheService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_psyche(interaction, PsycheService(game.store, game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="dose", description="Owned Dose Up cocktail choices and saved drug history"
    )
    async def dose_controls(interaction: discord.Interaction) -> None:
        from girlframe.discord_adapter.m3_dose_up import open_dose_up
        from girlframe.services.m3_dose_up import DoseUpService

        await interaction.response.defer(ephemeral=True)
        try:
            await open_dose_up(interaction, DoseUpService(game.store, game))
        except WorkflowError as error:
            await reply(interaction, str(error))

    @campaign.command(
        name="order", description="Record a source-authorized direct order in this scene"
    )
    @app_commands.choices(
        purpose=[
            app_commands.Choice(name="Ordinary order", value="ordinary"),
            app_commands.Choice(name="Dose Up (typed cocktail order)", value="dose_up"),
        ]
    )
    async def order(
        interaction: discord.Interaction,
        member: discord.Member,
        instruction: str,
        as_npc: bool = False,
        purpose: app_commands.Choice[str] | None = None,
    ) -> None:
        typed_dose = purpose is not None and purpose.value == "dose_up"
        if as_npc and typed_dose:
            await reply(
                interaction,
                "UNSUPPORTED_RULE: typed Dose Up Orders currently use original native issuers.",
            )
            return
        if as_npc:
            from girlframe.discord_adapter.m3_npc_orders import open_order
            from girlframe.services.m3_npc_orders import NpcOrderService

            await interaction.response.defer(ephemeral=True)
            try:
                await open_order(interaction, NpcOrderService(game), member.id, instruction)
            except WorkflowError as error:
                await reply(interaction, str(error))
            return
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
                    dose_up=typed_dose,
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
            if not await threaded(
                lambda: game.helpless_status(viewer_from_interaction(interaction))
            ):
                raise WorkflowError("No current Helpless condition needs recovery.")
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

    approval = game.store.policy.m3_approval
    if (
        approval
        and "plays" in approval.subsystems
        and "all_out_assault" in HEAT_IDS
        and "go_for_the_core" in HEAT_IDS
    ):
        tree.add_command(battle, guild=guild)
        tree.add_command(frame_core, guild=guild)
    tree.add_command(play, guild=guild)
    tree.add_command(choice, guild=guild)
