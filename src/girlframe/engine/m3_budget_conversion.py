"""The original High Budget demand and its next actual mission."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler

RULE = "strain.budget.high.2.1"
KIND = "budget_conversion_order"


class CaptureOrder(Model):
    id: str
    period: str
    source_event: str
    handler: ActorRef
    account: str = Field(min_length=1, max_length=2400)
    mission: str | None = None
    target: ActorRef | None = None
    dispatched: str | None = None
    settled: str | None = None
    conversion: str | None = None

    @model_validator(mode="after")
    def lifecycle(self) -> "CaptureOrder":
        if self.handler.kind != "handler" or (
            self.target is not None and self.target.kind != "external_pilot"
        ):
            raise ValueError("Preserve the original Handler and exact external Pilot")
        if (
            (self.mission is None) != (self.dispatched is None)
            or (self.target is None) != (self.dispatched is None)
            or (self.settled is not None and self.dispatched is None)
            or (self.conversion is not None and self.settled is None)
        ):
            raise ValueError("Preserve dispatch before settlement of the conversion demand")
        return self


def orders(state: GameState) -> tuple[CaptureOrder, ...]:
    return tuple(
        CaptureOrder.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: CaptureOrder) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def require_next(state: GameState, work: str, period: str, event: str, account: str) -> None:
    handler = active_handler(state)
    if handler is None or any(x.id == work for x in orders(state)):
        raise ValueError("Bind the real demand once to its original active Handler")
    put(
        state,
        CaptureOrder(id=work, period=period, source_event=event, handler=handler, account=account),
    )
