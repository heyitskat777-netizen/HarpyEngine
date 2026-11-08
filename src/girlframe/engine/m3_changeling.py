"""Source-bound Changeling brains, consumed Strings and original authored consequences."""

from typing import Literal, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

FRAME = "CHANGELING"
BASE = "frame.changeling."
BLANK, STRINGS, FINGERS = (
    BASE + x for x in ("blank-slate", "psych-strings", "fingers-in-the-brain")
)
WEB, MINDFUCK, RECONDITION, CLAY, WHIP = (
    BASE + x
    for x in ("web-implant", "mindfuck", "live-reconditioning-module", "body-of-clay", "psych-whip")
)
REQUISITIONS = (WEB, MINDFUCK, RECONDITION, CLAY, WHIP)
PLAYS = {"changeling_blank_slate": BLANK, "changeling_body_of_clay": CLAY}
FACETS = ("features", "age", "body", "sex", "voice")
FACET_LABELS = {
    "features": "Facial features and hair",
    "age": "Apparent age",
    "body": "Body type",
    "sex": "Sex characteristics",
    "voice": "Voice",
}
TAGS = ("Masochistic", "Obedient", "Pet")
type FingerKind = Literal[
    "pause", "sight", "interrupt", "question", "flirt_plus", "flirt_minus", "sex", "fry", "damage"
]
type Phase = Literal[
    "main", "effect", "answer", "counter", "erasure", "damage", "fry", "sex", "complete"
]


class BrainRef(Model):
    id: str
    actor: ActorRef
    vessel: str
    kind: Literal["girl", "gorgon", "harpy", "handler", "human_npc", "other"]
    controller: int
    source: str


class Speech(Model):
    id: str
    actor: ActorRef
    addressed: ActorRef
    brain: BrainRef
    addressed_brain: BrainRef
    kind: Literal["definition", "conversation", "push"]
    controller: int
    cast: SceneCast
    text: str
    event: str
    session: str | None = None
    used_by: str | None = None


class StartingBond(Model):
    id: str
    actor: ActorRef
    frame: str
    subject: ActorRef
    source: str
    event: str
    node: str | None = None
    attached_event: str | None = None


class String(Model):
    id: str
    actor: ActorRef
    frame: str
    subject: BrainRef
    origin: Literal["start", "deepen", "web", "assault"]
    source: str
    event: str
    spent_by: str | None = None
    spent_event: str | None = None


class Deepening(Model):
    id: str
    first: ActorRef
    second: ActorRef
    before: int
    after: int
    source: str
    event: str


class Session(Model):
    id: str
    actor: ActorRef
    brain: BrainRef
    frame: str
    play: Literal["changeling_blank_slate", "changeling_body_of_clay"]
    target: ActorRef | None
    target_brain: BrainRef | None
    handler: ActorRef
    handler_controller: int
    cast: SceneCast
    total: int
    roll_event: str
    event: str
    speech: str | None = None
    identities: tuple[str, ...] = ()
    erased_event: str | None = None
    blank: str | None = None
    recent_event: str | None = None
    owner_change_event: str | None = None
    handler_change_event: str | None = None
    taste_event: str | None = None
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class BlankSlate(Model):
    id: str
    session: str
    actor: ActorRef
    brain: BrainRef
    identity: str
    event: str
    conversation: tuple[str, str] | None = None
    copied_from: ActorRef | None = None
    copied_identity: str | None = None
    replacement: str | None = None
    replaced_event: str | None = None
    work: tuple[str, ...] = ()


class Push(Model):
    id: str
    session: str
    actor: ActorRef
    target: ActorRef
    speech: str
    label: str
    event: str
    work: tuple[str, ...] = ()


class Fingers(Model):
    id: str
    actor: ActorRef
    brain: BrainRef
    frame: str
    target: ActorRef
    subject: BrainRef
    node: str
    kind: FingerKind
    cast: SceneCast
    handler: ActorRef
    handler_controller: int
    controllers: dict[str, int]
    event: str
    account: str
    phase: Phase = "main"
    incoming: str | None = None
    subject_scene: str | None = None
    question: str | None = None
    counter: Literal["question", "erase", "tag", "pass"] | None = None
    counter_question: str | None = None
    counter_event: str | None = None
    counter_closed_event: str | None = None
    counter_unavailable_reason: Literal["not_eligible", "subject_ended"] | None = None
    counter_erase: str | None = None
    counter_tag: str | None = None
    main_event: str | None = None
    action: str | None = None
    consent_event: str | None = None
    sex_event: str | None = None
    sex_outcome: Literal["performed", "declined"] | None = None
    completed_event: str | None = None
    work: tuple[str, ...] = ()


