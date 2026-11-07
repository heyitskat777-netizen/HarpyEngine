"""Canonical pilot state and typed human inputs for the audited M2 subset."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.creation_review import ReviewSheet
from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_acquisition_state import PersonalFirearmGrant
from girlframe.engine.m3_actor_bond_state import BondEdge, HelplessCondition
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_alpha_state import Broken
from girlframe.engine.m3_career_state import (
    CareerArchive,
    CareerReturn,
    IncarnationBinding,
    UnlinkedCareer,
)
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_enforcer_state import Accusation, Grasp, RankFact
from girlframe.engine.m3_frame_control_state import FrameCommand, NeuralConnection
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_girl_runtime_state import GirlRuntime
from girlframe.engine.m3_handler_consequence_state import (
    HandlerArchive,
    HandlerConsequence,
    HandlerDeparture,
    HandlerFatalSource,
    HandlerInjury,
    HandlerOpportunity,
)
from girlframe.engine.m3_handler_girl_void_state import HandlerGirlVoid
from girlframe.engine.m3_handler_play_state import HandlerPlay
from girlframe.engine.m3_handler_state import HandlerPersona
from girlframe.engine.m3_handler_void_state import HandlerVoid
from girlframe.engine.m3_harpy_defeat_state import (
    Declaration as HarpyDefeatDeclaration,
)
from girlframe.engine.m3_harpy_defeat_state import (
    DefeatEffect,
    HarpySetup,
    NativeHarpyRuntime,
    Rift,
    Travel,
)
from girlframe.engine.m3_harpy_rest_state import Rest as HarpyRest
from girlframe.engine.m3_item_state import HeldItem, ItemTransfer
from girlframe.engine.m3_janus_link_state import BatteryAsset, BatteryLink
from girlframe.engine.m3_janus_state import JanusCore
from girlframe.engine.m3_leviathan_arrival_state import ExternalPose, LeviathanArrival
from girlframe.engine.m3_leviathan_obsession_state import IdentityAuthority, Obsession
from girlframe.engine.m3_lobotomy_state import BlockedPlay, Surgery
from girlframe.engine.m3_mockingbird_state import MockingbirdState
from girlframe.engine.m3_passenger_state import Passenger
from girlframe.engine.m3_physical_state import EscortJourney, FrameLock, ParkedFrame, Placement
from girlframe.engine.m3_refusal_state import RefusalBonus
from girlframe.engine.m3_regulation_state import Regulation
from girlframe.engine.m3_repair_state import Quote as RepairQuote
from girlframe.engine.m3_repair_state import Shortage as RepairShortage
from girlframe.engine.m3_requisition_state import Requisition
from girlframe.engine.m3_role_punishment_state import RolePunishment
from girlframe.engine.m3_strain_state import State as StrainState
from girlframe.engine.m3_supply_state import SupplyLoss
from girlframe.engine.m3_void_state import HarpyState, VoidThreshold
from girlframe.engine.m3_world_state import World

RULESET: Literal["girlframe-m2-pilot-1"] = "girlframe-m2-pilot-1"
PLAY_IDS = ("keep_your_head", "check_sensors", "engage", "disobey_orders", "flirt")
TRAITS = ("desperate", "sexy", "tough", "vicious", "in_control")
MANEUVERS = ("pin", "advance", "drive_back", "reposition", "cover", "shatter", "protect", "lure")
QUESTIONS = (
    "foundation_destination",
    "foundation_avoid",
    "enemy_activity",
    "repair_rest",
    "civilian_danger",
    "orders",
)
FLIRT_QUESTIONS = ("hurt", "be", "hide", "fears", "name", "intimacy")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class ReleaseApproval(Model):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    ruleset: Literal["girlframe-m2-pilot-1"] = RULESET
    registry_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1, max_length=120)
    reference: str = Field(min_length=1, max_length=240)


class IdentityState(Model):
    id: str
    name: str
    marked: bool = False
    protected: bool = False
    paired: bool = False
    slot: int | None = Field(default=None, ge=0, le=3)
    obsession_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    am_limiter: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )


class AssetState(Model):
    id: str
    family: Literal["girl", "frame"]
    name: str
    description: str = ""
    damaged: bool = False
    void: bool = False
    intrinsic: Literal["wyvern_enormous"] | None = None
    classification_event: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    concealed: bool = False
    battery_asset: BatteryAsset | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def actual_intrinsic_family(self) -> "AssetState":
        if self.intrinsic is not None and self.family != "frame" and not self.classification_event:
            raise ValueError("The printed WYVERN intrinsic belongs to its Frame Asset")
        if self.battery_asset is not None and (
            self.family != "girl"
            or self.id != self.battery_asset.asset_id
            or self.name != self.battery_asset.name
            or self.intrinsic is not None
        ):
            raise ValueError("Use the exact printed source-linked temporary mental Girl Asset")
        return self


class TagState(Model):
    id: str
    label: str = Field(min_length=1, max_length=120)
    giver: Snowflake
    observers: tuple[Snowflake, ...] = ()
    marked: bool = False
    scene_used: str | None = None
    rejection_pending: bool = False
    giver_character: str | None = None
    giver_actor: ActorRef | None = None
    gm_setter_appointment: str | None = Field(default=None, min_length=1)
    gm_setter_event: str | None = Field(default=None, min_length=1)
    gm_setter_grant: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def separate_setter_roles(self) -> "TagState":
        if self.gm_setter_appointment is not None and (
            self.giver_actor is not None or self.giver_character is not None
        ):
            raise ValueError("An OOC GM setter has no fictional actor or character authority")
        if (
            self.gm_setter_event is not None or self.gm_setter_grant is not None
        ) and self.gm_setter_appointment is None:
            raise ValueError("The OOC setter event requires its actual appointment source")
        return self


class PilotSheet(Model):
    owner: Snowflake
    character_id: str | None = Field(default=None, min_length=1, max_length=100)
    revision: int = 1
    callsign: str
    girl: str
    frame: str
    source_fingerprint: str
    source_profile_revision: int
    review: ReviewSheet
    identities: list[IdentityState]
    obsession_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    assets: list[AssetState]
    tags: list[TagState] = Field(default_factory=list)
    heat: int = Field(default=0, ge=0)
    permissions: int = Field(default=0, ge=0)
    mentor: Snowflake | None = None
    pair: Snowflake | None = None
    helpless_against: tuple[Snowflake, ...] = ()
    status_marked: bool = False
    maxims_marked: tuple[int, ...] = ()
    public_fields: tuple[str, ...] = ()
    sedation_locked: tuple[str, ...] = ()
    sedation_period: str | None = None
    libido_inhibited: bool = False
    obsolescence_marked: int = Field(default=0, ge=0, le=8)
    frame_scrapped: bool = False
    frame_runtime: FrameRuntime | None = None
    medical_state: Literal["fit", "unconscious_injured"] = "fit"
    girl_runtime: GirlRuntime | None = None
    blocked_plays: list[BlockedPlay] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> "PilotSheet":
        for collection in (self.identities, self.assets, self.tags):
            ids = [x.id for x in collection]
            if len(ids) != len(set(ids)):
                raise ValueError("Canonical entity IDs must be distinct")
        if len([x for x in self.identities if not x.protected or x.paired or x.am_limiter]) > 4:
            raise ValueError("A Girl has at most four ordinary/Paired Identities")
        slots = [x.slot for x in self.identities if x.slot is not None]
        if len(set(slots)) != len(slots) or any(
            x.slot is not None and x.protected and not x.paired and x.am_limiter is None
            for x in self.identities
        ):
            raise ValueError(
                "Ordinary/Paired Identity slots are distinct; protected extras are separate"
            )
        if any(
            x.am_limiter and (not x.protected or x.paired or x.slot is None)
            for x in self.identities
        ):
            raise ValueError("An actual Limiter protects its one ordinary Identity slot")
        return self


class DirectorContext(Model):
    id: str
    handler: Snowflake
    directors: tuple[str, ...]
    source_works: tuple[str, ...]
    identities: list[IdentityState]
    obsession_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    source_event: str
    body_actor: ActorRef | None = None
    active: bool = True
    revision: int = 1
    termination_reason: Literal["handler_death", "director_death", "handler_departure"] | None = (
        None
    )
    termination_event: str | None = None

    @model_validator(mode="after")
    def choices(self) -> "DirectorContext":
        if (
            len(self.identities) > 4
            or any(x.protected or x.paired for x in self.identities)
            or len({x.id for x in self.identities}) != len(self.identities)
        ):
            raise ValueError(
                "A Director context retains distinct ordinary Identity cards up to the Girl cap"
            )
        if (
            not self.source_works
            or len(set(self.source_works)) != len(self.source_works)
            or len(set(self.directors)) != len(self.directors)
            or (self.termination_reason is None and self.active != bool(self.directors))
            or (self.termination_reason is not None and (self.active or not self.termination_event))
            or (self.termination_reason is None and self.termination_event is not None)
        ):
            raise ValueError("The actual Director presence and its source work remain explicit")
        return self


class Obligation(Model):
    id: str
    kind: str
    owner: Snowflake
    target: Snowflake | None = None
    action: str
    details: dict[str, str] = Field(default_factory=dict)
    state: Literal["pending", "fulfilled"] = "pending"


class GameState(Model):
    schema_version: Literal[1] = 1
    revision: int = 0
    sheets: dict[str, PilotSheet] = Field(default_factory=dict)
    order: tuple[Snowflake, ...] = ()
    handler: Snowflake | None = None
    handler_heat: int = Field(default=0, ge=0)
    handler_tags: list[TagState] = Field(default_factory=list)
    handler_persona: HandlerPersona | None = None
    handler_archives: list[HandlerArchive] = Field(default_factory=list)
    handler_departures: list[HandlerDeparture] = Field(default_factory=list)
    mockingbird: MockingbirdState = Field(default_factory=MockingbirdState)
    passengers: list[Passenger] = Field(default_factory=list)
    handler_consequences: list[HandlerConsequence] = Field(default_factory=list)
    handler_injuries: list[HandlerInjury] = Field(default_factory=list)
    handler_opportunities: list[HandlerOpportunity] = Field(default_factory=list)
    handler_fatal_sources: list[HandlerFatalSource] = Field(default_factory=list)
    role_punishments: list[RolePunishment] = Field(default_factory=list)
    handler_plays: list[HandlerPlay] = Field(default_factory=list)
    held_items: list[HeldItem] = Field(default_factory=list)
    item_transfers: list[ItemTransfer] = Field(default_factory=list)
    bonds: dict[str, int] = Field(default_factory=dict)
    actor_bonds: list[BondEdge] = Field(default_factory=list)
    alpha_broken: list[Broken] = Field(default_factory=list, exclude_if=lambda value: not value)
    helpless_conditions: list[HelplessCondition] = Field(default_factory=list)
    leviathan_obsessions: list[Obsession] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    leviathan_identity_authorities: list[IdentityAuthority] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    external_poses: list[ExternalPose] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    leviathan_arrivals: list[LeviathanArrival] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    obligations: list[Obligation] = Field(default_factory=list)
    facts: list[dict[str, str]] = Field(default_factory=list)
    intense_tag_bonus: int | None = None
    strain: StrainState | None = None
    world: World | None = None
    director_contexts: list[DirectorContext] = Field(default_factory=list)
    scene_casts: list[SceneCast] = Field(default_factory=list)
    regulations: list[Regulation] = Field(default_factory=list)
    repair_shortages: list[RepairShortage] = Field(default_factory=list)
    repair_quotes: list[RepairQuote] = Field(default_factory=list)
    supply_losses: list[SupplyLoss] = Field(default_factory=list)
    requisitions: list[Requisition] = Field(default_factory=list)
    placements: list[Placement] = Field(default_factory=list)
    frame_locks: list[FrameLock] = Field(default_factory=list)
    parked_frames: list[ParkedFrame] = Field(default_factory=list)
    escort_journeys: list[EscortJourney] = Field(default_factory=list)
    personal_firearms: list[PersonalFirearmGrant] = Field(default_factory=list)
    refusal_bonuses: list[RefusalBonus] = Field(default_factory=list)
    contraband_finds: list[ContrabandFind] = Field(default_factory=list)
    career_archives: list[CareerArchive] = Field(default_factory=list)
    career_returns: list[CareerReturn] = Field(default_factory=list)
    incarnation_bindings: list[IncarnationBinding] = Field(default_factory=list)
    unlinked_careers: list[UnlinkedCareer] = Field(default_factory=list)
    harpy_states: list[HarpyState] = Field(default_factory=list)
    native_harpies: list[NativeHarpyRuntime] = Field(default_factory=list)
    janus_cores: list[JanusCore] = Field(default_factory=list, exclude_if=lambda value: not value)
    battery_links: list[BatteryLink] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    neural_connections: list[NeuralConnection] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    frame_commands: list[FrameCommand] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    harpy_setups: list[HarpySetup] = Field(default_factory=list)
    handler_girl_void: list[HandlerGirlVoid] = Field(default_factory=list)
    handler_void: list[HandlerVoid] = Field(default_factory=list)
    harpy_rests: list[HarpyRest] = Field(default_factory=list)
    harpy_defeats: list[DefeatEffect] = Field(default_factory=list)
    harpy_defeat_declarations: list[HarpyDefeatDeclaration] = Field(default_factory=list)
    void_rifts: list[Rift] = Field(default_factory=list)
    harpy_travels: list[Travel] = Field(default_factory=list)
    void_thresholds: list[VoidThreshold] = Field(default_factory=list)
    lobotomies: list[Surgery] = Field(default_factory=list)
    enforcer_ranks: list[RankFact] = Field(default_factory=list)
    enforcer_accusations: list[Accusation] = Field(default_factory=list)
    enforcer_grasps: list[Grasp] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_original_placements(self) -> "GameState":
        if any(x.get("kind") == "am_limiter" for x in self.facts) or any(
            x.am_limiter for sheet in self.sheets.values() for x in sheet.identities
        ):
            from girlframe.engine.m3_am import validate_slots

            validate_slots(self)
        edges = [frozenset((x.first, x.second)) for x in self.actor_bonds]
        if len(edges) != len(set(edges)):
            raise ValueError("One actual Bond has one canonical relationship authority")
        conditions = [(x.subject, x.foe) for x in self.helpless_conditions if x.active]
        if len(conditions) != len(set(conditions)):
            raise ValueError("One actual opponent has one active Helpless condition")
        if len({x.id for x in self.career_archives}) != len(self.career_archives):
            raise ValueError("Career archive IDs preserve distinct source endings")
        if len({x.id for x in self.contraband_finds}) != len(self.contraband_finds):
            raise ValueError("Actual contraband source finds must be distinct")
        if len({x.id for x in self.refusal_bonuses}) != len(self.refusal_bonuses):
            raise ValueError("Actual refusal bonus sources must be distinct")
        if len({x.actor for x in self.placements}) != len(self.placements) or len(
            {x.vessel_id for x in self.placements}
        ) != len(self.placements):
            raise ValueError("Original physical placements have distinct actors and vessels")
        return self


class PlayInput(Model):
    play: str
    context: str = Field(min_length=1, max_length=1200)
    trigger_confirmed: Literal[True]
    heat: int = Field(ge=0)
    dampener_modifier: Literal[2, 3] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    kicked_puppy_basis: bool = Field(default=False, exclude_if=lambda value: value is False)
    identity: str | None = None
    gain: int = Field(default=0, ge=0, le=5)
    pair_share: int = Field(default=0, ge=0, le=5)
    target: Snowflake | None = None
    target_actor: ActorRef | None = None
    attacking_asset: str | None = Field(default=None, min_length=1, max_length=200)
    target_asset: str | None = Field(default=None, min_length=1, max_length=200)
    battle_context: str | None = Field(default=None, min_length=1, max_length=100)
    piloting: bool = False
    order_id: str | None = None
    witnessed: bool = False
    obeying_orders: bool = Field(default=False, exclude_if=lambda value: value is False)
    order_account: str = Field(default="", max_length=1200, exclude_if=lambda value: value == "")
    parent: str | None = None
    off_duty_id: str | None = None
    source_work: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def battle_fields_only(self) -> "PlayInput":
        if self.kicked_puppy_basis and (self.play != "flirt" or self.heat != 0):
            raise ValueError("Kicked Puppy's alternative is only actual Flirt with zero Heat spent")
        if self.dampener_modifier is not None and self.heat < 5:
            raise ValueError("Dampener Link still requires at least five actual Heat spent")
        if self.play != "keep_your_head" and (self.obeying_orders or self.order_account):
            raise ValueError("Only actual Keep accepts current-order obedience details")
        if self.obeying_orders != bool(self.order_account.strip()):
            raise ValueError("Actual obedience and its nonblank account must be supplied together")
        if self.play not in ("all_out_assault", "go_for_the_core") and any(
            x is not None for x in (self.attacking_asset, self.target_asset, self.battle_context)
        ):
            raise ValueError("Only an actual battle Play accepts battle Asset/context fields")
        return self


class ChoiceAnswer(Model):
    options: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()
    text: str = Field(default="", max_length=1200)
    fields: dict[str, str] = Field(default_factory=dict, max_length=12)
    number: int | None = None
    flag: bool | None = None
    member: Snowflake | None = None

    @model_validator(mode="after")
    def bounded(self) -> "ChoiceAnswer":
        if len(set(self.options)) != len(self.options) or len(set(self.denied)) != len(self.denied):
            raise ValueError("Choose distinct options")
        if len(self.options) > 25 or len(self.denied) > 25:
            raise ValueError("Too many choices")
        if any(len(k) > 80 or len(v) > 1200 for k, v in self.fields.items()):
            raise ValueError("Choice details exceed supported bounds")
        return self


def pair_key(first: int, second: int) -> str:
    return ":".join(str(x) for x in sorted((first, second)))


def tier(total: int) -> Literal["low", "mid", "high"]:
    return "low" if total <= 7 else "mid" if total <= 10 else "high"


def shift_status(state: GameState, owner: int, delta: int) -> None:
    from girlframe.engine.m3_intracadre_marriage import status_groups

    groups = list(status_groups(state))
    if owner not in state.order or delta not in (-1, 1):
        raise ValueError("Invalid Status shift")
    before = groups[-1]
    old = next(i for i, group in enumerate(groups) if owner in group)
    new = min(max(old - delta, 0), len(groups) - 1)
    groups[old], groups[new] = groups[new], groups[old]
    state.order = tuple(member for group in groups for member in group)
    if before != groups[-1]:
        for member in before:
            if str(member) in state.sheets:
                state.sheets[str(member)].status_marked = False


def higher(state: GameState, first: int, second: int) -> bool:
    if first == second:
        return False
    if state.alpha_broken:
        from girlframe.engine.m3_alpha import legacy_status

        override = legacy_status(state, first, second)
        if override is not None:
            return override
    if first == state.handler:
        return True
    if second == state.handler:
        return False
    a, b = state.sheets.get(str(first)), state.sheets.get(str(second))
    from girlframe.engine.m3_girl_runtime_state import has_rule, relation_current

    a_mentor = (
        a is not None
        and a.mentor == second
        and has_rule(a, "girl.newgirl.mentor", "NEWGIRL")
        and relation_current(a, "mentor", state)
    )
    b_mentor = (
        b is not None
        and b.mentor == first
        and has_rule(b, "girl.newgirl.mentor", "NEWGIRL")
        and relation_current(b, "mentor", state)
    )
    if a_mentor and b_mentor:
        raise ValueError("Reciprocal Mentor authority is unresolved")
    if a_mentor:
        return False
    if b_mentor:
        return True
    if first not in state.order or second not in state.order:
        raise ValueError("Status is unresolved")
    from girlframe.engine.m3_intracadre_marriage import rank

    return rank(state, first) < rank(state, second)


def mark_identity(
    sheet: PilotSheet, entry: str, gain: int, share: int = 0, *, state: GameState | None = None
) -> int:
    identity = next((x for x in sheet.identities if x.id == entry), None)
    if identity is None or identity.marked:
        raise ValueError("Choose an unmarked Identity")
    if not set(sheet.obsession_sources) <= set(identity.obsession_sources):
        raise ValueError("Only an actual source-qualifying obsessed Identity can generate Heat")
    from girlframe.engine.m3_girl_runtime_state import has_rule, relation_current

    if identity.paired and has_rule(sheet, "girl.bonded.bonded-pair", "BONDED"):
        if (
            share
            and sheet.girl_runtime
            and sheet.girl_runtime.setup
            and (state is None or not relation_current(sheet, "pair", state))
        ):
            raise ValueError("Share Heat only with the actual original Pair")
        if gain != 5 or not 0 <= share <= 5:
            raise ValueError("Paired Identity grants five Heat, split by its owner")
    elif not 1 <= gain <= 3 or share:
        raise ValueError("An ordinary Identity grants one to three Heat")
    identity.marked = True
    sheet.heat += gain - share
    return share


def spend_heat(sheet: PilotSheet, amount: int) -> None:
    if amount < 0 or amount > sheet.heat or (sheet.heat >= 5 and amount != sheet.heat):
        raise ValueError("Spend available Heat; holding five or more requires spending all")
    sheet.heat -= amount
