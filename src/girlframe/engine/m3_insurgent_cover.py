"""The printed Insurgent Cover roll, its original holder and actual evidence."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.rolls import Face

RULE = "handler-playbook.insurgent.cover-strain"
WORK = "insurgent_cover_strain"


class Cover(Model):
    id: str
    period: str
    handler: ActorRef
    source_event: str
    face: Face | None = None
    effective_face: Face | None = None
    roll_event: str | None = None
    rng_source: Literal["os", "test_injected"] | None = None
    holder: ActorRef | None = None
    choice_event: str | None = None
    tag: str | None = None
    evidence_event: str | None = None
    lost_event: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def actual(self) -> "Cover":
        if (
            self.handler.kind != "handler"
            or (self.roll_event is None) != (self.face is None)
            or (self.rng_source is None) != (self.face is None)
            or self.effective_face is not None
            and self.face is None
            or (self.holder is None) != (self.choice_event is None)
            or self.holder is not None
            and (self.holder.kind != "pilot" or self.effective_face != 1)
            or (self.tag is None) != (self.evidence_event is None)
            or self.tag is not None
            and self.holder is None
            or self.lost_event is not None
            and self.tag is None
        ):
            raise ValueError("Recover the original Cover roll, actual evidence and its holder")
        return self


def records(state: GameState) -> tuple[Cover, ...]:
    return tuple(
        Cover.model_validate_json(row["body"]) for row in state.facts if row.get("kind") == WORK
    )


def put(state: GameState, value: Cover) -> None:
    state.facts = [x for x in state.facts if x.get("kind") != WORK or x.get("id") != value.id]
    state.facts.append(dict(kind=WORK, id=value.id, body=value.model_dump_json()))


def effective(state: GameState, handler: ActorRef, face: Face) -> int | None:
    repeated = any(x.handler == handler and x.effective_face == face for x in records(state))
    result = int(face) + int(repeated)
    return result if result <= 6 else None


def held_tag(state: GameState, handler: ActorRef, tag: str) -> bool:
    return any(
        x.handler == handler and x.tag == tag and x.lost_event is None for x in records(state)
    )
