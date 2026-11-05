"""A privately established NPC contact, retaining original people and source history."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler

RULE = "strain.rebellion.low.5.2"


class Contact(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    people: tuple[ActorRef, ...]
    city: str
    account: str = Field(min_length=1, max_length=2400)
    phase: Literal["choose", "confirm", "revise", "complete"] = "choose"
    girl: ActorRef | None = None
    npc: ActorRef | None = None
    controller: int | None = None
    method: str | None = Field(default=None, min_length=1, max_length=1200)
    claim_event: str | None = None
    response: str | None = Field(default=None, min_length=1, max_length=1200)
    response_event: str | None = None

    @model_validator(mode="after")
    def actual_people(self) -> "Contact":
        claimed = (self.girl, self.npc, self.controller, self.method, self.claim_event)
        if (
            self.handler.kind != "handler"
            or not self.people
            or len(set(self.people)) != len(self.people)
            or any(x.kind != "pilot" for x in self.people)
            or self.phase == "choose"
            and any(x is not None for x in claimed)
            or self.phase != "choose"
            and any(x is None for x in claimed)
            or self.girl is not None
            and self.girl not in self.people
            or self.npc is not None
            and self.npc.kind != "npc"
            or self.phase in ("revise", "complete")
            and not (self.response and self.response_event)
            or self.phase in ("choose", "confirm")
            and (self.response or self.response_event)
        ):
            raise ValueError(
                "Preserve actual original roles, authored route and owned confirmation"
            )
        return self


def contacts(state: GameState) -> tuple[Contact, ...]:
    return tuple(
        Contact.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "rebel_contact"
    )


def get(state: GameState, identity: str) -> Contact:
    value = next((x for x in contacts(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the actual original contact request")
    return value


def put(state: GameState, value: Contact) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == "rebel_contact" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="rebel_contact", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState, work: str, period: str, event: str, city: str, account: str
) -> GameState:
    location = (
        next((x for x in state.world.locations if x.id == city), None) if state.world else None
    )
    handler = active_handler(state)
    if (
        location is None
        or location.kind != "city"
        or handler is None
        or not state.order
        or any(x.source_work == work for x in contacts(state))
    ):
        raise ValueError("Choose the actual nearby city and original Cadre")
    changed = GameState.model_validate_json(state.model_dump_json())
    put(
        changed,
        Contact(
            id=work + ":contact",
            source_work=work,
            source_event=event,
            period=period,
            handler=handler,
            people=tuple(current_ref(state, uid) for uid in state.order),
            city=city,
            account=account,
        ),
    )
    return changed
