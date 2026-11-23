"""Only She Matters resolves an actual ordinary NPC and awards Harpy Heat."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_physical import interrupt_journeys


class Killing(Model):
    harpy: ActorRef
    target: ActorRef
    controller: int
    advancement: str
    scene: str
    event: str
    heat: Literal[1, 2]


def kill(state: GameState, result: Killing, account: str) -> GameState:
    if state.world is None or result.target.kind != "npc" or not account.strip():
        raise ValueError("Use an actual living ordinary NPC and describe the scene's outcome")
    victim = next((x for x in state.world.npcs if x.id == result.target.entity), None)
    source = harpy(state, result.harpy)
    if (
        victim is None
        or not victim.alive
        or victim.source_kind is not None
        or "director" in victim.jobs
        or source.controller != result.controller
    ):
        raise ValueError("Recover the living original Harpy and actual ordinary NPC")
    changed = interrupt_journeys(state, result.target, result.event, account)
    changed = end_actor_casts(changed, result.target, result.event)
    changed = update(changed, result.harpy, heat=source.heat + result.heat)
    assert changed.world is not None
    changed.world = changed.world.model_copy(
        update=dict(
            npcs=tuple(
                npc.model_copy(update=dict(alive=False)) if npc.id == victim.id else npc
                for npc in changed.world.npcs
            )
        )
    )
    changed.facts.append(
        dict(kind="harpy_only_she_matters", id=result.event, body=result.model_dump_json())
    )
    return changed