class Question(Model):
    id: str
    source: str
    asker: ActorRef
    answerer: BrainRef
    asker_controller: int
    question: str
    event: str
    answer: str | None = None
    answer_event: str | None = None


class FlirtGrant(Model):
    id: str
    use: str
    actor: ActorRef
    sign: Literal[-1, 1]
    event: str
    action: str | None = None
    rolled_event: str | None = None


class Access(Model):
    id: str
    actor: ActorRef
    frame: str
    subject: BrainRef
    handler: ActorRef
    handler_controller: int
    cast: SceneCast
    condition: Literal["unconscious", "helpless", "unexpecting"]
    facts: str
    account: str
    event: str
    used_event: str | None = None


class Reconditioning(Model):
    id: str
    actor: ActorRef
    frame: str
    subject: BrainRef
    asset: str
    source: str
    source_event: str
    cast: SceneCast
    controller: int
    event: str
    label: str | None = None
    completed_event: str | None = None


class AssaultGift(Model):
    id: str
    actor: ActorRef
    frame: str
    subject: BrainRef
    action: str
    roll_event: str
    event: str
    chosen: bool | None = None
    completed_event: str | None = None


class FacetChange(Model):
    id: str
    session: str
    actor: ActorRef
    brain: BrainRef
    frame: str
    author: ActorRef
    controller: int
    values: dict[str, str]
    event: str
    copied_from: ActorRef | None = None
    copied_source: str | None = None


class IdentityDisclosure(Model):
    id: str
    actor: ActorRef
    addressed: ActorRef
    identity: str
    label: str
    controller: int
    cast: SceneCast
    speech: str
    event: str


class BodyFact(Model):
    reset_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    reset_record: str | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str
    actor: ActorRef
    vessel: str
    brain: str
    kind: Literal["girl", "gorgon", "harpy", "handler", "human_npc", "other"]
    author: ActorRef
    controller: int
    cast: SceneCast
    account: str
    event: str


class Appearance(Model):
    id: str
    actor: ActorRef
    vessel: str
    values: dict[str, str]
    author: ActorRef
    controller: int
    cast: SceneCast
    event: str


class AppearanceDisclosure(Model):
    id: str
    appearance: str
    values: dict[str, str]
    actor: ActorRef
    addressed: ActorRef
    controller: int
    cast: SceneCast
    event: str


class PauseOpportunity(Model):
    id: str
    use: str
    actor: ActorRef
    subject: BrainRef
    cast: SceneCast
    event: str
    action: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None


class EyeView(Model):
    id: str
    use: str
    actor: ActorRef
    subject: BrainRef
    cast: SceneCast
    event: str
    ended_event: str | None = None


class EyeObservation(Model):
    id: str
    view: str
    subject: BrainRef
    controller: int
    scene: str
    cell: tuple[int, int]
    text: str
    event: str


class Interruption(Model):
    id: str
    use: str
    incoming: str
    actor: ActorRef
    original_play: str
    receipt: str | None
    cast: SceneCast
    choice: str
    event: str
    child: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None


class RecentLoss(Model):
    id: str
    session: str
    actor: ActorRef
    brain: BrainRef
    start_event: str
    through_event: str
    start_revision: int
    through_revision: int
    events: tuple[str, ...]
    handler: ActorRef
    controller: int
    account: str
    event: str


class ForcedDamage(Model):
    id: str
    use: str
    target: ActorRef
    asset: str
    controller: int
    event: str
    work: tuple[str, ...] = ()


class FryOutcome(Model):
    id: str
    use: str
    subject: BrainRef
    handler: ActorRef
    controller: int
    outcome: Literal["helpless", "dead"]
    event: str


