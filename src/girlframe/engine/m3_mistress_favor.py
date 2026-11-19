"""The Mistress's private favor, original roles and later performance."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_intracadre_marriage import status_groups

RULE = "handler-playbook.mistress.sex-play"
Phase = Literal["invite", "scene", "favor", "decision", "owed", "review", "complete", "withdrawn"]


class Favor(Model):
    id: str
    handler: ActorRef
    girl: ActorRef
    scene: str
    channel: int
    event: str
    phase: Phase = "invite"
    attestations: tuple[ActorRef, ...] = ()
    favor: str = Field(default="", max_length=1200)
    accepted_event: str | None = None
    outcome: Literal["fulfilled", "failed", "declined"] | None = None
    action: str | None = None
    account: str = Field(default="", max_length=1200)


def records(state: GameState) -> tuple[Favor, ...]:
    return tuple(
        Favor.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "mistress_favor"
    )


def put(state: GameState, value: Favor) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != ("mistress_favor", value.id)
    ] + [dict(kind="mistress_favor", id=value.id, body=value.model_dump_json())]


def change_rank(state: GameState, owner: int, *, ace: bool) -> None:
    groups = status_groups(state)
    index = next(i for i, group in enumerate(groups) if owner in group)
    if len(groups[index]) != 1:
        raise ValueError("Review this shared Status before the printed solitary rank change")
    distance = index if ace else len(groups) - 1 - index
    for _ in range(distance):
        shift_status(state, owner, 1 if ace else -1)
    if distance:
        state.sheets[str(owner)].revision += 1
