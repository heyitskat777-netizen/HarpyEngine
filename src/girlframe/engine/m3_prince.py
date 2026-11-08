"""Prince source records; original people, Frame, fans and real mechanical effects."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.fanbase import QUALITIES
from girlframe.engine.m2 import GameState, IdentityState, higher, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

FANBASE = "frame.prince.fanbase"
PERFORMER = "frame.prince.performer"
HERO = "frame.prince.a-hero-we-can-believe-in"
IMMORTAL = "frame.prince.immortal-hero"
TV = "frame.prince.tv-interviews"
BAD = "frame.prince.bad-girl"
GROWING = "frame.prince.growing-fanbase"
POWER = "frame.prince.power-imbalance"
RULES = (HERO, IMMORTAL, TV, BAD, GROWING, POWER)
PLAY = "prince_performer"
OPTIONS = ("bond", "status", "erase", "dismiss")
TITLES = dict(
    zip(
        RULES,
        (
            "A Hero We Can Believe In",
            "Immortal Hero",
            "TV Interviews",
            "Bad Girl",
            "Growing Fanbase",
            "Power Imbalance",
        ),
        strict=True,
    )
)


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:prince:" + ":".join(parts)))


class Demographic(Model):
    id: str
    name: str = Field(min_length=1, max_length=80)
    identity: str
    event: str


class FanbaseState(Model):
    actor: ActorRef
    frame: str
    origin: str
    demographics: tuple[Demographic, ...]
    demanded: tuple[str, ...]
    rejected: tuple[str, ...]
    event: str

    @model_validator(mode="after")
    def distinct(self) -> "FanbaseState":
        names = [x.name.strip().casefold() for x in self.demographics]
        if (
            len(names) < 2
            or len(set(names)) != len(names)
            or len({x.identity for x in self.demographics}) != len(names)
            or len(self.demanded) != 2
            or len(self.rejected) != 2
            or len({x.strip().casefold() for x in (*self.demanded, *self.rejected)}) != 4
            or any(not x.strip() or len(x) > 80 for x in (*self.demanded, *self.rejected))
            or len(
                {x.casefold() for x in (*self.demanded, *self.rejected)}
                - {x.casefold() for x in QUALITIES}
            )
            > 2
        ):
            raise ValueError(
                "Keep actual distinct demographics and two demanded/two rejected qualities"
            )
        return self


class Grant(Model):
    id: str
    actor: ActorRef
    frame: str
    rule: str
    purchase: str
    event: str
    handler: ActorRef | None = None


class Performance(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    frame: str
    fanbase_event: str
    part: str = Field(min_length=1, max_length=1200)
    following: bool
    account: str = Field(min_length=1, max_length=1200)
    event: str
    action: str | None = None
    bound_event: str | None = None
    result_event: str | None = None
    tier: str | None = None
    conformed_event: str | None = None
    conformed_part: str = ""
    completed_event: str | None = None
    broken_event: str | None = None


class Selection(Model):
    id: str
    performance: str
    action: str
    choice: str
    controller: int
    option: str
    event: str
    tags: tuple[str, ...] = ()
    account: str = ""
    case: str | None = None


class Break(Model):
    id: str
    performance: str
    actor: ActorRef
    event: str
    dismissed: bool
    account: str


class Membership(Model):
    id: str
    prince: ActorRef
    member: ActorRef
    controller: int
    demographic: str
    event: str
    account: str


class Recognition(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    handler: ActorRef
    handler_controller: int
    cast: SceneCast
    frame: str
    grant: str
    event: str
    account: str
    branch: Literal["predecessor", "mission", "secret"] | None = None
    selected_event: str | None = None
    question: str = ""
    question_event: str | None = None
    answer: str = ""
    completed_event: str | None = None
    tag: str | None = None


class DemandException(Model):
    id: str
    actor: ActorRef
    fanbase_event: str
    action: str
    receipt: str
    event: str
    account: str
    used_by: str | None = None
    used_event: str | None = None


class DemandAttempt(Model):
    id: str
    actor: ActorRef
    frame: str
    cast: SceneCast
    event: str
    account: str
    action: str | None = None
    bound_event: str | None = None


class DemographicMark(Model):
    id: str
    actor: ActorRef
    action: str
    receipt: str
    identity: str
    event: str
    account: str


class BadGirlOverride(Model):
    id: str
    actor: ActorRef
    action: str
    choice: str
    receipt: str
    grant: str
    fanbase_event: str
    before: int
    total: Literal[11] = 11
    event: str
    account: str


class PlanGrant(Model):
    id: str
    actor: ActorRef
    handler: ActorRef
    controller: int
    cast: SceneCast
    action: str
    override: str | None = None
    grant: str
    event: str
    used_event: str | None = None
    account: str = ""
    recipients: tuple[int, ...] = ()
    reveal_cast: SceneCast | None = None


class PlanUse(Model):
    id: str
    plan: str
    actor: ActorRef
    handler: ActorRef
    controller: int
    cast: SceneCast
    action: str
    event: str
    account: str
    recipients: tuple[int, ...]


class OffDutyTask(Model):
    id: str
    actor: ActorRef
    frame: str
    period: str
    action: str
    receipt: str
    rule: str
    grant: str
    event: str
    completed_event: str | None = None
    option: str | None = None
    account: str = ""


class Hero(Model):
    id: str
    actor: ActorRef
    frame: str
    grant: str
    first: bool
    event: str


class Discipline(Model):
    id: str
    actor: ActorRef
    executor: ActorRef
    controller: int
    frame: str | None
    cast: SceneCast
    source: str
    action: str | None
    event: str
    case: str
    completed_event: str | None = None


class Violation(Model):
    id: str
    actor: ActorRef
    handler: ActorRef
    controller: int
    cast: SceneCast
    event: str
    account: str
    disclosed: bool
    case: str | None = None
    decided_event: str | None = None


KINDS = {
    FanbaseState: "prince_fanbase",
    Grant: "prince_grant",
    Performance: "prince_performance",
    Selection: "prince_selection",
    Break: "prince_break",
    Membership: "prince_member",
    Recognition: "prince_recognition",
    DemandException: "prince_exception",
    DemandAttempt: "prince_demand_attempt",
    DemographicMark: "prince_demographic_mark",
    BadGirlOverride: "prince_override",
    PlanGrant: "prince_plan",
    PlanUse: "prince_plan_use",
    OffDutyTask: "prince_off_duty",
    Hero: "prince_hero",
    Discipline: "prince_discipline",
    Violation: "prince_violation",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind = KINDS[type(value)]
    key = (
        value.actor.token + ":" + value.frame
        if isinstance(value, FanbaseState)
        else value.model_dump()["id"]
    )
    state.facts = [x for x in state.facts if not (x.get("kind") == kind and x.get("id") == key)]
    state.facts.append(dict(kind=kind, id=key, body=value.model_dump_json()))


def current_frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame_scrapped
    ):
        raise ValueError("Use the actual original living Girl and current existing Frame")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def current_fanbase(state: GameState, actor: ActorRef) -> FanbaseState | None:
    frame = current_frame(state, actor)
    return next(
        (x for x in records(state, FanbaseState) if x.actor == actor and x.frame == frame), None
    )


def demographic_for(state: GameState, actor: ActorRef, identity_id: str) -> Demographic | None:
    value = current_fanbase(state, actor)
    return (
        next((x for x in value.demographics if x.identity == identity_id), None) if value else None
    )


def official_pronouns(state: GameState, actor: ActorRef) -> dict[str, str] | None:
    values = [x for x in records(state, Hero) if x.actor == actor]
    if not values:
        return None
    result = dict(girl="he/him")
    sheet = state.sheets.get(actor.entity)
    frame = (
        (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation))
        if sheet is not None and sheet.character_id == actor.incarnation
        else None
    )
    if any(x.frame == frame for x in values):
        result["frame"] = "he/him"
    return result


def presentation(state: GameState, actor: ActorRef, scene: str) -> str | None:
    values = [
        x
        for x in records(state, Performance)
        if x.actor == actor
        and x.cast.id == scene
        and x.tier in ("mid", "high")
        and x.result_event
        and (x.tier != "high" or x.following or x.conformed_event)
        and not x.broken_event
    ]
    return (values[-1].conformed_part or values[-1].part) if values else None


def can_detect_act(state: GameState, actor: ActorRef, scene: str) -> bool:
    return presentation(state, actor, scene) is None


def promote(state: GameState, actor: ActorRef, *, first: bool) -> None:
    if first:
        while not higher(state, int(actor.entity), state.order[0]) and state.order[0] != int(
            actor.entity
        ):
            from girlframe.engine.m3_intracadre_marriage import rank

            if rank(state, int(actor.entity)) == 0:
                break
            shift_status(state, int(actor.entity), 1)
    else:
        shift_status(state, int(actor.entity), 1)


def add_demographic(state: GameState, value: FanbaseState, name: str, event: str) -> FanbaseState:
    entry = Demographic(
        id=identity(value.actor.token, value.frame, "demographic", event),
        name=name.strip(),
        identity=identity(value.actor.token, value.frame, "fan", event),
        event=event,
    )
    changed = value.model_copy(update=dict(demographics=(*value.demographics, entry), event=event))
    changed = FanbaseState.model_validate_json(changed.model_dump_json())
    state.sheets[value.actor.entity].identities.append(
        IdentityState(id=entry.identity, name=entry.name, protected=True)
    )
    state.sheets[value.actor.entity].revision += 1
    put(state, changed)
    return changed
