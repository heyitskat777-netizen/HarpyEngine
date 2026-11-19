"""A single original Handler gain can suppress otherwise established witnesses."""

from pydantic import model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

RULE = "strain.void.endgame.5"


class Concealment(Model):
    id: str
    handler: ActorRef
    source: str
    granted: str
    used_work: str | None = None
    used_event: str | None = None

    @model_validator(mode="after")
    def actual_gain(self) -> "Concealment":
        if self.handler.kind != "handler" or (self.used_work is None) != (self.used_event is None):
            raise ValueError("Concealment belongs to the original Handler and one actual gain")
        return self


class Witness(Model):
    actor: ActorRef
    controller: int


class Notice(Model):
    id: str
    handler: ActorRef
    event: str
    witnesses: tuple[Witness, ...]


def grants(state: GameState) -> tuple[Concealment, ...]:
    return tuple(
        Concealment.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_void_concealment"
    )


def notices(state: GameState) -> tuple[Notice, ...]:
    return tuple(
        Notice.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "handler_void_notice"
    )


def save_grant(state: GameState, value: Concealment) -> None:
    state.facts = [
        x
        for x in state.facts
        if (x.get("kind"), x.get("id")) != ("handler_void_concealment", value.id)
    ] + [dict(kind="handler_void_concealment", id=value.id, body=value.model_dump_json())]


def record_gain(
    state: GameState,
    handler: ActorRef,
    work: str,
    event: str,
    witnesses: tuple[Witness, ...] = (),
) -> None:
    if handler.kind != "handler":
        return
    effects = grants(state)
    if any(x.used_work == work for x in effects) or any(x.id == work for x in notices(state)):
        return
    active = next((x for x in effects if x.handler == handler and x.used_event is None), None)
    if active is not None:
        save_grant(state, active.model_copy(update=dict(used_work=work, used_event=event)))
    elif witnesses:
        state.facts.append(
            dict(
                kind="handler_void_notice",
                id=work,
                body=Notice(
                    id=work, handler=handler, event=event, witnesses=witnesses
                ).model_dump_json(),
            )
        )
