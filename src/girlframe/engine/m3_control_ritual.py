"""Original Girl Control Rituals: Tag-like marks restricted to Disobey Orders."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.rebellion.high.4.2"


class Ritual(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    people: tuple[ActorRef, ...]
    actor: ActorRef | None = None
    action: str | None = None
    declined: bool = False
    tag: TagState | None = None
    creation_event: str | None = None
    removed: bool = False
    account: str = Field(min_length=1, max_length=2400)

    @model_validator(mode="after")
    def original_choice(self) -> "Ritual":
        if (
            not self.people
            or len(set(self.people)) != len(self.people)
            or any(x.kind != "pilot" for x in self.people)
            or (self.actor is None) != (self.action is None)
            or self.actor is not None
            and self.actor not in self.people
            or (self.declined or self.tag or self.creation_event or self.removed)
            and not self.actor
            or self.declined
            and self.tag is not None
            or self.tag is not None
            and (
                not self.creation_event
                or self.actor is None
                or self.tag.id != self.id
                or self.tag.giver != int(self.actor.entity)
                or self.tag.giver_character != self.actor.incarnation
            )
        ):
            raise ValueError("Preserve the original Cadre, successful refusal and Girl's choice")
        return self


def rituals(state: GameState) -> tuple[Ritual, ...]:
    return tuple(
        Ritual.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "control_ritual"
    )


def put(state: GameState, value: Ritual) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "control_ritual" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="control_ritual", id=value.id, body=value.model_dump_json()))


def create(state: GameState, work: str, period: str, event: str, account: str) -> GameState:
    if not state.order or any(x.source_work == work for x in rituals(state)):
        raise ValueError("Use the actual new Control Ritual source and original Girls")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Ritual(
            id=work + ":ritual",
            source_work=work,
            source_event=event,
            period=period,
            people=tuple(current_ref(state, uid) for uid in state.order),
            account=account,
        ),
    )
    return changed


def owned(state: GameState, owner: int) -> tuple[Ritual, ...]:
    sheet = state.sheets.get(str(owner))
    return tuple(
        x
        for x in rituals(state)
        if sheet and x.actor == current_ref(state, owner) and x.tag and not x.removed
    )


def tags(state: GameState, owner: int) -> list[TagState]:
    return [x.tag for x in owned(state, owner) if x.tag is not None]


def save_tag(state: GameState, owner: int, tag: TagState) -> None:
    for value in owned(state, owner):
        if value.tag and value.tag.id == tag.id:
            put(state, value.model_copy(update=dict(tag=tag)))
            return


def remove(state: GameState, owner: int, tag: str) -> None:
    for value in owned(state, owner):
        if value.tag and value.tag.id == tag:
            put(state, value.model_copy(update=dict(removed=True)))
