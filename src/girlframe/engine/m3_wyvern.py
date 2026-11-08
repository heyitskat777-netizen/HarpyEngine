"""WYVERN source state; its Leviathan Chassis is not a Gorgon Leviathan."""

from typing import Literal, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, ProfileBinding, SceneCast
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

FRAME = "WYVERN 0.4"
BASE = "frame.wyvern."
BEAST, BURDEN, CHASSIS = (
    BASE + x for x in ("a-vast-and-tractless-beast", "a-heavy-burden", "leviathan-chassis")
)
CRUSH, DEEP, RENOVATE, WRAITH, PROTECT = (
    BASE + x
    for x in (
        "crushing-bulk",
        "deep-exploration",
        "renovation-permission-forms",
        "wraith-am",
        "protector",
    )
)
REQUISITIONS = (CRUSH, DEEP, RENOVATE, WRAITH, PROTECT)
PLAYS = {
    "wyvern_explore": BEAST,
    "wyvern_rouse": BURDEN,
    "wyvern_wraith": WRAITH,
    "wyvern_protector": PROTECT,
}
QUESTIONS = {
    "servers": "What do I find in the server rooms, beeping and humming?",
    "engine": "What do I find in the engine room, burning hot?",
    "cots": "What do I find in the cots, hidden beneath the beds and blankets?",
    "cockpit": "What do I find in the cockpit, most of its chairs lying cold and empty?",
    "halls": "What do I find in the halls, seemingly endless and terribly dark?",
    "kitchen": "What do I find in the kitchen, between expired ration packets?",
    "panel": "What do I find in a secret panel, installed with rudimentary tools?",
    "armour": "What do I find outside the Frame, wedged in the vast tracts of armour plating?",
}
SLOTS = ("gunner", "navigator", "captain", "battery")
BONUSES = {
    "gunner": ("all_out_assault",),
    "navigator": ("dive_deep",),
    "captain": ("keep_your_head", "put_someone_beneath_you"),
    "battery": ("disobey_orders", "check_sensors"),
}


class Session(Model):
    id: str
    actor: ActorRef
    target: ActorRef | None
    frame: str
    play: Literal["wyvern_explore", "wyvern_rouse", "wyvern_wraith", "wyvern_protector"]
    handler: ActorRef
    handler_controller: int
    cast: SceneCast
    total: int
    roll_event: str
    event: str
    work: tuple[str, ...] = ()
    completed_event: str | None = None
    party: str | None = None
    questions: tuple[str, ...] = ()
    unmarked_event: str | None = None
    answers_closed_event: str | None = None
    danger: str | None = None
    wraith: str | None = None
    shield: str | None = None
    handler_play: str | None = None


class Party(Model):
    id: str
    actor: ActorRef
    frame: str
    cast: SceneCast
    companions: tuple[ActorRef, ...]
    event: str
    present: tuple[ActorRef, ...] = ()
    attendance_events: dict[str, str] = {}
    bound_action: str | None = None
    cancelled_event: str | None = None


class Question(Model):
    id: str
    session: str
    actor: ActorRef
    frame: str
    text: str
    table: tuple[int, ...]
    event: str
    closed_event: str | None = None


class Answer(Model):
    id: str
    question: str
    author: int
    text: str
    event: str


class Danger(Model):
    id: str
    session: str
    actor: ActorRef
    frame: str
    kind: Literal["delay", "escape"]
    event: str
    elapsed_event: str | None = None
    child: str | None = None
    child_completed_event: str | None = None
    returned_event: str | None = None


class Roused(Model):
    id: str
    actor: ActorRef
    frame: str
    session: str
    event: str
    use: str | None = None


class Last(Model):
    id: str
    actor: ActorRef
    frame: str
    session: str
    event: str
    unlinked_event: str | None = None


class RousedUse(Model):
    id: str
    actor: ActorRef
    frame: str
    roused: str
    target: ActorRef
    kind: Literal["strike", "too_big", "pin"]
    cast: SceneCast
    event: str
    asset: str | None = None
    target_frame: str | None = Field(default=None, exclude_if=lambda value: value is None)
    incoming: str | None = None
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Pin(Model):
    id: str
    use: str
    actor: ActorRef
    target: ActorRef
    frame: str
    event: str
    ended_event: str | None = None
    child: str | None = None


