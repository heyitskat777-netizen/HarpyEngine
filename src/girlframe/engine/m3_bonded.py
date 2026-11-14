"""Original-person Bonded sources and narrowly scoped printed effects."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

PAIR = "girl.bonded.bonded-pair"
SIDE = "girl.bonded.always-by-her-side"
INTIMACY = "girl.bonded.workplace-inappropriate-intimacy"
SEX = "girl.bonded.sex-play"
RULES = (PAIR, SIDE, INTIMACY, SEX)
SIDE_PLAY = "bonded_side"
SEX_PLAY = "bonded_sex"


def paired_conversion_legal(
    state: GameState, owner: ActorRef, paired_id: str, label: str, *, duplicate_labels: bool
) -> bool:
    """Validate the real slot; the service must prove the actual marking Pair."""
    from girlframe.engine.m3_leviathan_obsession import require_identity_change, require_unlocked

    sheet = state.sheets.get(owner.entity) if owner.kind == "pilot" else None
    if sheet is None or sheet.character_id != owner.incarnation:
        return False
    paired = next((x for x in sheet.identities if x.id == paired_id and x.paired), None)
    if paired is None or not label.strip():
        return False
    try:
        require_unlocked((paired,), (paired.id,))
        require_identity_change(state, owner, (paired.id,))
    except ValueError:
        return False
    return duplicate_labels or not any(
        x.id != paired.id and x.name.casefold() == label.casefold() for x in sheet.identities
    )


def convert_paired_tag(
    state: GameState, owner: ActorRef, paired_id: str, tag_id: str, *, duplicate_labels: bool
) -> str:
    """Consume the exact marked Tag; the proved caller completes real Tag obligations."""
    sheet = state.sheets.get(owner.entity) if owner.kind == "pilot" else None
    tag = next((x for x in sheet.tags if x.id == tag_id), None) if sheet else None
    if (
        tag is None
        or not tag.marked
        or tag.rejection_pending
        or not paired_conversion_legal(
            state, owner, paired_id, tag.label, duplicate_labels=duplicate_labels
        )
    ):
        raise ValueError("Preserve the actual marked Tag, protected Paired slot and source locks")
    assert sheet is not None
    paired = next(x for x in sheet.identities if x.id == paired_id and x.paired)
    paired.name = tag.label
    paired.marked = paired.id in sheet.sedation_locked
    sheet.tags = [x for x in sheet.tags if x.id != tag.id]
    sheet.revision += 1
    return tag.id


class Source(Model):
    learned_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    consent_event: str | None = Field(default=None, exclude_if=lambda value: value is None)
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str
    kind: Literal["side", "intimacy", "sex"]
    actor: ActorRef
    pair: ActorRef
    target: ActorRef | None = None
    observer: ActorRef | None = None
    controllers: dict[str, int]
    vessels: dict[str, str]
    cast: SceneCast
    registry: str
    pair_source: str
    apart: bool = Field(default=False, exclude_if=lambda value: not value)
    event: str
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal[
        "invited", "accepted", "declined", "bound", "results", "child", "complete", "withdrawn"
    ]
    route: Literal["pair", "seven", "delegated"] = "pair"
    delegated_rule: str | None = None
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    completed_event: str | None = None

    @property
    def proposed_event(self) -> str:
        return self.event

    @property
    def counterpart(self) -> int:
        if self.target is None:
            raise ValueError("This source has no intimacy counterpart")
        return self.controllers[self.target.token]

    @property
    def bonded_source(self) -> None:
        return None


class Consent(Model):
    id: str
    source: str
    person: ActorRef
    controller: int
    accepted: bool
    event: str
    account: str


class Activation(Model):
    id: str
    source: str
    actor: ActorRef
    event: str
    account: str


class NoRollManMark(Model):
    """The actual Man's optional partner-Tag mark, without a fabricated roll."""

    id: str
    source: str
    actor: ActorRef
    partner: ActorRef
    designation: str
    tag: str
    label: str
    event: str
    scene: str
    already_marked: bool = Field(default=False, exclude_if=lambda value: not value)


class ManTagResolution(Model):
    id: str
    source: str
    mark: str
    partner: ActorRef
    controller: int
    tag: str
    event: str


class ManTagDecision(Model):
    id: str
    work: str
    partner: ActorRef
    controller: int
    decision: Literal["embrace", "reject"]
    identity: str | None = None
    replacement: str | None = None
    event: str


class ManTagRejection(Model):
    id: str
    work: str
    partner: ActorRef
    controller: int
    account: str = Field(min_length=1, max_length=1200)
    event: str


class ManPairedWork(Model):
    id: str
    source: str
    mark: str
    owner: ActorRef
    marker: ActorRef
    controller: int
    relation: str
    paired: str
    slot: int | None
    tag: str
    event: str


