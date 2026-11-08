"""Red Queen Court residency and human-authored fictional memory; no simulated people."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.shared_setup import AM_ROLES

FRAME = "THE RED QUEEN"
BASE = "frame.red-queen."
COURT, TRANSFER, CONSULT = (BASE + x for x in ("queens-court", "am-transfer", "consult-the-court"))
PERSONALITY, PANOPTICON, JUDGEMENT, ACCUSATION, REGIMENT, MEMORY = (
    BASE + x
    for x in (
        "personality-extraction",
        "one-girl-panopticon",
        "judgement-on-high",
        "biting-accusation",
        "regiment-commander",
        "memory-extraction",
    )
)
REQUISITIONS = (PERSONALITY, PANOPTICON, JUDGEMENT, ACCUSATION, REGIMENT, MEMORY)
PLAYS = {
    "red_queen_consult": CONSULT,
    "red_queen_panopticon": PANOPTICON,
    "red_queen_memory": MEMORY,
}
QUESTIONS = {
    "where": "Where are you?",
    "hour": "Where will you be in an hour?",
    "fidget": "How do you fidget when you’re alone?",
    "flinch": "What makes you flinch?",
    "clothes": "What are you hiding under your clothes?",
    "opinion": "What opinion are you keeping a secret?",
    "ashamed": "What are you ashamed of?",
    "light": "What makes your eyes light up?",
    "repulsive": "Who do you find repulsive?",
    "void": "Where have you gained Void?",
}
DESIRES = dict(
    zip(
        AM_ROLES,
        ("service from others", "sex", "someone to protect", "a master", "escape"),
        strict=True,
    )
)


def identity(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:red-queen:" + kind + ":" + ":".join(parts)))


class Context(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    cast: SceneCast
    kind: Literal["distant", "brain", "watching"]
    actor_position: str | None
    target_position: str | None
    actor_vessel: str | None
    target_vessel: str | None
    actor_frame: str | None
    target_frame: str | None
    actor_cell: tuple[int, int] | None
    target_cell: tuple[int, int] | None
    author: int
    source_role: ActorRef
    account: str
    event: str


class Court(Model):
    id: str
    actor: ActorRef
    frame: str
    source_event: str
    event: str
    initial: dict[str, ActorRef]


class CourtAM(Model):
    id: str
    court: str
    role: str
    bearer: ActorRef
    event: str
    state_event: str
    person: ActorRef | None = None
    marked_event: str | None = None
    assigned_event: str | None = None
    installed_identity: str | None = None


class Assignment(Model):
    id: str
    court: str
    am: str
    previous: ActorRef
    target: ActorRef
    source: str
    source_event: str
    event: str


class Mark(Model):
    cast: SceneCast
    id: str
    court: str
    am: str
    actor: ActorRef
    target: ActorRef
    kind: Literal["status", "flirt", "bond", "assault", "doll", "helpless", "order", "modifier"]
    event: str
    counterpart: ActorRef | None = None
    instruction: str = ""
    amount: int = 0
    roll: str | None = None
    work: tuple[str, ...] = ()
    child: str | None = None
    order: str | None = None
    used_action: str | None = None
    applied_event: str | None = None
    completed_event: str | None = None


class Session(Model):
    target_controller: int | None
    id: str
    actor: ActorRef
    target: ActorRef | None
    court: str
    frame: str
    play: str
    cast: SceneCast
    handler: ActorRef
    handler_controller: int
    registry: str
    roll_event: str
    total: int
    event: str
    selected_event: str | None = None
    decree: str | None = None
    recalled: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    replies: dict[str, str] = {}
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Decree(Model):
    id: str
    court: str
    session: str
    actor: ActorRef
    text: str = Field(min_length=1, max_length=1200)
    event: str


class Advice(Model):
    cast: SceneCast
    id: str
    court: str
    session: str | None
    am: str
    actor: ActorRef
    author: int
    event: str
    instruction: str = ""
    order: str | None = None
    answered_event: str | None = None


class Breach(Model):
    id: str
    decree: str
    court: str
    actor: ActorRef
    target: ActorRef
    am: str
    account: str
    event: str
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Extraction(Model):
    id: str
    court: str
    session: str
    actor: ActorRef
    target: ActorRef
    category: Literal["person", "place", "day", "year"]
    scope: str
    memories: tuple[str, ...]
    identities: tuple[str, ...]
    am: str
    through_revision: int
    low: bool
    event: str
    restored_event: str | None = None
    restored_source: str | None = None
    selected_am: str | None = None


class Accusation(Model):
    id: str
    court: str
    actor: ActorRef
    purchase: str
    target_kind: Literal["girl", "city", "base", "npc"]
    target_actor: ActorRef | None = None
    target: str
    allegation: str
    consequence: str
    consequence_kind: Literal["punishment", "npc_tag", "administrative_closure"]
    consequence_detail: dict[str, str]
    director: ActorRef | None = None
    director_controller: int | None = None
    event: str
    endorsement_event: str | None = None
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Judgement(Model):
    id: str
    court: str
    actor: ActorRef
    target: ActorRef
    tag: str
    tag_event: str
    context: str
    event: str


class Reset(Model):
    id: str
    court: str
    period: str
    event: str


KINDS: dict[type[Model], str] = {
    Context: "red_queen_context",
    Court: "red_queen_court",
    CourtAM: "red_queen_am",
    Assignment: "red_queen_assignment",
    Mark: "red_queen_mark",
    Session: "red_queen_session",
    Decree: "red_queen_decree",
    Advice: "red_queen_advice",
    Breach: "red_queen_breach",
    Extraction: "red_queen_extraction",
    Accusation: "red_queen_accusation",
    Reset: "red_queen_reset",
    Judgement: "red_queen_judgement",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, key = KINDS[type(value)], str(value.model_dump()["id"])
    state.facts = [x for x in state.facts if not (x.get("kind") == kind and x.get("id") == key)]
    state.facts.append(dict(kind=kind, id=key, body=value.model_dump_json()))


def get[T: Model](state: GameState, model: type[T], key: str) -> T:
    value = next((x for x in records(state, model) if str(x.model_dump()["id"]) == key), None)
    if value is None:
        raise ValueError("Open the actual original Red Queen source")
    return value


def frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame != FRAME
        or sheet.frame_scrapped
    ):
        raise ValueError("Use the original current Girl and actual usable Red Queen Frame")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def court(state: GameState, actor: ActorRef) -> Court:
    original = frame(state, actor)
    value = next(
        (x for x in records(state, Court) if x.actor == actor and x.frame == original), None
    )
    if value is None:
        raise ValueError("Import the genuine accepted Court assignment first")
    return value


def ams(state: GameState, value: Court) -> tuple[CourtAM, ...]:
    return tuple(x for x in records(state, CourtAM) if x.court == value.id)


def queen_actor(state: GameState, owner: int) -> ActorRef | None:
    sheet = state.sheets.get(str(owner))
    if sheet is None:
        return None
    ref = ActorRef(kind="pilot", entity=str(owner), incarnation=sheet.character_id)
    value = next(
        (
            x
            for x in records(state, Court)
            if x.actor == ref
            and x.frame
            == (
                sheet.frame_runtime.id
                if sheet.frame_runtime
                else "initial:" + str(sheet.character_id)
            )
        ),
        None,
    )
    return (
        next((x.bearer for x in ams(state, value) if x.role == "The Queen"), None)
        if value
        else None
    )


def assigned(state: GameState, target: ActorRef, source: str | None = None) -> tuple[CourtAM, ...]:
    return tuple(
        x
        for x in records(state, CourtAM)
        if x.bearer == target and (source is None or x.court == source)
    )


def bootstrap(state: GameState, value: Court) -> None:
    if set(value.initial) != set(AM_ROLES) or any(x.id == value.id for x in records(state, Court)):
        raise ValueError("Import each exact genuine five-role Court once")
    put(state, value)
    for role, target in value.initial.items():
        put(
            state,
            CourtAM(
                id=identity("am", value.id, role),
                court=value.id,
                role=role,
                bearer=target,
                event=value.event,
                state_event=value.event,
                assigned_event=value.event,
            ),
        )


def assign(
    state: GameState, value: CourtAM, target: ActorRef, source: str, source_event: str, event: str
) -> Assignment:
    if value.bearer == target:
        raise ValueError("Assign the actual AM to a different original person")
    if value.installed_identity and value.bearer.kind == "pilot":
        old = state.sheets.get(value.bearer.entity)
        if old and old.character_id == value.bearer.incarnation:
            selected = next((x for x in old.identities if x.id == value.installed_identity), None)
            if selected and (
                selected.protected
                or selected.paired
                or selected.am_limiter
                or selected.id in old.sedation_locked
            ):
                raise ValueError(
                    "SOURCE_IMPLANTED_IDENTITY_REQUIRED: preserve protected original AM slot"
                )
            from girlframe.engine.m3_leviathan_obsession import require_unlocked

            if selected:
                require_unlocked(old.identities, (selected.id,))
            old.identities = [x for x in old.identities if x.id != value.installed_identity]
            old.revision += 1
    result = Assignment(
        id=identity("assignment", value.id, event),
        court=value.court,
        am=value.id,
        previous=value.bearer,
        target=target,
        source=source,
        source_event=source_event,
        event=event,
    )
    put(
        state,
        value.model_copy(
            update=dict(
                bearer=target, assigned_event=event, state_event=event, installed_identity=None
            )
        ),
    )
    put(state, result)
    return result


def mark(state: GameState, value: CourtAM, source: Mark) -> None:
    if (
        value.marked_event
        or source.am != value.id
        or source.target != value.bearer
        or source.court != value.court
    ):
        raise ValueError("Mark this actual unmarked Court AM once")
    put(state, value.model_copy(update=dict(marked_event=source.event, state_event=source.event)))
    if value.installed_identity and value.bearer.kind == "pilot":
        sheet = state.sheets[value.bearer.entity]
        for item in sheet.identities:
            if item.id == value.installed_identity:
                item.marked = True
    put(state, source)


def unmark(state: GameState, value: CourtAM, event: str) -> None:
    put(state, value.model_copy(update=dict(marked_event=None, state_event=event)))
    if value.installed_identity and value.bearer.kind == "pilot":
        sheet = state.sheets.get(value.bearer.entity)
        if sheet and sheet.character_id == value.bearer.incarnation:
            for item in sheet.identities:
                if item.id == value.installed_identity:
                    item.marked = False


def reset(state: GameState, actor: ActorRef, period: str, event: str) -> bool:
    value = court(state, actor)
    key = identity("reset", value.id, period)
    if any(x.id == key for x in records(state, Reset)):
        return False
    for item in ams(state, value):
        unmark(state, item, event)
    put(state, Reset(id=key, court=value.id, period=period, event=event))
    return True


def held(state: GameState, actor: ActorRef, rule: str) -> tuple[FrameRuleReceipt, ...]:
    original = frame(state, actor)
    spent = {x.purchase for x in records(state, Accusation)}
    return tuple(
        x
        for x in state.requisitions
        if isinstance(x, FrameRuleReceipt)
        and x.actor == actor
        and x.frame_instance == original
        and x.rule_id == rule
        and x.donor_frame == FRAME
        and x.id not in spent
        and not suspended(state, x.id)
    )


def extract_many(state: GameState, values: tuple[Extraction, ...]) -> None:
    if not values:
        raise ValueError("Choose the actual source memory categories")
    first = values[0]
    if first.target.kind == "npc":
        npc = (
            next((x for x in state.world.npcs if x.id == first.target.entity and x.alive), None)
            if state.world
            else None
        )
        if (
            npc is None
            or npc.source_kind == "wyvern_wraith"
            or any(value.identities for value in values)
        ):
            raise ValueError("Use a real living physical NPC with no invented Identity slots")
        for value in values:
            if (
                (value.target, value.session, value.am) != (first.target, first.session, first.am)
                or not value.memories
                or not value.scope.strip()
            ):
                raise ValueError("Keep the actual NPC compound memory source")
            put(state, value)
        return
    if first.target.kind != "pilot":
        raise ValueError(
            "The current memory Identity adapter requires an actual native Girl or NPC"
        )
    sheet = state.sheets[first.target.entity]
    if sheet.character_id != first.target.incarnation:
        raise ValueError("Preserve the actual original memory subject")
    keys: set[str] = set()
    for value in values:
        if (value.target, value.session, value.am) != (first.target, first.session, first.am):
            raise ValueError("Apply one source-owned existing AM to this actual extraction")
        if (
            not value.memories
            or not value.scope.strip()
            or any(not x.strip() for x in value.memories)
        ):
            raise ValueError("Record exact actual memories and category scope")
        keys.update(value.identities)
    selected = [x for x in sheet.identities if x.id in keys]
    if len(selected) != len(keys) or any(
        x.protected or x.paired or x.am_limiter or x.obsession_sources for x in selected
    ):
        raise ValueError("SOURCE_IDENTITY_ADAPTER_REQUIRED: preserve protected original slots")
    if selected:
        am = get(state, CourtAM, first.am)
        if am.bearer != first.target:
            assign(state, am, first.target, first.session, first.event, first.event)
            am = get(state, CourtAM, first.am)
        replacement = identity("identity", first.session)
        sheet.identities = [
            x for x in sheet.identities if x.id not in keys and x.id != am.installed_identity
        ]
        sheet.identities.append(
            IdentityState(
                id=replacement, name=am.role, marked=bool(am.marked_event), slot=selected[0].slot
            )
        )
        put(
            state,
            am.model_copy(update=dict(installed_identity=replacement, state_event=first.event)),
        )
        sheet.revision += 1
    for value in values:
        put(state, value)


def extract(state: GameState, value: Extraction) -> None:
    extract_many(state, (value,))


def can_recall(state: GameState, actor: ActorRef, memory: str, *, learned_revision: int) -> bool:
    normalized = " ".join(memory.split()).casefold()
    return not any(
        x.target == actor
        and not x.restored_event
        and learned_revision <= x.through_revision
        and normalized in {" ".join(y.split()).casefold() for y in x.memories}
        for x in records(state, Extraction)
    )


def modifier(state: GameState, action: str, target: ActorRef) -> int:
    return sum(
        x.amount
        for x in records(state, Mark)
        if x.kind == "modifier"
        and x.roll == action
        and x.counterpart == target
        and not x.applied_event
    )
