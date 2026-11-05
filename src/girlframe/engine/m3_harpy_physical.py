"""Actual Harpy-linked vessels, Frame consent and extraction without proxy Pilot placements."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_physical_state import ExtractionConsent, FrameLock


def locked(state: GameState, actor: ActorRef) -> FrameLock | None:
    body = harpy(state, actor)
    values = [
        x
        for x in state.frame_locks
        if x.owner == actor and x.frame_instance == body.frame_instance and x.active
    ]
    if len(values) > 1:
        raise ValueError("Recover the actual Harpy Frame's single source-bound cockpit lock")
    return values[0] if values else None


def _source(state: GameState, actor: ActorRef, event: str, account: str) -> None:
    if (
        actor.kind != "external_pilot"
        or not event.strip()
        or not account.strip()
        or len(account) > 1200
    ):
        raise ValueError("Use the actual Harpy identity, source event and physical account")
    body = harpy(state, actor)
    if getattr(body, "alive", True) is False or (
        state.world is not None
        and any(x.id == actor.entity and not x.alive for x in state.world.pilots)
    ):
        raise ValueError(
            "The original Harpy body ended; a new role cannot perform its physical actions"
        )
    if any(x.get("kind") == "harpy_physical" and x.get("event") == event for x in state.facts):
        raise ValueError("This actual physical source already owns its original effect")


def _fact(state: GameState, actor: ActorRef, event: str, account: str, operation: str) -> GameState:
    state.facts.append(
        dict(
            kind="harpy_physical",
            actor=actor.model_dump_json(),
            event=event,
            account=account,
            operation=operation,
        )
    )
    return state


def lock(state: GameState, actor: ActorRef, event: str, account: str) -> GameState:
    _source(state, actor, event, account)
    body = harpy(state, actor)
    if not body.linked or body.custody != "free" or locked(state, actor) is not None:
        raise ValueError("Subsumption requires the actual Harpy's linked, currently unlocked Frame")
    changed = update(state, actor, subsumed=True, vitals_active=False, physical_source_event=event)
    changed.frame_locks.append(
        FrameLock(
            id="cockpit:" + event,
            owner=actor,
            subject=actor,
            frame_instance=body.frame_instance,
            source_event=event,
        )
    )
    return _fact(changed, actor, event, account, "subsumed")


def consent(
    state: GameState, actor: ActorRef, controller: int, event: str, account: str, *, allowed: bool
) -> GameState:
    _source(state, actor, event, account)
    body, gate = harpy(state, actor), locked(state, actor)
    if gate is None or body.controller != controller or type(allowed) is not bool:
        raise ValueError(
            "Only this actual Harpy's human Frame voice may allow or refuse extraction"
        )
    changed = GameState.model_validate_json(state.model_dump_json())
    response = ExtractionConsent(
        actor=actor, controller=controller, allowed=allowed, source_event=event, account=account
    )
    changed.frame_locks = [
        x.model_copy(update={"consents": x.consents + (response,)}) if x.id == gate.id else x
        for x in changed.frame_locks
    ]
    return _fact(changed, actor, event, account, "extraction_consent")


def open_frame(
    state: GameState, actor: ActorRef, controller: int, event: str, account: str
) -> GameState:
    _source(state, actor, event, account)
    gate, body = locked(state, actor), harpy(state, actor)
    if gate is None or controller != body.controller:
        raise ValueError("Only this actual Harpy's human Frame voice may open its locked cockpit")
    changed = GameState.model_validate_json(state.model_dump_json())
    changed.frame_locks = [
        x.model_copy(update={"active": False, "released_event": event}) if x.id == gate.id else x
        for x in changed.frame_locks
    ]
    return _fact(changed, actor, event, account, "frame_opened")


def extract(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    extractor: ActorRef,
    event: str,
    account: str,
    *,
    contact_proven: bool = False,
) -> GameState:
    _source(state, actor, event, account)
    body = harpy(state, actor)
    helper = resolve(state, extractor, bindings, require_current_profile=False)
    if not body.linked or extractor == actor or helper.alive is False or body.custody != "free":
        raise ValueError("An actual other person extracts this original linked Harpy body")
    if helper.ref.kind == "pilot":
        place = next((x for x in state.placements if x.actor == helper.ref), None)
        cell = place.girl_cell if place else None
        if place is None or place.incapacitated or place.subsumed or place.custody is not None:
            raise ValueError("The actual extractor must be physically able and free to help")
    elif helper.ref.kind == "external_pilot":
        other = harpy(state, extractor)
        if other.body_incapacitated or other.subsumed or other.custody != "free":
            raise ValueError("The actual extractor must be physically able and free to help")
        cell = other.cell
    else:
        cell = helper.cell
    if cell is not None and body.frame_cell is not None and cell != body.frame_cell:
        raise ValueError("The actual extractor is not at this original Frame")
    if (cell is None or body.frame_cell is None) and not contact_proven:
        raise ValueError("Confirm actual contact when original positions are unknown")
    gate = locked(state, actor)
    if gate is not None:
        response = gate.consents[-1] if gate.consents else None
        if response is None or not response.allowed or response.used_event is not None:
            raise ValueError(
                "The actual Frame's latest explicit positive extraction consent is required"
            )
    changed = update(
        state,
        actor,
        linked=False,
        cell=body.frame_cell,
        subsumed=False,
        physical_source_event=event,
    )
    if gate is not None:
        consents = gate.consents[:-1] + (
            gate.consents[-1].model_copy(update={"used_event": event}),
        )
        changed.frame_locks = [
            x.model_copy(update={"consents": consents}) if x.id == gate.id else x
            for x in changed.frame_locks
        ]
    return _fact(changed, actor, event, account, "actual_extraction")


def recover(state: GameState, actor: ActorRef, event: str, account: str) -> GameState:
    _source(state, actor, event, account)
    body = harpy(state, actor)
    if (
        body.subsumed
        or body.linked
        and not body.vitals_active
        or body.vitals_active
        and not body.body_incapacitated
    ):
        raise ValueError(
            "First extract the actual inactive body, then establish real medical recovery"
        )
    changed = update(
        state, actor, vitals_active=True, body_incapacitated=False, physical_source_event=event
    )
    return _fact(changed, actor, event, account, "actual_medical_recovery")
