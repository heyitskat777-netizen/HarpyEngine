"""Director presence changes rule authority without making the Handler a Pilot."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import DirectorContext, GameState, IdentityState
from girlframe.engine.m3_off_duty import Period


def enter(
    state: GameState, handler: int, npc_id: str, work: str, labels: tuple[str, ...], source: str
) -> GameState:
    npc = (
        next((x for x in state.world.npcs if x.id == npc_id and x.alive), None)
        if state.world
        else None
    )
    if (
        handler != state.handler
        or npc is None
        or "director" not in npc.jobs
        or npc.controller == handler
        or not work.strip()
        or not source.strip()
    ):
        raise ValueError("Use the actual current Handler, separate Director and presence source")
    updated = GameState.model_validate_json(state.model_dump_json())
    if any(work in x.source_works for x in updated.director_contexts):
        raise ValueError("This presence source already established its actual context")
    active = [x for x in updated.director_contexts if x.active]
    if len(active) > 1 or any(x.handler != handler for x in active):
        raise ValueError("Recover the inconsistent active Handler rules context")
    if active:
        context = active[0]
        if labels or work in context.source_works:
            raise ValueError(
                "An overlapping Director does not restart Heat or grant another Identity set"
            )
        value = context.model_copy(
            update={
                "directors": tuple(dict.fromkeys((*context.directors, npc_id))),
                "source_works": (*context.source_works, work),
                "revision": context.revision + 1,
            }
        )
        updated.director_contexts[updated.director_contexts.index(context)] = (
            DirectorContext.model_validate_json(value.model_dump_json())
        )
    else:
        if len(labels) != 2 or any(not x.strip() or len(x.strip()) > 120 for x in labels):
            raise ValueError("The Handler chooses exactly two nonblank ordinary Identity names")
        identity = str(uuid5(NAMESPACE_URL, source + ":director-context"))
        from girlframe.engine.m3_handler_consequences import active_handler

        actual_body = active_handler(updated)
        if actual_body is None:
            raise ValueError("The actual current Handler body must exist before changing its rules")
        context = DirectorContext(
            id=identity,
            handler=handler,
            directors=(npc_id,),
            source_works=(work,),
            source_event=source,
            body_actor=actual_body,
            identities=[
                IdentityState(
                    id=str(uuid5(NAMESPACE_URL, identity + ":" + str(i))),
                    name=label.strip(),
                    slot=i,
                )
                for i, label in enumerate(labels)
            ],
        )
        updated.director_contexts.append(context)
        updated.handler_heat = 0
    return updated


def leave(state: GameState, actor: int, identity: str, npc_id: str, source: str) -> GameState:
    context = next((x for x in state.director_contexts if x.id == identity and x.active), None)
    npc = next((x for x in state.world.npcs if x.id == npc_id), None) if state.world else None
    if (
        context is None
        or npc is None
        or npc.controller != actor
        or npc_id not in context.directors
        or not npc.alive
        or not source.strip()
    ):
        raise ValueError("Only this actual Director's human controller records its departure")
    updated = GameState.model_validate_json(state.model_dump_json())
    directors = tuple(x for x in context.directors if x != npc_id)
    value = context.model_copy(
        update={"directors": directors, "active": bool(directors), "revision": context.revision + 1}
    )
    updated.director_contexts = [
        DirectorContext.model_validate_json(value.model_dump_json()) if x.id == identity else x
        for x in updated.director_contexts
    ]
    updated.facts.append(
        {"kind": "director_departed", "context": identity, "npc": npc_id, "source_event": source}
    )
    return updated


def absence(period: Period, state: GameState, npc_id: str, outcome: str) -> dict[str, object]:
    npc = next((x for x in state.world.npcs if x.id == npc_id), None) if state.world else None
    if npc is None or "director" not in npc.jobs:
        raise ValueError("The actual Director must still exist for this presence review")
    for subject, progress in period.progress.items():
        observation = progress.observation
        if observation is None or not any(
            x.id == outcome and x.resolved and x.kind == "director_or_rival_arrives"
            for x in observation.outcomes
        ):
            continue
        scene = progress.scene
        if (
            scene is None
            or scene.kind != "observation:director_or_rival_arrives"
            or period.handler in scene.participants
            or npc.controller not in scene.participants
            or set(scene.participants) != set(scene.acknowledgements)
        ):
            continue
        if not any(
            x.get("kind") == "observation_npc"
            and x.get("outcome") == outcome
            and x.get("npc") == npc_id
            for x in state.facts
        ):
            continue
        return {
            "period": period.id,
            "scene_owner": subject,
            "participants": scene.participants,
            "npc": npc_id,
            "controller": npc.controller,
        }
    raise ValueError(
        "A completed actual Director scene excluding the Handler is required for absence"
    )
