"""Original participants and explicit conditional Tag rights at a political function."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler

Kind = Literal["auction", "fundraiser", "ball", "orgy"]
NOTICE = "During this function, whenever you act out of line you may give the Handler a Tag."


class Function(Model):
    id: str = Field(min_length=1)
    source_work: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    period: str = Field(min_length=1)
    patron: ActorRef
    handler: ActorRef
    kind: Kind
    notice: str = NOTICE
    people: tuple[ActorRef, ...]
    attended: tuple[ActorRef, ...] = ()
    phase: Literal["attendance", "active", "complete"] = "attendance"
    account: str = Field(min_length=1, max_length=2400)
    ended_event: str | None = None

    @model_validator(mode="after")
    def actual_participants(self) -> "Function":
        if (
            not self.people
            or len(set(self.people)) != len(self.people)
            or any(x.kind != "pilot" for x in self.people)
            or self.patron.kind != "npc"
            or self.handler.kind != "handler"
            or len(set(self.attended)) != len(self.attended)
            or not set(self.attended) <= set(self.people)
            or (self.phase != "attendance" and set(self.attended) != set(self.people))
            or (self.phase == "complete") != (self.ended_event is not None)
        ):
            raise ValueError(
                "Preserve original participants, informed attendance and actual ending"
            )
        return self


def functions(state: GameState) -> tuple[Function, ...]:
    return tuple(
        Function.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "political_function"
    )


def get(state: GameState, identity: str) -> Function:
    record = next((x for x in functions(state) if x.id == identity), None)
    if record is None:
        raise ValueError("Open the actual source political function")
    return record


def put(state: GameState, record: Function) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "political_function" and x.get("id") == record.id)
    ]
    state.facts.append(dict(kind="political_function", id=record.id, body=record.model_dump_json()))


def create(
    state: GameState, work: str, period: str, event: str, patron: str, kind: Kind, account: str
) -> GameState:
    if (
        state.world is None
        or not state.order
        or any(x.source_work == work for x in functions(state))
    ):
        raise ValueError("Use the actual Cadre, map and one new political-function source")
    npc = next(
        (x for x in state.world.npcs if x.id == patron and x.alive and "patron" in x.jobs), None
    )
    handler = active_handler(state)
    if npc is None or handler is None:
        raise ValueError("Choose the existing local political patron and original Handler")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Function(
            id=work + ":function",
            source_work=work,
            source_event=event,
            period=period,
            patron=ActorRef(kind="npc", entity=patron),
            handler=handler,
            kind=kind,
            people=tuple(current_ref(state, uid) for uid in state.order),
            account=account,
        ),
    )
    return changed