KINDS: dict[type[Model], str] = {
    BrainRef: "changeling_brain",
    Speech: "changeling_speech",
    StartingBond: "changeling_start",
    String: "changeling_string",
    Deepening: "changeling_deepen",
    Session: "changeling_session",
    BlankSlate: "changeling_blank",
    Push: "changeling_push",
    Fingers: "changeling_fingers",
    Question: "changeling_question",
    FlirtGrant: "changeling_flirt",
    Access: "changeling_access",
    Reconditioning: "changeling_reconditioning",
    AssaultGift: "changeling_assault_gift",
    FacetChange: "changeling_facets",
    IdentityDisclosure: "changeling_identity_disclosure",
    BodyFact: "changeling_body_fact",
    Appearance: "changeling_appearance",
    AppearanceDisclosure: "changeling_appearance_disclosure",
    PauseOpportunity: "changeling_pause",
    EyeView: "changeling_eyes",
    EyeObservation: "changeling_eye_observation",
    Interruption: "changeling_interruption",
    RecentLoss: "changeling_recent_loss",
    ForcedDamage: "changeling_forced_damage",
    FryOutcome: "changeling_fry",
}
type Source = (
    BrainRef
    | Speech
    | StartingBond
    | String
    | Deepening
    | Session
    | BlankSlate
    | Push
    | Fingers
    | Question
    | FlirtGrant
    | Access
    | Reconditioning
    | AssaultGift
    | FacetChange
    | IdentityDisclosure
    | BodyFact
    | Appearance
    | AppearanceDisclosure
    | PauseOpportunity
    | EyeView
    | EyeObservation
    | Interruption
    | RecentLoss
    | ForcedDamage
    | FryOutcome
)


def identity(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:changeling:" + kind + ":" + ":".join(parts)))


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(item["body"])
        for item in state.facts
        if item.get("kind") == KINDS[model]
    )


def all_records(state: GameState) -> tuple[Source, ...]:
    return tuple(
        cast(Source, model.model_validate_json(item["body"]))
        for model, kind in KINDS.items()
        for item in state.facts
        if item.get("kind") == kind
    )


def put(state: GameState, value: Source) -> None:
    kind = KINDS[type(value)]
    state.facts = [
        item
        for item in state.facts
        if not (item.get("kind") == kind and item.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def record[T: Model](state: GameState, model: type[T], key: str) -> T:
    found = next(
        (value for value in records(state, model) if value.model_dump()["id"] == key), None
    )
    if found is None:
        raise ValueError("Recover the actual original Changeling source")
    return found


def session(state: GameState, identity: str) -> Session:
    return record(state, Session, identity)


def get(state: GameState, identity: str) -> Fingers:
    return record(state, Fingers, identity)


def frame(state: GameState, actor: ActorRef) -> str:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame != FRAME
        or sheet.frame_scrapped
    ):
        raise ValueError("Use the actual original living Changeling and her actual assigned Frame")
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)


def held(state: GameState, actor: ActorRef, rule: str) -> FrameRuleReceipt | None:
    original = frame(state, actor)
    return next(
        (
            item
            for item in state.requisitions
            if isinstance(item, FrameRuleReceipt)
            and item.actor == actor
            and item.frame_instance == original
            and item.donor_frame == FRAME
            and item.rule_id == rule
            and not suspended(state, item.id)
        ),
        None,
    )


def same_brain(first: BrainRef, second: BrainRef) -> bool:
    return (first.id, first.actor, first.vessel) == (second.id, second.actor, second.vessel)


def strings(state: GameState, actor: ActorRef, brain: BrainRef) -> tuple[String, ...]:
    return tuple(
        item
        for item in records(state, String)
        if item.actor == actor and same_brain(item.subject, brain) and item.spent_event is None
    )


def consume(state: GameState, node: str, use: str, event: str) -> String:
    actual = record(state, String, node)
    if actual.spent_event is not None:
        raise ValueError("Use each actual original Psych String only once")
    put(state, actual.model_copy(update=dict(spent_by=use, spent_event=event)))
    return actual


def reciprocal(subject: BrainRef) -> bool:
    return subject.kind in ("girl", "gorgon", "harpy", "handler")


def unanswered(state: GameState, actor: ActorRef) -> tuple[Question, ...]:
    return tuple(
        value
        for value in records(state, Question)
        if value.answerer.actor == actor and value.answer_event is None
    )


def pending_flirt(state: GameState, actor: ActorRef) -> tuple[FlirtGrant, ...]:
    return tuple(
        value
        for value in records(state, FlirtGrant)
        if value.actor == actor and value.rolled_event is None
    )


def can_recall(state: GameState, actor: ActorRef, learned_revision: int) -> bool:
    """Current structured fictional knowledge only; OOC records and owed choices are retained."""
    return not any(
        value.actor == actor and value.start_revision <= learned_revision <= value.through_revision
        for value in records(state, RecentLoss)
    )
