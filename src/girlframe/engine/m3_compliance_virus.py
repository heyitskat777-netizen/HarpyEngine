"""Source-specific Compliance Virus; no contact inference, dice or duplicate resources."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_compliance_virus_state import (
    FrameRef,
    InfectedPerson,
    PainRestraint,
    PastLinkExposure,
    Purge,
    Record,
    Strain,
)
from girlframe.engine.m3_enforcer_requisitions import VIRUS, frame, held
from girlframe.engine.m3_physical import occupied_frame

KINDS = {
    Strain: "compliance_virus_frame",
    InfectedPerson: "compliance_virus_person",
    Purge: "compliance_virus_purge",
    PainRestraint: "compliance_virus_pain",
    PastLinkExposure: "compliance_virus_past_link",
}


def records[T: Record](state: GameState, model: type[T]) -> tuple[T, ...]:
    values = tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )
    if len({x.id for x in values}) != len(values):
        raise ValueError("Recover unique actual Compliance Virus source records")
    return values


def record[T: Record](state: GameState, model: type[T], identity: str) -> T:
    found = next((x for x in records(state, model) if x.id == identity), None)
    if found is None:
        raise ValueError("Recover the actual original Compliance Virus source")
    return found


def put[T: Record](state: GameState, value: T) -> None:
    model = type(value)
    value = model.model_validate_json(value.model_dump_json())
    prior = [x for x in records(state, model) if x.id == value.id]
    if len(prior) > 1:
        raise ValueError("Recover the unique original Virus record")
    state.facts = [
        x
        for x in state.facts
        if not (
            x.get("kind") == KINDS[model] and model.model_validate_json(x["body"]).id == value.id
        )
    ]
    state.facts.append(dict(kind=KINDS[model], body=value.model_dump_json()))


def clone(state: GameState) -> GameState:
    return GameState.model_validate_json(state.model_dump_json())


def identity(kind: str, *sources: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:virus:" + kind + ":" + ":".join(sources)))


def cockpit(state: GameState, actor: ActorRef) -> tuple[FrameRef, str] | None:
    """Actual cockpit occupancy, never guessed from account, map or assigned Frame alone."""
    if actor.kind == "pilot":
        place = next((x for x in state.placements if x.actor == actor), None)
        if place is None:
            return None
        occupied = occupied_frame(place)
        return (
            (FrameRef(owner=occupied[0], instance=occupied[1]), place.source_event)
            if occupied
            else None
        )
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        body = harpy(state, actor)
        if body.linked:
            event = (
                body.physical_source_event
                or body.condition_event
                or getattr(body, "source_event", None)
            )
            if event:
                return FrameRef(owner=actor, instance=body.frame_instance), event
    return None


def frame_actor(state: GameState, target: FrameRef) -> ActorRef:
    """A retained original Frame has one vessel identity through proved same-person birth."""
    if target.owner.kind == "pilot":
        from girlframe.engine.m3_tag_permissions import conversion

        candidates = [
            x
            for x in state.harpy_states
            if x.alive and x.origin == target.owner and x.frame_instance == target.instance
        ]
        if len(candidates) > 1:
            raise ValueError("Recover the original Frame's unique actual conversion owner")
        if candidates:
            current = ActorRef(kind="external_pilot", entity=candidates[0].id)
            conversion(state, current)
            return current
    return target.owner


def same_frame(state: GameState, left: FrameRef, right: FrameRef) -> bool:
    return left.instance == right.instance and frame_actor(state, left) == frame_actor(state, right)


def linked(state: GameState, target: FrameRef) -> tuple[tuple[ActorRef, str], ...]:
    result: list[tuple[ActorRef, str]] = []
    for place in state.placements:
        if place.mode == "piloting" and occupied_frame(place) == (target.owner, target.instance):
            result.append((place.actor, place.source_event))
    from girlframe.engine.m3_harpy_defeat import harpy

    refs = [ActorRef(kind="external_pilot", entity=x.id) for x in state.harpy_states if x.alive]
    refs += [
        ActorRef(kind="external_pilot", entity=x.id)
        for x in state.native_harpies
        if ActorRef(kind="external_pilot", entity=x.id) not in refs
    ]
    for ref in refs:
        body = harpy(state, ref)
        if body.linked and same_frame(
            state, target, FrameRef(owner=ref, instance=body.frame_instance)
        ):
            source = (
                body.physical_source_event
                or body.condition_event
                or getattr(body, "source_event", None)
            )
            if source:
                result.append((ref, source))
    return tuple(result)


def require_creator(state: GameState, actor: ActorRef, grant: str | None = None) -> None:
    owned = held(state, actor, VIRUS)
    if owned is None or grant is not None and owned.id != grant:
        raise ValueError(
            "Use the original actually held Compliance Virus ability and current Frame"
        )


def infect(
    original: GameState,
    actor: ActorRef,
    target: FrameRef,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    account: str,
) -> GameState:
    state = clone(original)
    require_creator(state, actor)
    own = resolve(state, actor, bindings, require_current_profile=False)
    position = cockpit(state, actor)
    grant = held(state, actor, VIRUS)
    assigned = frame(state, actor)
    if (
        position is None
        or not same_frame(state, position[0], target)
        or not event
        or not account.strip()
        or grant is None
        or assigned is None
    ):
        raise ValueError("Infect only the actual Frame whose cockpit your original body occupies")
    if any(
        x.creator == actor and x.target == target and x.purged_event is None
        for x in records(state, Strain)
    ):
        raise ValueError("This actual original strain already infects that Frame")
    created = Strain(
        id=identity("strain", actor.token, target.instance, event),
        creator=actor,
        controller=own.controller,
        grant=grant.id,
        creator_frame=assigned,
        target=target,
        source_event=event,
        cockpit_source=position[1],
        account=account,
    )
    put(state, created)
    return spread(state, bindings, event, strains=(created.id,))


def spread(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    *,
    strains: tuple[str, ...] = (),
    actors: tuple[ActorRef, ...] = (),
) -> GameState:
    """Called only after a real canonical link transition, also at actual initial infection."""
    state = clone(original)
    if not event or not (strains or actors):
        raise ValueError("Scope transmission to actual new strain or actual new linker")
    for strain in records(state, Strain):
        if strain.purged_event is not None or strains and strain.id not in strains:
            continue
        for actor, source in linked(state, strain.target):
            if actors and (actor not in actors or source != event):
                continue
            if any(
                x.strain == strain.id and x.actor == actor and x.purged_event is None
                for x in records(state, InfectedPerson)
            ):
                continue
            actual = resolve(state, actor, bindings, require_current_profile=False)
            put(
                state,
                InfectedPerson(
                    id=identity("person", strain.id, actor.token, event),
                    strain=strain.id,
                    actor=actor,
                    controller=actual.controller,
                    source_event=event,
                    link_source=source,
                ),
            )
    return state


def touch_purge(original: GameState, value: Purge, event: str) -> GameState:
    state = clone(original)
    require_creator(state, value.creator, value.grant)
    infection = record(state, InfectedPerson, value.person_infection or "")
    strain = record(state, Strain, value.strain)
    if (
        value.kind != "girl"
        or infection.actor != value.target
        or infection.strain != strain.id
        or strain.grant != value.grant
        or infection.purged_event
        or not value.contact_confirmed
        or value.review_event != event
        or value.phase != "order"
    ):
        raise ValueError(
            "Actual touch purge requires the original infection and factual source review"
        )
    put(state, infection.model_copy(update={"purged_event": event}))
    put(state, value)
    return state


def frame_purge(
    original: GameState, value: Purge, bindings: tuple[ProfileBinding, ...]
) -> GameState:
    state = clone(original)
    require_creator(state, value.creator, value.grant)
    strain = record(state, Strain, value.strain)
    actual = linked(state, strain.target)
    if (
        value.kind != "frame"
        or value.phase != "punishment"
        or strain.purged_event
        or strain.grant != value.grant
        or value.target_frame != strain.target
        or len(actual) != 1
        or actual[0][0] != value.target
    ):
        raise ValueError(
            "Purge the actual infected Frame against its actual currently linked original"
        )
    if value.effect_event is None or value.target is None:
        raise ValueError("Actual printed fixed11 needs its real Pilot and source event")
    actual_target = resolve(state, value.target, bindings, require_current_profile=False)
    if value.target != value.creator and (
        actual_target.rules in ("girl_frame", "handler_girl", "npc", "handler", "director")
        or actual_target.girl == "harpy"
    ):
        state = make_helpless(state, value.target, value.creator, value.effect_event)
    put(state, strain.model_copy(update={"purged_event": value.effect_event}))
    put(state, value)
    put(
        state,
        PainRestraint(
            id="pain:" + value.id,
            purge=value.id,
            actor=value.target,
            inflictor=value.creator,
            source_event=value.effect_event,
        ),
    )
    return state


def complete(original: GameState, purge: str, event: str) -> GameState:
    state = clone(original)
    value = record(state, Purge, purge)
    if value.phase == "complete":
        return state
    if value.phase not in ("punishment", "awaiting_order") or not event:
        raise ValueError("Complete only the actual owned order or immediate Punishment chain")
    put(
        state,
        value.model_copy(
            update={"phase": "complete", "completion_event": event, "revision": value.revision + 1}
        ),
    )
    for pain in records(state, PainRestraint):
        if pain.purge == purge and pain.active:
            put(state, pain.model_copy(update={"active": False, "ended_event": event}))
    # Actual Helpless is deliberately preserved for normal source-backed recovery.
    return state


def restrained(state: GameState, actor: ActorRef) -> PainRestraint | None:
    return next((x for x in records(state, PainRestraint) if x.actor == actor and x.active), None)


def purge_vacant_frame(original: GameState, value: Purge, event: str) -> GameState:
    state = clone(original)
    require_creator(state, value.creator, value.grant)
    strain = record(state, Strain, value.strain)
    if (
        value.kind != "frame"
        or value.target is not None
        or value.role_case is not None
        or value.vacancy_reviewed_event != event
        or not value.vacancy_proposed_event
        or linked(state, strain.target)
        or strain.purged_event
        or value.phase != "complete"
    ):
        raise ValueError("Only source-owned reviewed actual vacancy permits a purge with no Pilot")
    put(state, strain.model_copy(update=dict(purged_event=event)))
    put(state, value)
    return state
