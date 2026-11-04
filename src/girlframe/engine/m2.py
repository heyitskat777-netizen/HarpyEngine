"""Canonical pilot state and typed human inputs for the audited M2 subset."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.creation_review import ReviewSheet
from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_frame_state import FrameRuntime

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


class AssetState(Model):
    id: str
    family: Literal["girl", "frame"]
    name: str
    description: str = ""
    damaged: bool = False
    void: bool = False


class TagState(Model):
    id: str
    label: str = Field(min_length=1, max_length=120)
    giver: Snowflake
    observers: tuple[Snowflake, ...] = ()
    marked: bool = False
    scene_used: str | None = None
    rejection_pending: bool = False


class PilotSheet(Model):
    owner: Snowflake
    revision: int = 1
    callsign: str
    girl: str
    frame: str
    source_fingerprint: str
    source_profile_revision: int
    review: ReviewSheet
    identities: list[IdentityState]
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
    libido_inhibited: bool = False
    obsolescence_marked: int = Field(default=0, ge=0, le=8)
    frame_scrapped: bool = False
    frame_runtime: FrameRuntime | None = None

    @model_validator(mode="after")
    def unique_ids(self) -> "PilotSheet":
        for collection in (self.identities, self.assets, self.tags):
            ids = [x.id for x in collection]
            if len(ids) != len(set(ids)):
                raise ValueError("Canonical entity IDs must be distinct")
        if len([x for x in self.identities if not x.protected or x.paired]) > 4:
            raise ValueError("A Girl has at most four ordinary/Paired Identities")
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
    bonds: dict[str, int] = Field(default_factory=dict)
    obligations: list[Obligation] = Field(default_factory=list)
    facts: list[dict[str, str]] = Field(default_factory=list)
    intense_tag_bonus: int | None = None


class PlayInput(Model):
    play: str
    context: str = Field(min_length=1, max_length=1200)
    trigger_confirmed: Literal[True]
    heat: int = Field(ge=0)
    identity: str | None = None
    gain: int = Field(default=0, ge=0, le=5)
    pair_share: int = Field(default=0, ge=0, le=5)
    target: Snowflake | None = None
    piloting: bool = False
    order_id: str | None = None
    witnessed: bool = False
    parent: str | None = None


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
    order = list(state.order)
    if owner not in order or delta not in (-1, 1):
        raise ValueError("Invalid Status shift")
    before = order[-1]
    old = order.index(owner)
    new = min(max(old - delta, 0), len(order) - 1)
    order[old], order[new] = order[new], order[old]
    state.order = tuple(order)
    if before != order[-1] and str(before) in state.sheets:
        state.sheets[str(before)].status_marked = False


def higher(state: GameState, first: int, second: int) -> bool:
    if first == second:
        return False
    if first == state.handler:
        return True
    if second == state.handler:
        return False
    a, b = state.sheets.get(str(first)), state.sheets.get(str(second))
    if a and b and a.mentor == second and b.mentor == first:
        raise ValueError("Reciprocal Mentor authority is unresolved")
    if a and a.mentor == second:
        return False
    if b and b.mentor == first:
        return True
    if first not in state.order or second not in state.order:
        raise ValueError("Status is unresolved")
    return state.order.index(first) < state.order.index(second)


def mark_identity(sheet: PilotSheet, entry: str, gain: int, share: int = 0) -> int:
    identity = next((x for x in sheet.identities if x.id == entry), None)
    if identity is None or identity.marked:
        raise ValueError("Choose an unmarked Identity")
    if identity.paired:
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
