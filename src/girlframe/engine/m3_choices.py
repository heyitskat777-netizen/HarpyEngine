"""Exact shared-Play decision contracts; mechanical application remains a separate reducer."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import Model, tier

Role = Literal["actor", "target", "handler", "table"]
BasicPlay = Literal[
    "put_someone_beneath_you",
    "all_out_assault",
    "go_for_the_core",
    "dive_deep",
    "go_off_duty",
    "void_observation",
    "defeat",
]


class Group(Model):
    id: str
    owner: Role
    options: tuple[str, ...]
    minimum: int = Field(ge=0)
    maximum: int = Field(ge=1)

    @model_validator(mode="after")
    def bounds(self) -> "Group":
        if (
            self.minimum > self.maximum
            or self.maximum > len(self.options)
            or len(set(self.options)) != len(self.options)
        ):
            raise ValueError("Invalid decision contract bounds")
        return self

    def select(self, actor: Role, values: tuple[str, ...]) -> None:
        if actor != self.owner:
            raise ValueError("This choice belongs to another participant")
        if (
            not self.minimum <= len(values) <= self.maximum
            or len(set(values)) != len(values)
            or not set(values) <= set(self.options)
        ):
            raise ValueError("Choose the exact permitted distinct options")


class Context(Model):
    total: int
    target_is_npc: bool = False
    target_is_gorgon_or_piloting: bool = False
    target_core_exposed: bool = False
    can_punish_target: bool = False
    target_can_punish_actor: bool = False
    hide_void_suspected: bool = False


class Plan(Model):
    play: BasicPlay
    level: Literal["low", "mid", "high"]
    source_pdf: int
    groups: tuple[Group, ...]
    pre_roll_requirements: tuple[str, ...] = ()
    fixed_followups: tuple[str, ...] = ()
    after_choices: tuple[str, ...] = ()
    # This object is not a completed mechanical action or permission to post an outcome.
    mechanical_application_required: Literal[True] = True


def group(
    identity: str, owner: Role, options: tuple[str, ...], minimum: int, maximum: int | None = None
) -> Group:
    return Group(
        id=identity,
        owner=owner,
        options=options,
        minimum=minimum,
        maximum=minimum if maximum is None else maximum,
    )


PUT_BASIC = ("inflict_tag", "lower_status", "weaken_bond")
PUT_HIGH = ("require_tag_rejection_consent", "pin_and_request_response")
DIVE = (
    "void_and_unmark_all",
    "erase_identity_and_table_question",
    "nearby_npcs_gain_void",
    "table_replaces_identity",
    "locked_cockpit_extraction_requires_frame_consent",
)
OFF_DUTY = {
    "mid": ("barracks", "mess_hall", "hangar", "training", "other_routine"),
    "high": ("handler_office", "nearby_city", "prisoner", "briefing_or_emergency", "other_unusual"),
    "low": ("handler_office", "cell", "vital_frame", "medical_bay", "other_unwanted"),
}
OBSERVATION = (
    "remove_girl_void_asset",
    "remove_frame_void_asset",
    "assigned_observer",
    "medical_probing",
    "hospital_stay",
    "public_display_tag",
)
HIDDEN_VOID = (
    "moderate_punishment",
    "reprogram",
    "become_dog",
    "harpy_candidate_tag",
    "director_or_rival_arrives",
)
DEFEAT_MID = (
    "new_girl_and_frame_void_assets_heat4",
    "escape_cockpit_choose_location",
    "pilot_rescue_deepen_bond",
    "handler_rescue_swap_girl_play_on_waking",
)
DEFEAT_HIGH = ("lower_status", "another_girl_gives_tag", "post_mission_punishment")
DEFEAT_LOW = (
    "death",
    "lose_frame_choose_later",
    "change_girl_playbook",
    "amnesia_reset_and_replace",
    "handler_ruinous_alternative",
)
CORE_RETALIATION = (
    "damage_actor_asset",
    "make_play_against_actor",
    "actor_helpless",
    "target_dies_with_handler_play",
)


def plan(play: BasicPlay, context: Context) -> Plan:
    level = tier(context.total)
    groups: list[Group] = []
    fixed: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    if play == "put_someone_beneath_you":
        high = PUT_HIGH + (("punish",) if context.can_punish_target else ())
        if level == "mid":
            groups = [group("basic", "actor", PUT_BASIC, 2)]
        elif level == "high":
            groups = [group("basic", "actor", PUT_BASIC, 1), group("extra", "actor", high, 1)]
        else:
            groups = [
                group(
                    "reversal",
                    "target",
                    PUT_BASIC
                    + PUT_HIGH
                    + (("punish",) if context.target_can_punish_actor else ())
                    + ("damage_actor_asset",),
                    1,
                )
            ]
        source = 22
    elif play == "all_out_assault":
        source = 25
        if level == "low":
            fixed = ("enemy_damages_actor_asset", "handler_play")
        else:
            fixed = (
                "declare_owned_asset_and_target_asset",
                "table_vast_advantage_ruling",
                "damage_target_asset_unless_vast_advantage",
            )
            if level == "high":
                groups = [
                    group(
                        "handler_consequences",
                        "handler",
                        ("collateral_damage", "handler_play", "damage_actor_asset"),
                        1,
                        2,
                    )
                ]
    elif play == "go_for_the_core":
        source = 26
        before = (
            "declare_owned_asset_for_decisive_strike",
            "subtract_target_undamaged_assets",
            "verify_required_core_exposure",
        )
        if context.target_is_gorgon_or_piloting and not context.target_core_exposed:
            raise ValueError("Core must be exposed before this Play can begin")
        if level == "mid":
            fixed = ("target_messy_death_now_or_shortly",)
        elif level == "high" and context.target_is_npc:
            fixed = ("target_explodes", "every_other_character_damages_asset_or_dies")
        else:
            groups = [
                group("retaliation", "target", CORE_RETALIATION, 1, 2 if level == "low" else 1)
            ]
            if level == "low" and context.target_is_npc:
                fixed = ("npc_dies_unless_valid_fictional_defense",)
    elif play == "dive_deep":
        source = 24
        if level == "mid":
            groups = [group("dive", "actor", DIVE, 1)]
        elif level == "high":
            groups = [group("dive", "actor", DIVE, 1), group("handler_dive", "handler", DIVE, 1)]
            after = ("handler_detects_spike_lower_actor_status",)
        else:
            groups = [group("handler_dive", "handler", DIVE, 1)]
            after = ("human_describes_painful_connection",)
    elif play == "go_off_duty":
        source = 27
        before = ("use_status_modifier_instead_of_heat",)
        groups = [group("scene", "actor", OFF_DUTY[level], 0 if level == "mid" else 1, 1)]
        after = (
            "if_scene_selected_require_other_girls"
            if level == "mid"
            else "scene_requires_handler_or_other_girls",
            "optional_embrace_tag",
            "unmark_one_identity",
            "repair_all_assets_unless_restricted",
            "resolve_offscreen_requisitions_and_punishments",
        )
        if level == "low":
            fixed = ("punishments_must_happen_on_screen",)
    elif play == "void_observation":
        source = 28
        before = ("lower_actor_status", "use_void_asset_count_instead_of_heat")
        options = OBSERVATION + (HIDDEN_VOID if context.hide_void_suspected else ())
        groups = [group("observation", "actor", options, 1)]
        if level != "low":
            groups.append(
                group("handler_observation", "handler", options, 1 if level == "mid" else 2)
            )
        after = ("choose_observation_or_harsh_off_duty_scene", "normal_off_duty_recovery")
    elif play == "defeat":
        source = 29
        before = ("use_undamaged_girl_asset_count_instead_of_heat",)
        groups = [
            group(
                "defeat",
                "actor",
                DEFEAT_LOW if level == "low" else DEFEAT_MID if level == "mid" else DEFEAT_HIGH,
                1 if level != "high" else 2,
                2 if level in ("low", "high") else 1,
            )
        ]
        if level == "high":
            fixed = ("handler_or_agents_rescue",)
    else:
        raise ValueError("UNSUPPORTED_RULE: no audited shared-Play decision contract")
    return Plan(
        play=play,
        level=level,
        source_pdf=source,
        groups=tuple(groups),
        pre_roll_requirements=before,
        fixed_followups=fixed,
        after_choices=after,
    )


def off_duty_modifier(status: Literal["Ace", "Wings", "Dog"]) -> int:
    return {"Ace": 4, "Wings": 2, "Dog": 0}[status]