class ManPairedDecision(Model):
    id: str
    work: str
    marker: ActorRef
    controller: int
    convert: bool
    event: str


class Selection(Model):
    id: str
    source: str
    action: str | None
    person: ActorRef
    controller: int
    kind: str
    options: tuple[str, ...]
    identities: tuple[str, ...] = ()
    request: str | None = None
    text: str
    event: str


class PairHelp(Model):
    id: str
    source: str
    actor: ActorRef
    pair: ActorRef
    controller: int
    event: str
    account: str


class Child(Model):
    id: str
    source: str
    actor: ActorRef
    target: ActorRef
    parent: str | None
    play: str
    account: str
    event: str
    child: str | None = None
    bound_event: str | None = None
    completed_event: str | None = None
    total: int | None = None


class Silence(Model):
    id: str
    source: str
    child: str
    actor: ActorRef
    pair: ActorRef
    observer: ActorRef
    observation: str
    event: str


class Detail(Model):
    """Actual addressed secret, changed appearance, Tag request or source-authorized Order."""

    id: str
    source: str
    kind: Literal["secret", "appearance", "order"]
    actor: ActorRef
    target: ActorRef
    controller: int
    account: str
    event: str
    order: str | None = None


class Delegation(Model):
    id: str
    source: str
    session: str
    rule: str
    actor: ActorRef
    target: ActorRef
    event: str
    completed_event: str | None = None
    action: str | None = None


class DelegationRelease(Model):
    id: str
    source: str
    session: str
    actor: ActorRef
    controller: int
    outcome: Literal["declined", "withdrawn"]
    event: str


class OrderBinding(Model):
    id: str
    detail: str
    source: str
    actor: ActorRef
    target: ActorRef
    order: str
    event: str


KINDS: dict[type[Model], str] = {
    Source: "bonded_source",
    DelegationRelease: "bonded_delegation_release",
    Consent: "bonded_consent",
    Activation: "bonded_activation",
    NoRollManMark: "bonded_no_roll_man_mark",
    ManTagResolution: "bonded_man_tag_resolution",
    ManTagDecision: "bonded_man_tag_decision",
    ManTagRejection: "bonded_man_tag_rejection",
    ManPairedWork: "bonded_man_paired_work",
    ManPairedDecision: "bonded_man_paired_decision",
    Selection: "bonded_selection",
    PairHelp: "bonded_pair_help",
    Child: "bonded_child",
    Silence: "bonded_silence",
    Detail: "bonded_detail",
    OrderBinding: "bonded_order_binding",
    Delegation: "bonded_delegation",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], str(value.model_dump()["id"])
    if not isinstance(value, (Source, Child, Delegation)) and any(
        x.get("kind") == kind and x.get("id") == identity for x in state.facts
    ):
        raise ValueError("Preserve the original person's immutable Bonded response")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def get(state: GameState, identity: str) -> Source:
    value = next((x for x in records(state, Source) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the genuine original Bonded source")
    return value


def pair(state: GameState, actor: ActorRef) -> ActorRef:
    sheet = state.sheets.get(actor.entity)
    if actor.kind != "pilot" or sheet is None or sheet.character_id != actor.incarnation:
        raise ValueError("Use the original current Bonded Girl")
    setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
    actual = setup.pair if setup else None
    if actual is None:
        saved = [x.pair for x in records(state, Source) if x.actor == actor]
        if not saved or len(set(saved)) != 1:
            raise ValueError("SOURCE_PAIR_REQUIRED: prove the original accepted creation Bond")
        actual = saved[0]
    other = state.sheets.get(actual.entity)
    if actual.kind != "pilot" or other is None or other.character_id != actual.incarnation:
        raise ValueError("SOURCE_PAIR_REQUIRED: the original Pair cannot alias a replacement")
    if actual == actor:
        raise ValueError("The Pair is a distinct actual person")
    return actual


def helpless(state: GameState, actor: ActorRef) -> bool:
    return any(
        x.actor == actor
        and x.kind == "side"
        and x.tier == "low"
        and x.effect_event is not None
        and not any(
            y.source == x.id and y.actor == actor and y.pair == x.pair
            for y in records(state, PairHelp)
        )
        for x in records(state, Source)
    )


def can_disclose(state: GameState, speaker: ActorRef, observation: str) -> bool:
    return not any(
        x.observer == speaker and x.observation == observation for x in records(state, Silence)
    )


def appearance(state: GameState, actor: ActorRef) -> str | None:
    value = next(
        (
            x
            for x in reversed(records(state, Detail))
            if x.kind == "appearance" and x.target == actor
        ),
        None,
    )
    if value is None:
        return None
    placement = next((x for x in state.placements if x.actor == actor), None)
    source = get(state, value.source)
    return (
        value.account
        if placement is not None and placement.vessel_id == source.vessels.get(actor.token)
        else None
    )
