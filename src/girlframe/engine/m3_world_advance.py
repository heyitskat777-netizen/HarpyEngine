"""Map advancement uses actual present bodies; cached offstage cells have no effects."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import ClassChange, Movement, Result, directed_steps, end_off_duty


def plan(state: GameState) -> tuple[frozenset[str], tuple[dict[str, str], ...]]:
    if state.world is None:
        raise ValueError("Initialize the actual map before world advancement")
    present: set[str] = set()
    deferred: list[dict[str, str]] = []
    for gorgon in state.world.gorgons:
        if not gorgon.alive:
            continue
        actor = ActorRef(kind="gorgon", entity=gorgon.id)
        actual = resolve(state, actor, ())
        missing = actual.cell is None
        reason = actual.offstage_source or "actual_position_unknown"
        if not missing and gorgon.gorgon_class == "directed" and gorgon.goal is not None:
            if gorgon.goal.kind == "npc":
                goal_ref = ActorRef(kind="npc", entity=gorgon.goal.entity_id or "")
                goal = resolve(state, goal_ref, (), require_alive=False)
                if not goal.alive:
                    endpoint = next(x for x in state.world.npcs if x.id == goal_ref.entity)
                    deferred.append(
                        dict(
                            actor=actor.model_dump_json(),
                            source="actual_goal_ended",
                            goal=goal_ref.model_dump_json(),
                            endpoint=endpoint.model_dump_json(),
                        )
                    )
                    continue
                missing = goal.cell is None
                reason = goal.offstage_source or "actual_goal_position_unknown"
        if missing:
            deferred.append(dict(actor=actor.model_dump_json(), source=reason))
        else:
            present.add(gorgon.id)
    return frozenset(present), tuple(deferred)


def steps(state: GameState) -> dict[str, tuple[tuple[int, int], ...]]:
    present, _ = plan(state)
    assert state.world is not None
    return {
        x.id: directed_steps(state.world, x)
        for x in state.world.gorgons
        if x.id in present and x.gorgon_class == "directed" and x.alive
    }


def advance(
    state: GameState, period: str, movements: tuple[Movement, ...], changes: tuple[ClassChange, ...]
) -> tuple[Result, tuple[dict[str, str], ...]]:
    present, deferred = plan(state)
    assert state.world is not None
    return end_off_duty(state.world, period, movements, changes, present_gorgons=present), deferred
