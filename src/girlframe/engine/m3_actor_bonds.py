"""One relationship authority across originals, NPCs and converted Harpies."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bond_state import BondEdge, HelplessCondition
from girlframe.engine.m3_actor_state import ActorRef


def current_ref(state: GameState, owner: int) -> ActorRef:
    sheet = state.sheets.get(str(owner))
    if sheet is not None and sheet.character_id is not None:
        return ActorRef(kind="pilot", entity=str(owner), incarnation=sheet.character_id)
    if state.handler == owner:
        from girlframe.engine.m3_handler_consequences import active_handler

        actual = active_handler(state)
        if actual is not None:
            return actual
        raise ValueError("The original Handler body ended; create an actual fresh persona")
    raise ValueError("Recover the actual current character identity")


def _current(state: GameState, actor: ActorRef) -> bool:
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, actor)
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        return bool(sheet and sheet.character_id == actor.incarnation)
    if actor.kind == "external_pilot" and any(
        x.id == actor.entity and x.alive for x in state.harpy_states
    ):
        return True
    if state.world is None:
        return False
    if actor.kind == "npc":
        return any(x.id == actor.entity and x.alive for x in state.world.npcs)
    if actor.kind == "external_pilot":
        return any(x.id == actor.entity and x.alive for x in state.world.pilots)
    return any(x.id == actor.entity and x.alive for x in state.world.gorgons)


def _known(state: GameState, actor: ActorRef) -> bool:
    if (
        _current(state, actor)
        or any(x.actor == actor for x in state.career_archives)
        or any(x.actor == actor for x in state.handler_archives)
        or any(actor in (x.first, x.second) for x in state.actor_bonds)
        or any(actor in (x.subject, x.foe) for x in state.helpless_conditions)
        or (
            actor.kind == "external_pilot" and any(x.id == actor.entity for x in state.harpy_states)
        )
    ):
        return True
    if state.world is None:
        return False
    return any(
        actor.kind == kind and row.id == actor.entity
        for kind, rows in (
            ("npc", state.world.npcs),
            ("external_pilot", state.world.pilots),
            ("gorgon", state.world.gorgons),
        )
        for row in rows
    )


def _legacy_bound(state: GameState, actor: ActorRef) -> bool:
    # Human numeric keys need their current incarnation; world IDs remain distinct
    # original people after death and cannot alias a controller's next character.
    return _current(state, actor) if actor.kind in ("pilot", "handler") else _known(state, actor)


def _edge(state: GameState, first: ActorRef, second: ActorRef) -> BondEdge | None:
    found = [x for x in state.actor_bonds if {x.first, x.second} == {first, second}]
    if len(found) > 1:
        raise ValueError("A Bond cannot have duplicate live authorities")
    return found[0] if found else None


def _legacy(state: GameState, first: ActorRef, second: ActorRef) -> int:
    if not (_legacy_bound(state, first) and _legacy_bound(state, second)):
        return 0
    if first.kind in ("pilot", "handler") and second.kind in ("pilot", "handler"):
        key = ":".join(sorted((first.entity, second.entity), key=int))
        legacy_value = state.bonds.get(key, 0)
        if legacy_value:
            from girlframe.engine.m3_handler_consequences import active_handler

            handler = active_handler(state)
            if handler is not None and any(
                ref.entity == handler.entity and ref.entity in state.sheets
                for ref in (first, second)
            ):
                raise ValueError(
                    "Recover the actual separate-role source of this ambiguous numeric Bond"
                )
        return legacy_value
    values = []
    for npc, other in ((first, second), (second, first)):
        if npc.kind == "npc" and state.world is not None:
            row = next((x for x in state.world.npcs if x.id == npc.entity), None)
            if row is not None:
                value = row.bonds.get(other.kind + ":" + other.entity)
                if value is not None:
                    values.append(value)
    if len(set(values)) > 1:
        raise ValueError("Conflicting legacy Bond evidence needs actual source review")
    return values[0] if values else 0


def depth(state: GameState, first: ActorRef, second: ActorRef) -> int:
    if first == second:
        return 0
    edge, old = _edge(state, first, second), _legacy(state, first, second)
    if edge is not None and old:
        raise ValueError("A migrated Bond cannot also retain its numeric authority")
    return edge.depth if edge is not None else old


def _remove_legacy(state: GameState, first: ActorRef, second: ActorRef) -> None:
    if not (_legacy_bound(state, first) and _legacy_bound(state, second)):
        return
    if first.kind in ("pilot", "handler") and second.kind in ("pilot", "handler"):
        state.bonds.pop(":".join(sorted((first.entity, second.entity), key=int)), None)
    if state.world is not None:
        npcs = list(state.world.npcs)
        for index, npc in enumerate(npcs):
            for ref, other in ((first, second), (second, first)):
                if ref.kind == "npc" and npc.id == ref.entity:
                    bonds = dict(npc.bonds)
                    bonds.pop(other.kind + ":" + other.entity, None)
                    npcs[index] = npc.model_copy(update={"bonds": bonds})
        state.world = state.world.model_copy(update={"npcs": tuple(npcs)})


def set_depth(
    original: GameState,
    first: ActorRef,
    second: ActorRef,
    value: Literal[0, 1, 2],
    source_event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if (
        first == second
        or not source_event.strip()
        or not all(_known(state, x) for x in (first, second))
    ):
        raise ValueError("A Bond needs actual source-bound people and consequence")
    depth(state, first, second)
    _remove_legacy(state, first, second)
    state.actor_bonds = [x for x in state.actor_bonds if {x.first, x.second} != {first, second}]
    state.actor_bonds.append(
        BondEdge(first=first, second=second, depth=value, source_event=source_event)
    )
    return state


def _heat(state: GameState, actor: ActorRef) -> None:
    if not _current(state, actor):
        return
    if actor.kind == "pilot":
        sheet = state.sheets[actor.entity]
        sheet.heat += 2
        sheet.revision += 1
    elif actor.kind == "handler":
        state.handler_heat += 2
    elif actor.kind == "external_pilot":
        rows = getattr(state, "harpy_states", ())
        row = next((x for x in rows if x.id == actor.entity), None)
        if row is not None:
            state.harpy_states = [
                x.model_copy(update={"heat": x.heat + 2}) if x.id == row.id else x for x in rows
            ]
        elif any(x.id == actor.entity for x in state.native_harpies):
            state.native_harpies = [
                x.model_copy(update={"heat": x.heat + 2}) if x.id == actor.entity else x
                for x in state.native_harpies
            ]
        elif state.world is not None and any(x.id == actor.entity for x in state.world.pilots):
            raise ValueError("An external Pilot needs an actual Heat resource before deepening")


def change(
    original: GameState, first: ActorRef, second: ActorRef, delta: Literal[-1, 1], source_event: str
) -> GameState:
    old = depth(original, first, second)
    if delta == -1 and old == 0:
        raise ValueError("There is no Bond to weaken")
    value: Literal[0, 1, 2] = 0 if old + delta <= 0 else 2 if old + delta >= 2 else 1
    state = set_depth(original, first, second, value, source_event)
    if delta == 1 and old == 2:
        for actor in (first, second):
            _heat(state, actor)
    return state


def migrate_actor(original: GameState, actor: ActorRef, source_event: str) -> GameState:
    """Move each actual legacy edge before ending/converting its original live body."""
    state = GameState.model_validate_json(original.model_dump_json())
    if not _current(state, actor):
        raise ValueError("Migrate before removing the actual original body")
    pairs: list[tuple[ActorRef, int]] = []
    if actor.kind in ("pilot", "handler"):
        for key, value in state.bonds.items():
            owners = key.split(":")
            if actor.entity in owners:
                other_owner = next(x for x in owners if x != actor.entity)
                pairs.append((current_ref(state, int(other_owner)), value))
    if state.world is not None:
        for npc in state.world.npcs:
            npc_depth = npc.bonds.get(actor.kind + ":" + actor.entity)
            if npc_depth is not None:
                pairs.append((ActorRef(kind="npc", entity=npc.id), npc_depth))
    for other, value in pairs:
        bounded: Literal[0, 1, 2] = 2 if value == 2 else 1 if value == 1 else 0
        state = set_depth(state, actor, other, bounded, source_event)
    return state


def rebind(original: GameState, old: ActorRef, new: ActorRef, source_event: str) -> GameState:
    """Trusted conversion only: the same fictional person gains a different body type."""
    state = GameState.model_validate_json(original.model_dump_json())
    initial_handler = (
        old.kind == new.kind == "handler"
        and old.entity == new.entity
        and old.incarnation is None
        and state.handler_persona is not None
        and state.handler_persona.id == new.incarnation
    )
    if (
        not (_known(state, old) or initial_handler)
        or not _current(state, new)
        or old == new
        or not source_event
    ):
        raise ValueError("Rebinding requires the real conversion's source and identities")
    edges: list[BondEdge] = []
    for edge in state.actor_bonds:
        first = new if edge.first == old else edge.first
        second = new if edge.second == old else edge.second
        if first == second or any({x.first, x.second} == {first, second} for x in edges):
            raise ValueError("Conversion cannot merge distinct people's Bonds")
        edges.append(edge.model_copy(update={"first": first, "second": second}))
    state.actor_bonds = edges
    state.helpless_conditions = [
        x.model_copy(
            update={
                "subject": new if x.subject == old else x.subject,
                "foe": new if x.foe == old else x.foe,
            }
        )
        for x in state.helpless_conditions
    ]
    return GameState.model_validate_json(state.model_dump_json())


def _same_body(state: GameState, first: ActorRef, second: ActorRef) -> bool:
    if first == second:
        return True
    if first.kind != "handler" or second.kind != "handler":
        return False
    from girlframe.engine.m3_handler_consequences import same_handler_body

    return same_handler_body(state, first) and same_handler_body(state, second)


def is_helpless(state: GameState, subject: ActorRef, foe: ActorRef | None = None) -> bool:
    if any(
        x.active
        and _same_body(state, x.subject, subject)
        and (foe is None or _same_body(state, x.foe, foe))
        for x in state.helpless_conditions
    ):
        return True
    if subject.kind == "pilot" and _current(state, subject):
        owners = state.sheets[subject.entity].helpless_against
        return (
            bool(owners)
            if foe is None
            else (
                foe.kind in ("pilot", "handler")
                and _current(state, foe)
                and int(foe.entity) in owners
            )
        )
    return False


def make_helpless(
    original: GameState, subject: ActorRef, foe: ActorRef, source_event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    from girlframe.engine.m3_handler_consequences import same_handler_body

    if (
        _same_body(state, subject, foe)
        or not source_event
        or not all(_known(state, x) or same_handler_body(state, x) for x in (subject, foe))
    ):
        raise ValueError("Helplessness needs actual source-bound opposing people")
    if subject.kind == "pilot" and _current(state, subject) and foe.kind in ("pilot", "handler"):
        sheet = state.sheets[subject.entity]
        sheet.helpless_against = tuple(x for x in sheet.helpless_against if str(x) != foe.entity)
    active = next(
        (
            x
            for x in state.helpless_conditions
            if x.active and _same_body(state, x.subject, subject) and _same_body(state, x.foe, foe)
        ),
        None,
    )
    if active is not None:
        events = tuple(dict.fromkeys((*active.source_events, source_event)))
        state.helpless_conditions = [
            x.model_copy(update={"source_events": events}) if x.id == active.id else x
            for x in state.helpless_conditions
        ]
    else:
        identity = str(uuid5(NAMESPACE_URL, subject.token + foe.token + source_event))
        state.helpless_conditions.append(
            HelplessCondition(
                id=identity,
                subject=subject,
                foe=foe,
                source_events=(source_event,),
            )
        )
    return state


def migrate_helpless(original: GameState, actor: ActorRef, source_event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    for sheet in tuple(state.sheets.values()):
        subject = current_ref(state, sheet.owner)
        for owner in tuple(sheet.helpless_against):
            foe = current_ref(state, owner)
            if actor in (subject, foe):
                state = make_helpless(state, subject, foe, source_event)
    return state


def clear_helpless(
    original: GameState, subject: ActorRef, source_event: str, foe: ActorRef | None = None
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if not source_event or not is_helpless(state, subject, foe):
        raise ValueError("Only an actual recovery source can clear existing Helplessness")
    state.helpless_conditions = [
        x.model_copy(update={"active": False, "recovery_event": source_event})
        if x.active
        and _same_body(state, x.subject, subject)
        and (foe is None or _same_body(state, x.foe, foe))
        else x
        for x in state.helpless_conditions
    ]
    if subject.kind == "pilot" and _current(state, subject):
        sheet = state.sheets[subject.entity]
        sheet.helpless_against = (
            () if foe is None else tuple(x for x in sheet.helpless_against if str(x) != foe.entity)
        )
    return state


def bond_ref(state: GameState, ref: ActorRef) -> ActorRef:
    """Only a proved current same-body Handler alias shares its actual Bond endpoint.

    This normalizes reads, not stored edges or historic consent. Existing raw alias
    edges require a real source-bound write/recovery rather than silent migration.
    """
    import json

    from girlframe.engine.m3_handler_consequences import active_handler

    actual = active_handler(state)
    if ref.kind != "handler" or actual is None or ref.entity != actual.entity or ref == actual:
        return ref
    initial_alias = ref.incarnation is None and not state.handler_archives
    context = next(
        (
            x
            for x in state.director_contexts
            if x.active
            and x.handler == state.handler
            and x.id == ref.incarnation
            and x.source_event.strip()
        ),
        None,
    )
    if context is not None:
        for archive in state.handler_archives:
            saved = json.loads(archive.links_json).get("director_contexts", ())
            if any(x.get("id") == context.id for x in saved):
                return ref  # An ended original context never identifies a replacement body.
    if not initial_alias and context is None:
        return ref
    if any(ref in (x.first, x.second) for x in state.actor_bonds):
        raise ValueError(
            "Recover source-bound Handler alias Bond edges; do not duplicate authority"
        )
    return actual
