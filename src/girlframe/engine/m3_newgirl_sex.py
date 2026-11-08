"""Real original-person intimacy and independently owned Newgirl outcomes."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.newgirl.sex-play"
PLAY = "newgirl_sex"


class Session(Model):
    id: str
    actor: ActorRef
    partners: tuple[ActorRef, ...]
    controllers: dict[str, int]
    vessels: dict[str, str]
    cast: SceneCast
    registry: str
    mentors_before: tuple[ActorRef, ...]
    mentor_source: str
    proposed_event: str
    proposal: str
    phase: Literal["invited", "accepted", "declined", "bound", "results", "damage", "complete"] = (
        "invited"
    )
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    completed_event: str | None = None


class Consent(Model):
    id: str
    session: str
    person: ActorRef
    controller: int
    accepted: bool
    account: str
    event: str


class Selection(Model):
    id: str
    session: str
    action: str
    partner: ActorRef
    controller: int
    kind: str
    options: tuple[str, ...]
    text: str
    asset: str | None
    tag: str | None
    work: tuple[str, ...]
    event: str


class Discovery(Model):
    id: str
    session: str
    mentor: ActorRef
    actor: ActorRef
    observer: ActorRef
    controller: int
    cast: SceneCast
    basis: Literal["witness", "disclosure"]
    account: str
    event: str
    learned_event: str | None = None
    learned_account: str = ""
    tag: str | None = None
    tag_event: str | None = None
    tag_label: str = ""


KINDS = {
    Session: "newgirl_sex_session",
    Consent: "newgirl_sex_consent",
    Selection: "newgirl_sex_selection",
    Discovery: "newgirl_sex_discovery",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"])
        for x in getattr(state, "facts", [])
        if x.get("kind") == KINDS[model]
    )


def get(state: GameState, identity: str) -> Session:
    value = next((x for x in records(state, Session) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the original genuine Newgirl intimacy source")
    return value


def put(state: GameState, value: Session | Consent | Selection | Discovery) -> None:
    kind = KINDS[type(value)]
    facts = state.facts
    if isinstance(value, (Consent, Selection)) and any(
        x.get("kind") == kind and x.get("id") == value.id for x in facts
    ):
        raise ValueError("Preserve the actual original human response")
    state.facts = [x for x in facts if not (x.get("kind") == kind and x.get("id") == value.id)] + [
        dict(kind=kind, id=value.id, body=value.model_dump_json())
    ]


def choices(state: GameState, value: Session) -> tuple[Selection, ...]:
    return tuple(x for x in records(state, Selection) if x.session == value.id)


def assigned(state: GameState, value: Session) -> tuple[ActorRef, ...]:
    if len(value.partners) > 1:
        return value.partners
    partner = value.partners[0]
    selected = choices(state, value)
    return (
        (partner,)
        if any(
            x.partner == partner
            and (
                x.kind == "newgirl_sex_respect"
                and x.options == ("no",)
                or x.kind == "newgirl_sex_damage"
                and x.options == ("damage",)
                or x.kind == "newgirl_sex_low"
                and x.options == ("mentor",)
            )
            for x in selected
        )
        else ()
    )


def eligible_mentors(state: GameState, value: Session) -> tuple[ActorRef, ...]:
    return tuple(
        p for p in value.partners if p in value.mentors_before or p in assigned(state, value)
    )
