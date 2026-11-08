"""A real original Girl owns acceptance of the source-bound stipend offer."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.void.endgame.4"


class Offer(Model):
    id: str
    source_event: str
    offered_event: str
    handler: ActorRef
    girl: ActorRef
    account: str = Field(min_length=1, max_length=1200)
    phase: Literal["offered", "accepted", "declined"] = "offered"
    response: str | None = Field(default=None, max_length=1200)
    response_event: str | None = None
    archive: str | None = None

    @model_validator(mode="after")
    def original_roles(self) -> "Offer":
        if (
            self.handler.kind != "handler"
            or self.girl.kind != "pilot"
            or (self.phase == "offered") != (self.response_event is None)
            or (self.phase != "offered" and not self.response)
            or (self.phase == "accepted") != bool(self.archive)
        ):
            raise ValueError("Keep the actual original offer, recipient and owned outcome")
        return self


def offers(state: GameState) -> tuple[Offer, ...]:
    return tuple(
        Offer.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "void_retirement_offer"
    )


def put(state: GameState, value: Offer) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "void_retirement_offer" and x.get("id") == value.id)
    ]
    state.facts.append(
        dict(kind="void_retirement_offer", id=value.id, body=value.model_dump_json())
    )
