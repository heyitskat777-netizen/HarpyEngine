"""Original Vatgrown Investors, source learning and explicit rule evidence."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

EXPERIMENT = "girl.vatgrown.just-an-experiment"
INVESTMENT = "girl.vatgrown.prime-investment"
SEX = "girl.vatgrown.sex-play"
PLAY = "vatgrown_sex"
EFFECTS = ("identity", "play", "plans", "good")
BRUTALIZE = "girl.alpha.brutalize"


class Session(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    registry: str
    actor_vessel: str
    target_vessel: str
    proposed_event: str
    proposal: str
    consent_event: str | None = None
    consent_account: str = ""
    phase: str = "invited"
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    learning_event: str | None = None
    question: str = ""
    question_event: str | None = None
    answer: str = ""
    answer_event: str | None = None
    liked: bool | None = None
    dislike_event: str | None = None
    discipline: str | None = None
    departed_event: str | None = None
    completed_event: str | None = None


class Selection(Model):
    id: str
    session: str
    action: str
    controller: int
    choice: str
    options: tuple[str, ...]
    fields: dict[str, str]
    account: str
    event: str


class IdentityCopy(Model):
    id: str
    actor: ActorRef
    teacher: ActorRef
    session: str
    selection: str
    original: str | None
    text: str
    replaced: str | None
    event: str


class LearnedPlay(Model):
    id: str
    actor: ActorRef
    teacher: ActorRef
    session: str
    rule_id: str
    event: str


class SideCondition(Model):
    id: str
    session: str
    actor: ActorRef
    counterpart: ActorRef
    event: str
    released_event: str | None = None
    departure: str | None = None
    leaving_action: str | None = None
    left_event: str | None = None


class Investor(Model):
    id: str
    owner: ActorRef
    actor: ActorRef
    controller: int
    event: str
    source: Literal["creation", "transition", "added"]
    desires: tuple[str, ...]
    quote: int | None = None
    quote_event: str | None = None
    added_event: str | None = None
    changes: tuple[str, ...] = ()


class Investment(Model):
    id: str
    owner: ActorRef
    period: str
    source_action: str
    roll_event: str
    total: int
    event: str
    investor: str | None = None
    actor: ActorRef | None = None
    controller: int | None = None
    kind: str = "prime_low"
    phase: str = "select"
    scene_event: str | None = None
    scene_completed: str | None = None
    roles: tuple[ActorRef, ...] = ()
    good: bool | None = None
    judgment_event: str | None = None
    desire: str | None = None
    desire_event: str | None = None
    performance_action: str | None = None
    performance_bound_event: str | None = None
    performance_record_event: str | None = None
    performance_event: str | None = None
    completed_event: str | None = None


class RequisitionOffer(Model):
    id: str
    actor: ActorRef
    investor: ActorRef
    investment: str
    kind: str
    event: str


class Favour(Model):
    id: str
    investment: str
    actor: ActorRef
    investor: ActorRef
    controller: int
    kind: Literal["answer"] = "answer"
    question: str
    event: str
    answer: str = ""
    answer_event: str | None = None
    backed_down: bool | None = None
    resolution_event: str | None = None
    tag_event: str | None = None


class Violation(Model):
    id: str
    actor: ActorRef
    counterpart: ActorRef | None = None
    kind: str
    source: str
    author: int
    event: str
    account: str
    witnesses: tuple[ActorRef, ...] = ()
    performed_event: str | None = None
    disclosed_event: str | None = None
    disclosed_handler: ActorRef | None = None
    judgment_event: str | None = None
    discipline: str | None = None


class Discipline(Model):
    id: str
    actor: ActorRef
    chooser: ActorRef
    controller: int
    event: str
    source: str
    case: str
    completed_event: str | None = None


KINDS: dict[type[Model], str] = {
    Session: "vatgrown_sex_session",
    Selection: "vatgrown_selection",
    IdentityCopy: "vatgrown_identity_copy",
    LearnedPlay: "vatgrown_learned_play",
    SideCondition: "vatgrown_side",
    Investor: "vatgrown_investor",
    Investment: "vatgrown_investment",
    RequisitionOffer: "vatgrown_requisition_offer",
    Favour: "vatgrown_favour",
    Violation: "vatgrown_violation",
    Discipline: "vatgrown_discipline",
}
IMMUTABLE = (Selection, IdentityCopy, LearnedPlay, RequisitionOffer)


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def find[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise ValueError("Recover the actual original Vatgrown source")
    return value


def get(state: GameState, identity: str) -> Session:
    return find(state, Session, identity)


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    if isinstance(value, IMMUTABLE) and any(
        x.get("kind") == kind and x.get("id") == identity for x in state.facts
    ):
        raise ValueError("Preserve this immutable actual Vatgrown effect")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def identity(kind: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:vatgrown:" + kind + ":" + ":".join(parts)))
