"""Actual Director NPC effects use Handler rules without sharing the GM's body."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_enforcer import end_grasps
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_world_state import Npc


def body(state: GameState, actor: ActorRef, *, alive: bool = True) -> Npc:
    npc = next((x for x in state.world.npcs if x.id == actor.entity), None) if state.world else None
    if actor.kind != "npc" or npc is None or "director" not in npc.jobs or alive and not npc.alive:
        raise ValueError("Use the actual original Director NPC body, not the GM or another NPC")
    return npc


def die(original: GameState, actor: ActorRef, event: str, account: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    npc = body(state, actor)
    if not event or not account.strip():
        raise ValueError("The actual Director ending needs its real cause and event")
    from girlframe.engine.m3_handler_void import end_actor

    state = end_actor(state, actor, event)
    state = end_actor_casts(
        end_grasps(interrupt_journeys(state, actor, event, account), actor, event), actor, event
    )
    assert state.world is not None
    state.world = state.world.model_copy(
        update={
            "npcs": tuple(
                x.model_copy(update={"alive": False}) if x.id == actor.entity else x
                for x in state.world.npcs
            )
        }
    )
    current_body = active_handler(state)
    for index, context in enumerate(state.director_contexts):
        if context.active and actor.entity in context.directors:
            remaining = tuple(
                x
                for x in context.directors
                if x != actor.entity
                and any(
                    candidate.id == x and candidate.alive and "director" in candidate.jobs
                    for candidate in state.world.npcs
                )
            )
            update: dict[str, object] = dict(
                directors=remaining, active=bool(remaining), revision=context.revision + 1
            )
            if not remaining:
                update.update(termination_reason="director_death", termination_event=event)
                if current_body is not None:
                    old = ActorRef(
                        kind="handler", entity=str(context.handler), incarnation=context.id
                    )
                    for number, cast in enumerate(state.scene_casts):
                        if any(x.actor == old for x in cast.roles):
                            roles = tuple(
                                x.model_copy(update={"actor": current_body})
                                if x.actor == old
                                else x
                                for x in cast.roles
                            )
                            unique = tuple({x.actor: x for x in roles}.values())
                            state.scene_casts[number] = cast.model_copy(
                                update={"roles": unique, "revision": cast.revision + 1}
                            )
            state.director_contexts[index] = context.model_copy(update=update)
    state.facts.append(
        dict(
            kind="director_body_ended",
            actor=actor.model_dump_json(),
            event=event,
            account=account,
            body=npc.model_dump_json(),
            controller=str(npc.controller),
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def consequence(
    original: GameState,
    actor: ActorRef,
    choice: str,
    event: str,
    account: str,
    *,
    source_work: str,
    opponent: ActorRef | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    body(state, actor)
    if (
        choice not in ("opportunity", "chance_to_act", "weakness", "injury", "death")
        or not account.strip()
    ):
        raise ValueError("The actual Director owner chooses one printed Handler effect")
    if choice == "death":
        state = die(state, actor, event, account)
    else:
        state.facts.append(
            dict(
                kind="director_injury" if choice == "injury" else "director_opportunity",
                actor=actor.model_dump_json(),
                opponent=opponent.model_dump_json() if opponent else "",
                event=event,
                choice=choice,
                account=account,
                source_work=source_work,
            )
        )
    return state
