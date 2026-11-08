"""CONSUME source state belongs to real people and their original physical Frame."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import AssetState, GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

BASE = "frame.consume."
STARVATION, EAT = BASE + "starvation", BASE + "eat"
HOUND = BASE + "human-hound"
PARTAKE = BASE + "let-us-partake"
FORMS = BASE + "cannibal-requisition-forms"
FERAL = BASE + "feral"
NIBBLE = BASE + "just-a-nibble"
DRIVE = BASE + "ontological-consumption-drive"
TIME = BASE + "time-to-eat"
REQUISITIONS = (HOUND, PARTAKE, FORMS, FERAL, NIBBLE, DRIVE, TIME)
PLAYS = {"consume_eat": EAT, "consume_feral": FERAL}
type Level = Literal["Quiet", "Gnawing", "Ravenous"]
LEVELS: tuple[Level, ...] = ("Quiet", "Gnawing", "Ravenous")
TAGS = {"rabid": "Rabid Mutt", "bloodhound": "Bloodhound"}


class Hunger(Model):
    id: str
    actor: ActorRef
    frame: str
    level: Literal["Quiet", "Gnawing", "Ravenous"]
    event: str


class HungerTrigger(Model):
    id: str
    actor: ActorRef
    frame: str
    subject: ActorRef
    kind: Literal["link", "helpless"]
    before: Literal["Quiet", "Gnawing", "Ravenous"]
    after: Literal["Quiet", "Gnawing", "Ravenous"]
    event: str


class StarvationMark(Model):
    id: str
    actor: ActorRef
    marker: ActorRef
    frame: str
    scene: str
    level: Literal["Quiet", "Gnawing", "Ravenous"]
    event: str


class Session(Model):
    id: str
    play: Literal["consume_eat", "consume_feral"]
    actor: ActorRef
    target: ActorRef | None
    handler: ActorRef
    handler_controller: int
    frame: str
    cast: SceneCast
    hunger: Literal["Quiet", "Gnawing", "Ravenous"]
    vulnerable: bool
    killable: bool
    total: int
    roll_event: str
    event: str
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Consumption(Model):
    id: str
    session: str
    actor: ActorRef
    target: ActorRef
    option: Literal["bite", "kill", "swallow", "nibble", "repelled"]
    own_asset: str | None = None
    target_asset: str | None = None
    custody: str | None = None
    event: str
    choice: str | None = None
    escaped_event: str | None = None


class MouthHold(Model):
    id: str
    session: str
    actor: ActorRef
    target: ActorRef
    frame: str
    helpless: bool
    event: str
    ended_event: str | None = None


class FeralEffect(Model):
    id: str
    session: str
    actor: ActorRef
    handler: ActorRef
    tag: str
    label: str
    tier: Literal["low", "mid", "high"]
    event: str


class Reaffirmation(Model):
    id: str
    session: str
    actor: ActorRef
    tag: str
    event: str
    action: str | None = None
    completed_event: str | None = None


class CannibalPermit(Model):
    id: str
    receipt: str
    actor: ActorRef
    frame: str
    target: ActorRef
    handler: ActorRef
    event: str


class Partaking(Model):
    id: str
    action: str
    actor: ActorRef
    option: Literal["regrow", "excrete", "appearance"]
    girl_asset: str
    frame_assets: tuple[str, ...] = ()
    appearance: str = ""
    event: str
    work: tuple[str, ...] = ()
    replaced_frame: str | None = None


class Erasure(Model):
    id: str
    session: str
    actor: ActorRef
    target: ActorRef
    event: str


class Opportunity(Model):
    id: str
    action: str
    actor: ActorRef
    target: ActorRef | None
    kind: Literal["partake", "time_eat"]
    event: str
    completed_event: str | None = None
    primary_waiting: bool = False
    primary_resumed_event: str | None = None


class PermitRequest(Model):
    id: str
    actor: ActorRef
    frame: str
    target: ActorRef
    handler: ActorRef
    handler_controller: int
    event: str
    superior: bool | None = None
    review_event: str | None = None
    receipt: str | None = None
    completed_event: str | None = None


class InternalCustody(Model):
    id: str
    session: str
    actor: ActorRef
    target: ActorRef
    frame: str
    event: str
    original_position: str | None = None
    cell: tuple[int, int]
    escaped_event: str | None = None


class OrderPursuit(Model):
    id: str
    actor: ActorRef
    feral: str
    tag: str
    order: str
    parent: str
    scene: SceneCast
    mode: Literal["tag", "hunger"]
    event: str
    choice: str
    action: str | None = None
    completed_event: str | None = None


KINDS = {
    Hunger: "consume_hunger",
    HungerTrigger: "consume_hunger_trigger",
    StarvationMark: "consume_starvation_mark",
    Session: "consume_session",
    Consumption: "consume_consumption",
    MouthHold: "consume_mouth_hold",
    FeralEffect: "consume_feral",
    Reaffirmation: "consume_reaffirmation",
    CannibalPermit: "consume_permit",
    Partaking: "consume_partaking",
    Erasure: "consume_erasure",
    Opportunity: "consume_opportunity",
    PermitRequest: "consume_permit_request",
    InternalCustody: "consume_internal_custody",
    OrderPursuit: "consume_order_pursuit",
}

type Source = (
    Hunger
    | HungerTrigger
    | StarvationMark
    | Session
    | Consumption
    | MouthHold
    | FeralEffect
    | Reaffirmation
    | CannibalPermit
    | Partaking
    | Erasure
    | Opportunity
    | PermitRequest
    | InternalCustody
    | OrderPursuit
)


def identity(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:consume:" + kind + ":" + ":".join(parts)))


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Source) -> None:
    kind = KINDS[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame != "CONSUME"
        or sheet.frame_scrapped
    ):
        raise ValueError("Use the actual original living CONSUME Pilot and physical Frame")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def hunger(state: GameState, actor: ActorRef) -> Literal["Quiet", "Gnawing", "Ravenous"]:
    original = frame(state, actor)
    values = [x for x in records(state, Hunger) if x.frame == original]
    if len(values) > 1:
        raise ValueError("Recover this one physical Frame's original starvation source")
    if values:
        return values[0].level
    runtime = state.sheets[actor.entity].frame_runtime
    return runtime.consume_hunger if runtime and runtime.consume_hunger else "Quiet"


def starving_asset(original_frame: str) -> str:
    return identity("starving", original_frame)


def _level(
    state: GameState,
    actor: ActorRef,
    level: Literal["Quiet", "Gnawing", "Ravenous"],
    event: str,
) -> None:
    original = frame(state, actor)
    sheet = state.sheets[actor.entity]
    if sheet.frame_runtime:
        sheet.frame_runtime = sheet.frame_runtime.model_copy(update={"consume_hunger": level})
    asset = starving_asset(original)
    if level == "Quiet":
        sheet.assets = [x for x in sheet.assets if x.id != asset]
    elif not any(x.id == asset for x in sheet.assets):
        sheet.assets.append(
            AssetState(
                id=asset,
                family="girl",
                name="Starving",
                description="CONSUME's source-bound temporary starvation Asset",
            )
        )
    sheet.revision += 1
    put(
        state,
        Hunger(
            id=identity("hunger", original), actor=actor, frame=original, level=level, event=event
        ),
    )


def increase(
    state: GameState,
    actor: ActorRef,
    subject: ActorRef,
    kind: Literal["link", "helpless"],
    event: str,
) -> None:
    original = frame(state, actor)
    key = identity("trigger", original, subject.token, kind, event)
    previous = next((x for x in records(state, HungerTrigger) if x.id == key), None)
    if previous:
        if previous.actor != actor or previous.subject != subject or previous.event != event:
            raise ValueError("Preserve the actual original hunger trigger")
        return
    before = hunger(state, actor)
    after = LEVELS[min(2, LEVELS.index(before) + 1)]
    if before == "Quiet" and after == "Gnawing":
        state.sheets[actor.entity].heat += 3
    _level(state, actor, after, event)
    put(
        state,
        HungerTrigger(
            id=key,
            actor=actor,
            frame=original,
            subject=subject,
            kind=kind,
            before=before,
            after=after,
            event=event,
        ),
    )


def fed(state: GameState, actor: ActorRef, event: str, *, entire: bool) -> None:
    before = hunger(state, actor)
    level = "Quiet" if entire else LEVELS[max(0, LEVELS.index(before) - 1)]
    _level(state, actor, level, event)


def held(state: GameState, actor: ActorRef, rule: str) -> FrameRuleReceipt | None:
    original = frame(state, actor)
    return next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt)
            and x.actor == actor
            and x.frame_instance == original
            and x.rule_id == rule
            and x.donor_frame == "CONSUME"
            and not suspended(state, x.id)
        ),
        None,
    )


def tag(state: GameState, actor: ActorRef, identity: str) -> TagState | None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return None
    return next((x for x in sheet.tags if x.id == identity), None)


def feral_effects(state: GameState, actor: ActorRef) -> tuple[FeralEffect, ...]:
    return tuple(
        x for x in records(state, FeralEffect) if x.actor == actor and tag(state, actor, x.tag)
    )


def feral_bonus(state: GameState, actor: ActorRef, play: str) -> int:
    return int(
        any(
            (x.label == TAGS["rabid"] and play in ("all_out_assault", "flirt"))
            or (x.label == TAGS["bloodhound"] and play == "check_sensors")
            for x in feral_effects(state, actor)
        )
    )


def disobey_low(state: GameState, actor: ActorRef) -> bool:
    return any(x.tier == "low" for x in feral_effects(state, actor))


def mouth_helpless(state: GameState, actor: ActorRef, foe: ActorRef | None = None) -> bool:
    return any(
        x.actor == actor and x.helpless and not x.ended_event and (foe is None or x.target == foe)
        for x in records(state, MouthHold)
    )


def forgotten(state: GameState, target: ActorRef) -> bool:
    return any(x.target == target for x in records(state, Erasure))


def permitted(state: GameState, actor: ActorRef, target: ActorRef) -> bool:
    original = frame(state, actor)
    receipts = {
        x.id
        for x in state.requisitions
        if isinstance(x, FrameRuleReceipt)
        and x.actor == actor
        and x.frame_instance == original
        and x.rule_id == FORMS
        and not suspended(state, x.id)
    }
    return any(
        x.actor == actor and x.target == target and x.frame == original and x.receipt in receipts
        for x in records(state, CannibalPermit)
    )


def custody(state: GameState, actor: ActorRef) -> InternalCustody | None:
    return next(
        (
            x
            for x in records(state, InternalCustody)
            if x.target == actor and x.escaped_event is None
        ),
        None,
    )


def session(state: GameState, identity: str) -> Session:
    found = next((x for x in records(state, Session) if x.id == identity), None)
    if found is None:
        raise ValueError("Recover this original committed CONSUME source")
    return found