class Cargo(Model):
    id: str
    actor: ActorRef
    frame: str
    owner: ActorRef
    guest_frame: str
    event: str
    accepted_event: str | None = None
    boarded_event: str | None = None
    ended_event: str | None = None


class InteriorGuest(Model):
    id: str
    session: str
    actor: ActorRef
    carrier: ActorRef
    frame: str
    controller: int
    accepted_event: str
    entered_event: str
    original_pose: str
    ended_event: str | None = None


class Shield(Model):
    id: str
    session: str
    actor: ActorRef
    frame: str
    target: ActorRef
    target_vessel: str | None
    high: bool
    event: str
    ended_event: str | None = None


class Approach(Model):
    id: str
    shield: str
    actor: ActorRef
    controller: int
    event: str
    gave_up_event: str | None = None
    tag: str | None = None


class DeepQuestions(Model):
    id: str
    actor: ActorRef
    frame: str
    receipt: str
    questions: tuple[str, str]
    event: str


class Renovation(Model):
    id: str
    actor: ActorRef
    frame: str
    receipt: str
    handler: ActorRef
    handler_controller: int
    room: str
    kind: Literal["contraband", "past", "void"]
    name: str
    description: str
    replace: str | None
    event: str
    answer: str | None = None
    answered_event: str | None = None
    asset: str | None = None
    completed_event: str | None = None
    work: tuple[str, ...] = ()


class Wraith(Model):
    id: str
    actor: ActorRef
    frame: str
    slot: Literal["gunner", "navigator", "captain", "battery"]
    name: str
    persona: ActorRef | None
    handler: ActorRef
    handler_controller: int
    session: str
    table: tuple[int, ...]
    event: str
    profile: Literal["frame_bound_npc"] | None = None
    rules_answer: str | None = None
    rules_event: str | None = None
    controller: int | None = None
    active: bool = False
    stubborn: bool = False
    tag: str | None = None
    ended_event: str | None = None


class Voice(Model):
    id: str
    wraith: str
    author: int
    text: str
    event: str


KINDS: dict[type[Model], str] = {
    Session: "wyvern_session",
    Party: "wyvern_party",
    Question: "wyvern_question",
    Answer: "wyvern_answer",
    Danger: "wyvern_danger",
    Roused: "wyvern_roused",
    Last: "wyvern_last",
    RousedUse: "wyvern_use",
    Pin: "wyvern_pin",
    Cargo: "wyvern_cargo",
    InteriorGuest: "wyvern_interior_guest",
    Shield: "wyvern_shield",
    Approach: "wyvern_approach",
    DeepQuestions: "wyvern_deep",
    Renovation: "wyvern_renovation",
    Wraith: "wyvern_wraith",
    Voice: "wyvern_voice",
}
type Source = (
    Session
    | Party
    | Question
    | Answer
    | Danger
    | Roused
    | Last
    | RousedUse
    | Pin
    | Cargo
    | InteriorGuest
    | Shield
    | Approach
    | DeepQuestions
    | Renovation
    | Wraith
    | Voice
)


def identity(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:wyvern:" + kind + ":" + ":".join(parts)))


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def all_records(
    state: GameState, models: tuple[type[Model], ...] | None = None
) -> tuple[Source, ...]:
    return tuple(
        cast(Source, model.model_validate_json(item["body"]))
        for model in (models or tuple(KINDS))
        for item in state.facts
        if item.get("kind") == KINDS[model]
    )


def put(state: GameState, source: Source) -> None:
    kind = KINDS[type(source)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == source.id)
    ]
    state.facts.append(dict(kind=kind, id=source.id, body=source.model_dump_json()))


def session(state: GameState, identity: str) -> Session:
    result = next((x for x in records(state, Session) if x.id == identity), None)
    if result is None:
        raise ValueError("Recover the actual original Wyvern source Session")
    return result


def frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame != FRAME
        or sheet.frame_scrapped
    ):
        raise ValueError("Use the actual original Pilot and her original living WYVERN Frame")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


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
            and x.donor_frame == FRAME
            and not suspended(state, x.id)
        ),
        None,
    )


def roused(state: GameState, actor: ActorRef, original: str | None = None) -> Roused | None:
    actual = original or frame(state, actor)
    return next(
        (x for x in reversed(records(state, Roused)) if x.frame == actual and x.use is None), None
    )


def spend_roused(state: GameState, use: RousedUse) -> None:
    source = next((x for x in records(state, Roused) if x.id == use.roused), None)
    if source is None or source.use is not None or source.frame != use.frame:
        raise ValueError("Spend the one actual original physical Frame's Roused state once")
    put(state, source.model_copy(update={"use": use.id}))
    put(state, use)


def acts_last(state: GameState, actor: ActorRef) -> bool:
    return any(x.actor == actor and not x.unlinked_event for x in records(state, Last))


def pinned(state: GameState, actor: ActorRef) -> Pin | None:
    return next((x for x in records(state, Pin) if x.target == actor and not x.ended_event), None)


def bindings(state: GameState) -> tuple[ProfileBinding, ...]:
    # Read actual canonical originals; this produces no profile or new actor.
    return tuple(
        ProfileBinding(
            owner=sheet.owner,
            character_id=sheet.character_id,
            profile_revision=sheet.source_profile_revision,
        )
        for sheet in state.sheets.values()
        if sheet.character_id is not None
    )


def carried_recipient(state: GameState, source: Shield, actual: ActorView) -> bool:
    if not actual.inside_frame or actual.occupied_frame_instance is None:
        return False
    occupied = actual.occupied_frame_instance
    seen: set[str] = set()
    while occupied not in seen:
        if occupied == source.frame:
            return True
        seen.add(occupied)
        container = next(
            (
                x
                for x in records(state, Cargo)
                if x.guest_frame == occupied and x.boarded_event and not x.ended_event
            ),
            None,
        )
        if container is None:
            return False
        occupied = container.frame
    return False


def shield_active(state: GameState, source: Shield) -> bool:
    from girlframe.engine.m3_actors import frame_position, resolve

    if source.ended_event:
        return False
    try:
        actual = resolve(
            state,
            source.target,
            bindings(state),
            require_alive=False,
            require_current_profile=False,
        )
    except ValueError:
        # Unknown geometry never silently removes the actual source protection.
        return True
    if (
        not actual.alive
        or actual.offstage_source
        or source.target_vessel is not None
        and actual.vessel_id is not None
        and source.target_vessel != actual.vessel_id
    ):
        return False
    if carried_recipient(state, source, actual):
        return True
    located = frame_position(state, source.actor, source.frame)
    return not (located is not None and actual.cell is not None and located != actual.cell)


def shielded(state: GameState, actor: ActorRef) -> Shield | None:
    return next(
        (
            source
            for source in records(state, Shield)
            if source.target == actor and shield_active(state, source)
        ),
        None,
    )


def cargo(state: GameState, owner: ActorRef, original: str) -> Cargo | None:
    return next(
        (
            x
            for x in records(state, Cargo)
            if x.owner == owner
            and x.guest_frame == original
            and x.boarded_event
            and not x.ended_event
        ),
        None,
    )


def wraith_bonus(state: GameState, actor: ActorRef, play: str) -> int:
    try:
        original = frame(state, actor)
    except ValueError:
        return 0
    return int(
        any(
            x.frame == original and x.active and x.persona and x.profile and play in BONUSES[x.slot]
            for x in records(state, Wraith)
        )
    )


def questions(state: GameState, actor: ActorRef) -> dict[str, str]:
    result = dict(QUESTIONS)
    original = frame(state, actor)
    for source in records(state, DeepQuestions):
        if source.actor == actor and source.frame == original:
            result.update(
                {
                    identity("question", source.id, str(index)): text
                    for index, text in enumerate(source.questions)
                }
            )
    return result
