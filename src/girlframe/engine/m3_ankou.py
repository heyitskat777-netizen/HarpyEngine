"""Original Ankou sources and lifetimes; benefits never replace actual Bond authority."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

FRAME = "PROJECT ANKOU"
PREFIX = "frame.ankou."
RELAY, FIGHT, OBSESSIVE, PROCESSOR, QUICKCHANGE, PULSE, STALKER = (
    PREFIX + x
    for x in (
        "emotional-relay",
        "fight-fawn-procedure",
        "obsessive",
        "processor-core",
        "quickchange-implant",
        "amygdala-pulse",
        "stalker",
    )
)
REQUISITIONS = (FIGHT, OBSESSIVE, PROCESSOR, QUICKCHANGE, PULSE, STALKER)
PLAY = "ankou_processor"
BENEFITS = ("emotion", "speech", "interrupt", "touch", "sense")
PROCESSOR_BENEFITS = ("identity", "champion", "eyes", "will")
SYMPTOMS = (
    "Auditory hallucinations",
    "Vomiting and nausea",
    "Seizures",
    "Crippling migraines and headaches",
    "Blindness or extreme light sensitivity",
    "Extreme paranoia and anxiety",
)


class Relay(Model):
    id: str
    actor: ActorRef
    frame: str
    cast: SceneCast
    handler: ActorRef
    handler_controller: int
    benefits: tuple[str, ...]
    event: str
    consequence: Literal["death", "nominees", "feedback"] | None = None
    consequence_event: str | None = None
    completed_event: str | None = None
    ended_event: str | None = None


class Proposal(Model):
    id: str
    actor: ActorRef
    frame: str
    cast: SceneCast
    handler: ActorRef
    handler_controller: int
    minds: tuple[ActorRef, ...]
    positions: dict[str, str]
    exempt_cadre: bool
    exempt: ActorRef | None
    account: str
    event: str
    action: str | None = None
    bound_event: str | None = None


class Processor(Model):
    id: str
    actor: ActorRef
    frame: str
    cast: SceneCast
    handler: ActorRef
    handler_controller: int
    registry: str
    minds: tuple[ActorRef, ...]
    positions: dict[str, str]
    event: str
    roll_event: str
    total: int
    benefits: tuple[str, ...] = ()
    symptoms: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    selected_event: str | None = None
    symptoms_event: str | None = None
    unlink_in_battle: bool | None = None
    unlinked_event: str | None = None
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Task(Model):
    id: str
    source: str
    actor: ActorRef
    controller: int
    kind: Literal[
        "emotion",
        "fight_fawn",
        "nominate",
        "perform",
        "death_identity",
        "missed_obsession",
        "interrupt",
        "disclosure",
        "spy_context",
        "company",
    ]
    cast: SceneCast
    event: str
    target: ActorRef | None = None
    source_action: str | None = None
    source_asset: str | None = None
    source_tag: str | None = None
    selected_event: str | None = None
    options: tuple[str, ...] = ()
    account: str = ""
    choice: str | None = None
    child: str | None = None
    request: str | None = None
    completed_event: str | None = None


class FightFawn(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    task: str
    play: Literal["all_out_assault", "flirt"]
    event: str
    used_action: str | None = None
    used_event: str | None = None


class Obsession(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    frame: str
    event: str
    sequence: str | None = None
    ended_event: str | None = None
    replacement_event: str | None = None


class Company(Model):
    id: str
    actor: ActorRef
    companions: tuple[ActorRef, ...]
    positions: dict[str, str]
    author: int
    account: str
    event: str
    request: str


class Encounter(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    kind: Literal["touch", "spy", "seen"]
    cast: SceneCast
    actor_position: str
    target_position: str
    author: int
    account: str
    event: str
    period: str | None = None
    thinks_private: bool = False
    request: str | None = None


class TagUse(Model):
    id: str
    source: str
    actor: ActorRef
    target: ActorRef
    tag: str
    scene: str
    event: str
    kind: Literal["emotion", "obsession", "spy", "symptom", "champion", "pulse"]
    ended_event: str | None = None


class Touch(Model):
    id: str
    relay: str
    encounter: str
    actor: ActorRef
    target: ActorRef
    asset: str
    frame: str | None = None
    event: str
    work: tuple[str, ...] = ()
    completed_event: str | None = None


class Delivery(Model):
    id: str
    source: str
    author: ActorRef
    target: ActorRef
    author_controller: int
    target_controller: int
    account: str
    event: str
    saved_event: str | None = None


class FeedbackSequence(Model):
    id: str
    actor: ActorRef
    cast: SceneCast | None
    source: str
    event: str
    count: Literal[1, 5]
    venue: SceneCast | None = None
    activated_event: str | None = None
    reason: Literal["relay", "obsession"]
    steps: tuple[str, ...] = ()
    completed_event: str | None = None
    terminal_event: str | None = None


class FeedbackStep(Model):
    id: str
    sequence: str
    actor: ActorRef
    cast: SceneCast
    event: str
    ordinal: int
    phase: Literal["choice", "purpose", "identity", "child", "complete", "ended"] = "choice"
    choice: Literal["bond", "purpose", "tear", "die"] | None = None
    target: ActorRef | None = None
    target_controller: int | None = None
    account: str = ""
    purpose: str | None = None
    purpose_event: str | None = None
    asset: str | None = None
    opponent: ActorRef | None = None
    no_opponent: bool = False
    child: str | None = None
    child_event: str | None = None
    choice_event: str | None = None
    completed_event: str | None = None
    work: tuple[str, ...] = ()


class Quickchange(Model):
    id: str
    actor: ActorRef
    period: str
    source_person: ActorRef | None
    source_identity: str | None
    source_tag: str | None
    erased: str | None
    written: str | None
    label: str | None
    event: str


KINDS = {
    Proposal: "ankou_proposal",
    Relay: "ankou_relay",
    Processor: "ankou_processor",
    Task: "ankou_task",
    FightFawn: "ankou_fight_fawn",
    Obsession: "ankou_obsession",
    Company: "ankou_company",
    Encounter: "ankou_encounter",
    TagUse: "ankou_tag_use",
    Touch: "ankou_touch",
    Delivery: "ankou_delivery",
    FeedbackSequence: "ankou_feedback_sequence",
    FeedbackStep: "ankou_feedback_step",
    Quickchange: "ankou_quickchange",
}


def identity(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:ankou:" + ":".join(parts)))


def records[T: Model](state: GameState, cls: type[T]) -> tuple[T, ...]:
    return tuple(
        cls.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[cls]
    )


def get[T: Model](state: GameState, cls: type[T], key: str) -> T:
    value = next((x for x in records(state, cls) if x.model_dump()["id"] == key), None)
    if value is None:
        raise ValueError("Recover this actual original Ankou source")
    return value


def put(state: GameState, value: Model) -> None:
    kind = KINDS[type(value)]
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == kind and x.get("id") == value.model_dump()["id"])
    ]
    state.facts.append(dict(kind=kind, id=value.model_dump()["id"], body=value.model_dump_json()))


def frame(state: GameState, actor: ActorRef) -> str:
    from girlframe.engine.m3_nightmare import current

    sheet, original = current(state, actor)
    if sheet.frame != FRAME or sheet.frame_scrapped:
        raise ValueError("Use the actual original current Ankou Frame")
    return original


def held(state: GameState, actor: ActorRef, rule: str) -> tuple[FrameRuleReceipt, ...]:
    from girlframe.engine.m3_privileges import suspended

    original = frame(state, actor)
    return tuple(
        x
        for x in state.requisitions
        if isinstance(x, FrameRuleReceipt)
        and x.actor == actor
        and x.frame_instance == original
        and x.donor_frame == FRAME
        and x.rule_id == rule
        and not suspended(state, x.id)
    )


def effective_intense(state: GameState, first: ActorRef, second: ActorRef) -> bool:
    """Directional benefit only; never a Bond operation or acquisition trigger."""
    if depth(state, first, second) == 2:
        return True
    values = [
        x
        for x in records(state, Obsession)
        if x.actor == first and x.target == second and not x.ended_event
    ]
    if not values:
        return False
    try:
        original = frame(state, first)
    except ValueError:
        return False
    return bool(held(state, first, OBSESSIVE)) and any(x.frame == original for x in values)


def active_relays(state: GameState, actor: ActorRef | None = None) -> tuple[Relay, ...]:
    return tuple(
        x
        for x in records(state, Relay)
        if not x.ended_event and (actor is None or x.actor == actor)
    )


def pending_feedback(state: GameState, actor: ActorRef | None = None) -> tuple[FeedbackStep, ...]:
    return tuple(
        x
        for x in records(state, FeedbackStep)
        if x.phase not in ("complete", "ended") and (actor is None or x.actor == actor)
    )


def helpless(state: GameState, actor: ActorRef, foe: ActorRef | None = None) -> bool:
    return any(
        x.get("kind") == "ankou_death_helpless"
        and not x.get("recovery_event")
        and ActorRef.model_validate_json(x["actor"]) == actor
        for x in state.facts
    )


def clear_unqualified_helpless(state: GameState, actor: ActorRef, event: str) -> bool:
    """Only actual general recovery clears this source; preserve all other causes."""
    changed = False
    for index, fact in enumerate(state.facts):
        if (
            fact.get("kind") == "ankou_death_helpless"
            and not fact.get("recovery_event")
            and ActorRef.model_validate_json(fact["actor"]) == actor
        ):
            if not event:
                raise ValueError("Use the actual recovery source event")
            state.facts[index] = fact | dict(recovery_event=event)
            changed = True
    return changed
