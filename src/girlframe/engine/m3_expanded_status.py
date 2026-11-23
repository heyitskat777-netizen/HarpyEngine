"""The Foundation hierarchy and source-proved table designations."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_rebel_alignment import current as rebel_alignment

RULE = "situational.situational.expanded-status"
Level = Literal[1, 2, 3, 4, 5, 6]
LEVELS: dict[Level, str] = {
    1: "Director or Director's Council",
    2: "Politicians, major investors and the ultra-rich",
    3: "Handlers",
    4: "Specialized staff and officers",
    5: "Girls and soldiers",
    6: "Other staff and civilians",
}
JOB_LEVELS: dict[str, Level] = {
    "director": 1,
    "patron": 2,
    "handler": 3,
    "doctor": 4,
    "intelligence_agent": 4,
    "mechanic": 4,
    "scientist": 4,
    "guard": 5,
}


class Designation(Model):
    actor: ActorRef
    level: Level
    event: str
    appointment: str
    account: str = Field(min_length=1, max_length=1200)


def designation(state: GameState, actor: ActorRef) -> Designation | None:
    return next(
        (
            Designation.model_validate_json(x["body"])
            for x in reversed(state.facts)
            if x.get("kind") == "expanded_status_designation" and x.get("actor") == actor.token
        ),
        None,
    )


def default(state: GameState, actor: ActorView) -> Level | None:
    if actor.ref.kind == "handler":
        return None if rebel_alignment(state) is not None else 3
    if actor.ref.kind == "pilot":
        return 5
    if state.world is None:
        return None
    if actor.ref.kind == "external_pilot":
        person = next((x for x in state.world.pilots if x.id == actor.ref.entity), None)
        return 5 if person and person.kind == "foundation" else None
    if actor.ref.kind != "npc":
        return None
    npc = next((x for x in state.world.npcs if x.id == actor.ref.entity), None)
    if npc is None or any(x.id == npc.faction and x.kind == "rebel" for x in state.world.factions):
        return None
    return min((JOB_LEVELS.get(x, 6) for x in npc.jobs), default=6)
