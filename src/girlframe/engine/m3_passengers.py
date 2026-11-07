"""Actual paired cockpit boarding, with one physical authority for each original body."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_passenger_state import Passenger


def same_body(state: GameState, first: ActorRef, second: ActorRef) -> bool:
    if first == second:
        return True
    if first.kind == second.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, first) and same_handler_body(state, second)
    return False


def passenger_view(state: GameState, actor: ActorRef) -> Passenger | None:
    values = [
        x for x in state.passengers if same_body(state, x.actor, actor) and x.state == "boarded"
    ]
    if actor.kind == "pilot":
        body = next((x for x in state.placements if x.actor == actor), None)
        values = [
            x
            for x in values
            if body is not None
            and (body.occupied_frame_owner, body.occupied_frame_instance, body.mode)
            == (x.carrier, x.frame, "inside_frame")
        ]
    if len(values) > 1:
        raise ValueError("Recover this original body's one actual occupied cockpit")
    if not values:
        return None
    value = values[0]
    if actor.kind == "pilot":
        body = next((x for x in state.placements if x.actor == actor), None)
        if body is None or (
            body.occupied_frame_owner,
            body.occupied_frame_instance,
            body.mode,
        ) != (value.carrier, value.frame, "inside_frame"):
            # Placement owns Pilot bodies; a real later exit never leaves a phantom passenger.
            return None
    return value


def _save(state: GameState, value: Passenger) -> None:
    state.passengers = [x for x in state.passengers if x.id != value.id] + [value]


def body_ready(state: GameState, actor: ActorRef) -> bool:
    if actor.kind == "pilot":
        body = next((x for x in state.placements if x.actor == actor), None)
        return bool(
            body is not None
            and not body.incapacitated
            and not body.subsumed
            and body.vitals_active
            and body.custody is None
        )
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy
        from girlframe.engine.m3_janus import find

        if find(state, actor) is not None:
            return False  # Independent Core boarding needs its actual current hardware rights.
        try:
            actual = harpy(state, actor)
        except ValueError:
            return False
        return not actual.body_incapacitated and not actual.subsumed and actual.vitals_active
    return True


def board(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    value: Passenger,
    event: str,
    account: str,
) -> GameState:
    """Trusted source service proves the carrier invitation and original guest acceptance."""
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical import cockpit_exit, cockpit_lock

    if (
        not event
        or not account.strip()
        or not value.accepted_event
        or value.actor == value.carrier
        or value.state != "proposed"
        or passenger_view(original, value.actor) is not None
        or not body_ready(original, value.actor)
    ):
        raise ValueError("Board only after both actual source humans accept this original guest")
    guest = resolve(original, value.actor, bindings, require_current_profile=False)
    carrier = resolve(original, value.carrier, bindings, require_current_profile=False)
    if (
        guest.controller != value.controller
        or not body_ready(original, value.carrier)
        or guest.offstage_source
        or carrier.offstage_source
        or carrier.frame_instance != value.frame
        or carrier.inside_frame is not True
        or carrier.occupied_frame_instance not in (None, value.frame)
        or carrier.frame_scrapped
        or carrier.piloting is False
        and carrier.subsumed
        or guest.subsumed
        or guest.vitals_active is False
        or guest.custody not in (None, "free")
        or cockpit_lock(original, value.carrier, value.frame) is not None
        or guest.cell is not None
        and carrier.cell is not None
        and guest.cell != carrier.cell
    ):
        raise ValueError(
            "Actual unlocked source cockpit, free bodies and real contact are required"
        )
    if (
        guest.position_sha256 or guest.source_sha256
    ) != value.position_sha256 or carrier.source_sha256 != value.carrier_sha256:
        raise ValueError("STALE_PASSENGER: review the actual current bodies and carrier Frame")
    state = GameState.model_validate_json(original.model_dump_json())
    if value.actor.kind == "pilot":
        placement = next((x for x in state.placements if x.actor == value.actor), None)
        if placement is None:
            raise ValueError("Record the actual original Girl's body before ordinary boarding")
        if placement.incapacitated or placement.custody is not None:
            raise ValueError("This voluntary boarding cannot manufacture rescue or custody release")
        if placement.mode != "outside_frame":
            state = cockpit_exit(state, bindings, value.actor, event, account)
            placement = next(x for x in state.placements if x.actor == value.actor)
        placed = placement.model_copy(
            update=dict(
                mode="inside_frame",
                girl_cell=carrier.cell,
                occupied_frame_owner=value.carrier,
                occupied_frame_instance=value.frame,
                source_event=event,
                account=account,
            )
        )
        state.placements = [placed if x.actor == value.actor else x for x in state.placements]
    elif value.actor.kind == "external_pilot" and guest.girl == "harpy":
        from girlframe.engine.m3_harpy_defeat import update

        state = update(
            state, value.actor, linked=False, cell=carrier.cell, physical_source_event=event
        )
    elif value.actor.kind == "external_pilot":
        raise ValueError("Establish this actual guest's independent physical body port first")
    boarded = value.model_copy(
        update=dict(
            state="boarded",
            source_event=event,
            cell=carrier.cell,
            account=account,
            revision=value.revision + 1,
        )
    )
    _save(state, boarded)
    state.facts.append(
        dict(
            kind="call_guest_boarded",
            passenger=value.id,
            event=event,
            actor=value.actor.model_dump_json(),
            carrier=value.carrier.model_dump_json(),
            frame=value.frame,
        )
    )
    return state


def subsume(original: GameState, identity: str, event: str, account: str) -> GameState:
    from girlframe.engine.m3_physical import cockpit_lock
    from girlframe.engine.m3_physical_state import FrameLock

    value = next((x for x in original.passengers if x.id == identity), None)
    if (
        value is None
        or passenger_view(original, value.actor) != value
        or value.subsumed
        or not event
        or not account.strip()
        or cockpit_lock(original, value.carrier, value.frame) is not None
    ):
        raise ValueError("Subsume only this actual guest inside the actual unlocked occupied Frame")
    state = GameState.model_validate_json(original.model_dump_json())
    changed = value.model_copy(
        update=dict(
            subsumed=True,
            vitals_active=False,
            choice_event=event,
            revision=value.revision + 1,
        )
    )
    _save(state, changed)
    state.frame_locks.append(
        FrameLock(
            id="call-cockpit:" + event,
            owner=value.carrier,
            subject=value.actor,
            frame_instance=value.frame,
            source_event=event,
        )
    )
    if value.actor.kind == "pilot":
        state.placements = [
            x.model_copy(
                update=dict(
                    subsumed=True,
                    vitals_active=False,
                    source_event=event,
                    account=account,
                )
            )
            if x.actor == value.actor
            else x
            for x in state.placements
        ]
    elif value.actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import update

        state = update(
            state, value.actor, subsumed=True, vitals_active=False, physical_source_event=event
        )
    return state


def frame_controller(state: GameState, value: Passenger) -> int:
    if value.carrier.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        body = harpy(state, value.carrier)
        if body.frame_instance != value.frame or getattr(body, "alive", True) is False:
            raise ValueError("Recover the actual living Harpy Frame's voice")
        return body.controller
    from girlframe.engine.m3_physical import frame_voice

    return frame_voice(state, value.carrier, value.frame)


def consent(
    original: GameState, identity: str, controller: int, allowed: bool, event: str, account: str
) -> GameState:
    from girlframe.engine.m3_physical import cockpit_lock
    from girlframe.engine.m3_physical_state import ExtractionConsent

    value = next((x for x in original.passengers if x.id == identity), None)
    if value is None or passenger_view(original, value.actor) != value:
        raise ValueError("Use this actual original guest and occupied Frame")
    gate = cockpit_lock(original, value.carrier, value.frame)
    if gate is None or frame_controller(original, value) != controller or not account.strip():
        raise ValueError("Only the actual current Frame voice responds about extraction")
    state = GameState.model_validate_json(original.model_dump_json())
    answer = ExtractionConsent(
        actor=value.actor,
        controller=controller,
        allowed=allowed,
        source_event=event,
        account=account,
    )
    state.frame_locks = [
        x.model_copy(update={"consents": (*x.consents, answer)}) if x.id == gate.id else x
        for x in state.frame_locks
    ]
    _save(state, value.model_copy(update={"consent_event": event, "revision": value.revision + 1}))
    return state


def leave(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    actor: ActorRef,
    event: str,
    account: str,
    *,
    extraction: bool = False,
) -> GameState:
    from girlframe.engine.m3_actors import frame_position, resolve
    from girlframe.engine.m3_physical import cockpit_lock

    value = next((x for x in original.passengers if x.id == identity), None)
    if value is None or passenger_view(original, value.actor) != value or not account.strip():
        raise ValueError("Use this actual occupied original guest body")
    operator = resolve(original, actor, bindings, require_current_profile=False)
    patient = resolve(original, value.actor, bindings, require_current_profile=False)
    if patient.custody not in (None, "free"):
        raise ValueError(
            "Resolve this actual body's custody/protective hold before extraction or departure"
        )
    cell = frame_position(original, value.carrier, value.frame, fallback=value.cell)
    if extraction:
        same_cell = operator.cell is not None and cell is not None and operator.cell == cell
        at_own_cockpit = (
            actor == value.carrier
            and operator.inside_frame is True
            and operator.occupied_frame_instance in (None, value.frame)
        )
        if (
            same_body(original, actor, value.actor)
            or operator.offstage_source
            or not (same_cell or at_own_cockpit)
        ):
            raise ValueError("Another actual role at the source cockpit performs real extraction")
    elif not same_body(original, actor, value.actor) or value.subsumed or not value.vitals_active:
        raise ValueError("An actual extractor is required for this subsumed or inactive body")
    gate = cockpit_lock(original, value.carrier, value.frame)
    state = GameState.model_validate_json(original.model_dump_json())
    if gate is not None:
        answer = next((x for x in reversed(gate.consents) if x.actor == value.actor), None)
        if answer is None or not answer.allowed or answer.used_event is not None:
            raise ValueError("FRAME_CONSENT_REQUIRED: the actual Frame must permit extraction")
        state.frame_locks = [
            x.model_copy(
                update={
                    "consents": tuple(
                        y.model_copy(update={"used_event": event}) if y == answer else y
                        for y in x.consents
                    )
                }
            )
            if x.id == gate.id
            else x
            for x in state.frame_locks
        ]
    if value.actor.kind == "pilot":
        from girlframe.engine.m3_a_bomb import exit_fact

        prior = next(x for x in state.placements if x.actor == value.actor)
        if cell is not None:
            exit_fact(state, value.actor, prior.vessel_id, value.frame, value.carrier, cell, event)
        state.placements = [
            x.model_copy(
                update=dict(
                    mode="outside_frame",
                    occupied_frame_owner=None,
                    occupied_frame_instance=None,
                    girl_cell=cell,
                    subsumed=False,
                    source_event=event,
                    account=account,
                )
            )
            if x.actor == value.actor
            else x
            for x in state.placements
        ]
    elif value.actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import update

        state = update(
            state, value.actor, linked=False, cell=cell, subsumed=False, physical_source_event=event
        )
    elif state.world and value.actor.kind == "npc" and cell is not None:
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"cell": cell}) if x.id == value.actor.entity else x
                    for x in state.world.npcs
                )
            }
        )
    elif state.world and value.actor.kind == "gorgon":
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(
                    x.model_copy(update={"cell": cell, "position_event": event})
                    if x.id == value.actor.entity
                    else x
                    for x in state.world.gorgons
                )
            }
        )
    _save(
        state,
        value.model_copy(
            update=dict(
                state="left",
                cell=cell,
                subsumed=False,
                left_event=event,
                revision=value.revision + 1,
            )
        ),
    )
    state.facts.append(
        dict(
            kind="call_guest_left",
            passenger=identity,
            event=event,
            actor=actor.model_dump_json(),
            extracted=str(extraction),
        )
    )
    if state.external_poses or state.leviathan_arrivals:
        from girlframe.engine.m3_leviathan_arrival import record_existing_body_position

        state = record_existing_body_position(state, value.actor, cell, event, account)
    return state
