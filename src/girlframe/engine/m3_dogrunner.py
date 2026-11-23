"""Dogrunner designations persist independently of the underlying Status order."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef

RULE = "handler-playbook.dogrunner.no-rest-for-hounds"
BOOK = "handler-playbook.dogrunner.dogrunner"


def all_except_ace(state: GameState) -> bool:
    from girlframe.engine.m3_intracadre_marriage import status_groups

    assigned = owners(state)
    groups = status_groups(state)
    return (
        assigned is not None
        and len(groups) >= 2
        and len(groups[0]) == 1
        and set(assigned) == set(state.order) - set(groups[0])
    )


def owners(state: GameState) -> tuple[int, ...] | None:
    from girlframe.engine.m3_intracadre_marriage import status_groups

    persona = state.handler_persona
    if persona is None or persona.owner != state.handler or persona.playbook != "Dogrunner":
        return None
    groups = status_groups(state)
    ace = groups[0] if groups else ()
    return tuple(
        sheet.owner
        for ref in persona.sticky_dogs
        if ref.kind == "pilot"
        and (sheet := state.sheets.get(ref.entity)) is not None
        and sheet.character_id == ref.incarnation
        and sheet.owner in state.order
        and sheet.owner not in ace
    )


def _assign(state: GameState, roles: tuple[int, ...], former: tuple[int, ...]) -> None:
    from girlframe.engine.m3_learned_play_state import clear_hound_status

    persona = state.handler_persona
    assert persona is not None
    existing = tuple(
        ActorRef(kind="pilot", entity=str(uid), incarnation=state.sheets[str(uid)].character_id)
        for uid in roles
    )
    if persona.sticky_dogs != existing:
        state.handler_persona = persona.model_copy(update=dict(sticky_dogs=existing))
    for uid in set(former) - set(roles):
        if (sheet := state.sheets.get(str(uid))) is not None:
            clear_hound_status(state, uid, "rank")
            sheet.status_marked = False


def after_rank_change(
    state: GameState,
    former: tuple[int, ...],
    previous_bottom: tuple[int, ...],
) -> None:
    from girlframe.engine.m3_intracadre_marriage import status_groups

    assigned = owners(state)
    if assigned is None:
        return
    groups = status_groups(state)
    if not groups:
        _assign(state, (), former)
        return
    ace, last = groups[0], groups[-1]
    new_dogs = tuple(
        uid
        for uid in last
        if uid not in previous_bottom and uid not in ace and str(uid) in state.sheets
    )
    _assign(state, tuple(dict.fromkeys((*assigned, *new_dogs))), former)


def after_punishment(state: GameState, subject: int) -> None:
    assigned = owners(state)
    if assigned is None or subject not in assigned:
        return
    _assign(state, tuple(uid for uid in assigned if uid != subject), assigned)
