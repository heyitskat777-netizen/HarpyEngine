"""Actor-bound Broken and its exact relative Status/removal effects (PDF52)."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_alpha_state import Broken

RULE = "girl.alpha.brutalize"


def current(state: GameState, ref: ActorRef) -> bool:
    from girlframe.engine.m3_careers import binding

    if ref.kind == "pilot":
        sheet = state.sheets.get(ref.entity)
        active = binding(state, int(ref.entity))
        return (
            sheet is not None
            and sheet.character_id == ref.incarnation
            and int(ref.entity) in state.order
            and (
                active is None
                and not any(x.actor == ref for x in state.career_archives)
                or active is not None
                and active.active
                and active.character == ref.incarnation
            )
        )
    if ref.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, ref)
    if ref.kind == "npc":
        return bool(state.world and any(x.id == ref.entity and x.alive for x in state.world.npcs))
    return False


def conditions(state: GameState, subject: ActorRef, inflictor: ActorRef) -> tuple[Broken, ...]:
    return tuple(
        x
        for x in state.alpha_broken
        if x.subject == subject and x.inflictor == inflictor and x.removed_event is None
    )


def status(state: GameState, first: ActorRef, second: ActorRef) -> bool | None:
    if first == second or not current(state, first) or not current(state, second):
        return None
    a, b = bool(conditions(state, second, first)), bool(conditions(state, first, second))
    if a and b:
        raise ValueError(
            "Reciprocal Broken Status is unresolved; recover the actual condition source"
        )
    return True if a else False if b else None


def legacy_status(state: GameState, first: int, second: int) -> bool | None:
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_handler_consequences import active_handler

    try:
        a = active_handler(state) if first == state.handler else current_ref(state, first)
        b = active_handler(state) if second == state.handler else current_ref(state, second)
    except ValueError:
        return None
    return status(state, a, b) if a is not None and b is not None else None


def inflict(
    original: GameState,
    subject: ActorRef,
    inflictor: ActorRef,
    action: str,
    event: str,
    *,
    counter: str | None = None,
    distinct_source: bool = False,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if subject == inflictor or not current(state, subject) or not event:
        raise ValueError("Break an actual distinct current original, not a successor or self")
    existing = conditions(state, subject, inflictor)
    if existing and (not distinct_source or any(x.source_action == action for x in existing)):
        return state
    state.alpha_broken.append(
        Broken(
            id=str(uuid5(NAMESPACE_URL, "girlframe:broken:" + action + ":" + subject.token)),
            subject=subject,
            inflictor=inflictor,
            source_action=action,
            source_event=event,
            counter=counter,
        )
    )
    return state


def remove(
    original: GameState, subject: ActorRef, inflictor: ActorRef, action: str, event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    existing = conditions(state, subject, inflictor)
    if not existing or not current(state, subject) or not event:
        raise ValueError("Remove only the actual subject's Broken against this original inflictor")
    ids = {x.id for x in existing}
    state.alpha_broken = [
        x.model_copy(update=dict(removed_event=event, removed_action=action)) if x.id in ids else x
        for x in state.alpha_broken
    ]
    return state
