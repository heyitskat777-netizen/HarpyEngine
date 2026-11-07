"""Original physical facts need actual ownership and a distinct review source."""

import json

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, ActorView, ProfileBinding
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.engine.m3_physical_state import (
    EscortJourney,
    ExtractionConsent,
    FrameLock,
    InitialPlacement,
    Mode,
    ParkedFrame,
    Placement,
)


def validate(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    proposal: InitialPlacement,
) -> ActorView:
    proposal = InitialPlacement.model_validate_json(proposal.model_dump_json())
    actor = resolve(state, proposal.actor, bindings, require_current_profile=False)
    if actor.rules != "girl_frame" or actor.frame_instance != proposal.frame_instance:
        raise ValueError("STALE_PLACEMENT: recover the actual original character and Frame")
    previous = next((x for x in state.placements if x.actor == proposal.actor), None)
    if previous is not None:
        replacement = previous.frame_instance != actor.frame_instance
        if (
            previous.occupied_frame_owner is not None
            or previous.custody is not None
            or any(
                (x.active and proposal.actor in (x.traveler, x.supervisor))
                or proposal.actor in x.offstage_refs
                for x in state.escort_journeys
            )
            or proposal.mode != previous.mode
            or (replacement and previous.mode != "outside_frame")
            or (previous.girl_cell is not None and previous.girl_cell != proposal.girl_cell)
            or (
                not replacement
                and previous.frame_cell is not None
                and previous.frame_cell != proposal.frame_cell
            )
            or (
                not replacement
                and previous.girl_cell is not None
                and previous.frame_cell is not None
            )
        ):
            raise ValueError(
                "Initial placement cannot reset or move an already placed body; "
                "confirm only genuinely unknown facts"
            )
    if state.world is None or any(
        not state.world.board.contains(cell) for cell in (proposal.girl_cell, proposal.frame_cell)
    ):
        raise ValueError("Record both actual positions on the current canonical map")
    if proposal.mode == "piloting" and actor.frame_scrapped:
        raise ValueError(
            "A scrapped Frame cannot be piloted; occupancy is a separate physical fact"
        )
    return actor


def initial(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    proposal: InitialPlacement,
    vessel: str,
    proposed_event: str,
    source_event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    proposal = InitialPlacement.model_validate_json(proposal.model_dump_json())
    validate(state, bindings, proposal)
    previous = next((x for x in state.placements if x.actor == proposal.actor), None)
    if previous is not None:
        _save(
            state,
            previous.model_copy(
                update=dict(
                    frame_instance=proposal.frame_instance,
                    girl_cell=proposal.girl_cell,
                    frame_cell=proposal.frame_cell,
                    source_event=source_event,
                    account=proposal.account,
                )
            ),
        )
        return _finish(
            state, proposal.actor, source_event, proposal.account, "unknown_physical_facts_recorded"
        )
    if any(x.vessel_id == vessel for x in state.placements):
        raise ValueError("An initial vessel cannot be assigned to a different actual character")
    state.placements.append(
        Placement(
            actor=proposal.actor,
            vessel_id=vessel,
            frame_instance=proposal.frame_instance,
            girl_cell=proposal.girl_cell,
            frame_cell=proposal.frame_cell,
            mode=proposal.mode,
            incapacitated=state.sheets[proposal.actor.entity].medical_state != "fit",
            proposed_event=proposed_event,
            source_event=source_event,
            account=proposal.account,
        )
    )
    return state


def _source(state: GameState, event: str, account: str, actor: ActorRef) -> None:
    if not event.strip() or not account.strip() or len(account) > 1200:
        raise ValueError("Record the actual physical source and account in 1–1200 characters")
    if any(
        x.get("kind") == "physical_operation"
        and x.get("source_event") == event
        and x.get("actor") == actor.model_dump_json()
        for x in state.facts
    ):
        raise ValueError("This physical source has already been applied")


def _save(state: GameState, placement: Placement) -> None:
    placement = Placement.model_validate_json(placement.model_dump_json())
    state.passengers = [
        x.model_copy(
            update=dict(
                subsumed=placement.subsumed,
                vitals_active=placement.vitals_active,
                revision=x.revision + 1,
            )
        )
        if x.actor == placement.actor
        and x.state == "boarded"
        and occupied_frame(placement) == (x.carrier, x.frame)
        and (x.subsumed != placement.subsumed or x.vitals_active != placement.vitals_active)
        else x
        for x in state.passengers
    ]
    state.passengers = [
        x.model_copy(
            update=dict(
                state="left",
                cell=placement.girl_cell,
                subsumed=False,
                left_event=placement.source_event,
                vitals_active=placement.vitals_active,
                revision=x.revision + 1,
            )
        )
        if x.actor == placement.actor
        and x.state == "boarded"
        and occupied_frame(placement) != (x.carrier, x.frame)
        else x
        for x in state.passengers
    ]
    state.placements = [placement if x.actor == placement.actor else x for x in state.placements]


def _finish(state: GameState, actor: ActorRef, event: str, account: str, kind: str) -> GameState:
    state.facts.append(
        dict(
            kind="physical_operation",
            operation=kind,
            actor=actor.model_dump_json(),
            source_event=event,
            account=account,
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def original_placement(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
    *,
    prior_event: str | None = None,
    mode: Mode = "outside_frame",
) -> tuple[GameState, Placement]:
    """A printed physical consequence can establish an unknown legacy body, never coordinates."""
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings, require_current_profile=False)
    if actor.kind != "pilot" or view.frame_instance is None:
        raise ValueError("Use the actual original Girl and assigned Frame")
    placement = next((x for x in state.placements if x.actor == actor), None)
    if placement is not None:
        return state, placement
    if not prior_event or prior_event == source_event:
        raise ValueError("An unplaced original body needs its actual distinct prior source")
    placement = Placement(
        actor=actor,
        vessel_id="vessel:" + actor.token,
        frame_instance=view.frame_instance,
        girl_cell=None,
        frame_cell=None,
        mode=mode,
        incapacitated=state.sheets[actor.entity].medical_state != "fit",
        proposed_event=prior_event,
        source_event=source_event,
        account=account,
    )
    state.placements.append(placement)
    return state, placement


def occupied_frame(placement: Placement) -> tuple[ActorRef, str] | None:
    if placement.mode == "outside_frame":
        return None
    return (
        placement.occupied_frame_owner or placement.actor,
        placement.occupied_frame_instance or placement.frame_instance,
    )


def cockpit_lock(state: GameState, owner: ActorRef, frame: str) -> FrameLock | None:
    active = [
        x for x in state.frame_locks if x.active and x.owner == owner and x.frame_instance == frame
    ]
    if len(active) > 1:
        raise ValueError("Recover the inconsistent actual cockpit lock")
    return active[0] if active else None


def _leave(state: GameState, placement: Placement, source_event: str, account: str) -> Placement:
    occupied = occupied_frame(placement)
    if occupied is not None:
        lock = cockpit_lock(state, *occupied)
        if lock is not None:
            latest = next((x for x in reversed(lock.consents) if x.actor == placement.actor), None)
            if latest is None or not latest.allowed or latest.used_event is not None:
                raise ValueError(
                    "FRAME_CONSENT_REQUIRED: the actual Frame must consent to extraction"
                )
            changed = lock.model_copy(
                update={
                    "consents": tuple(
                        x.model_copy(update={"used_event": source_event}) if x == latest else x
                        for x in lock.consents
                    )
                }
            )
            state.frame_locks = [changed if x.id == lock.id else x for x in state.frame_locks]
    cell = placement.girl_cell
    if occupied is not None:
        owner, instance = occupied
        cell = frame_position(state, owner, instance, fallback=placement.girl_cell)
        state.passengers = [
            x.model_copy(
                update=dict(
                    state="left",
                    cell=cell,
                    subsumed=False,
                    left_event=source_event,
                    vitals_active=placement.vitals_active,
                    revision=x.revision + 1,
                )
            )
            if x.actor == placement.actor
            and x.state == "boarded"
            and (x.carrier, x.frame) == occupied
            else x
            for x in state.passengers
        ]
    if occupied is not None and cell is not None:
        from girlframe.engine.m3_a_bomb import exit_fact

        exit_fact(
            state,
            placement.actor,
            placement.vessel_id,
            occupied[1],
            occupied[0],
            cell,
            source_event,
        )
    return placement.model_copy(
        update=dict(
            mode="outside_frame",
            girl_cell=cell,
            occupied_frame_owner=None,
            occupied_frame_instance=None,
            custody=None,
            subsumed=False,
            source_event=source_event,
            account=account,
        )
    )


def cockpit_exit(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if placement is None:
        raise ValueError("Record the actual body and occupancy before ordinary cockpit operations")
    if placement.custody is not None:
        raise ValueError("Resolve actual custody before voluntarily leaving this cockpit")
    if not placement.vitals_active or placement.incapacitated or placement.subsumed:
        raise ValueError("EXTRACTION_REQUIRED: another actual role must extract this body")
    if placement.mode == "outside_frame":
        raise ValueError("This actual body is already outside a Frame")
    _save(state, _leave(state, placement, source_event, account))
    return _finish(state, actor, source_event, account, "cockpit_exit")


def exchange_assigned_frame(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    old_sheet: PilotSheet,
    delivered_cell: tuple[int, int],
    source_event: str,
    account: str,
) -> GameState:
    """Trusted actual delivery resolver calls after installing the new reviewed Frame package."""
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    view = resolve(state, actor, bindings, require_current_profile=False)
    body = next((x for x in state.placements if x.actor == actor), None)
    old_instance = (
        old_sheet.frame_runtime.id
        if old_sheet.frame_runtime
        else "initial:" + str(actor.incarnation)
    )
    if (
        body is None
        or body.mode != "outside_frame"
        or body.occupied_frame_owner is not None
        or body.custody is not None
        or body.incapacitated
        or not body.vitals_active
        or old_sheet.owner != int(actor.entity)
        or old_sheet.character_id != actor.incarnation
        or body.frame_instance != old_instance
        or view.frame_instance in (None, old_instance)
        or delivered_cell != body.girl_cell
        or state.world is None
        or not state.world.board.contains(delivered_cell)
    ):
        raise ValueError(
            "Swap only the outside original Girl's actually delivered colocated new Frame"
        )
    if any(
        x.frame_instance in (old_instance, view.frame_instance) for x in state.parked_frames
    ) or any(
        x.actor != actor and x.frame_instance == view.frame_instance for x in state.placements
    ):
        raise ValueError(
            "Preserve each actual existing Frame identity without duplicating a parked body"
        )
    if any(
        (x.active and actor in (x.traveler, x.supervisor)) or actor in x.offstage_refs
        for x in state.escort_journeys
    ):
        raise ValueError(
            "Recover the actual original Girl from her existing supervised journey first"
        )
    state.parked_frames.append(
        ParkedFrame(
            owner=actor,
            frame_instance=old_instance,
            cell=body.frame_cell,
            source_event=source_event,
            prior_event=body.source_event,
            core_id=old_sheet.frame_runtime.core_id if old_sheet.frame_runtime else None,
            frame_json=old_sheet.model_dump_json(),
        )
    )
    _save(
        state,
        body.model_copy(
            update=dict(
                frame_instance=view.frame_instance,
                frame_cell=delivered_cell,
                source_event=source_event,
                account=account,
            )
        ),
    )
    return _finish(state, actor, source_event, account, "assigned_frame_exchanged")


def cockpit_enter(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
    *,
    pilot: bool,
    void_threshold: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    view = resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if placement is None or type(pilot) is not bool:
        raise ValueError("Record the actual original physical facts first")
    if pilot:
        from girlframe.engine.m3_frame_control import active_takeover

        if view.frame_shutdown:
            raise ValueError(
                "The captured Frame is still shut down; record its actual restart first"
            )
        if active_takeover(state, actor, placement.frame_instance) is not None:
            raise ValueError("Resolve this actual Frame's source takeover before ordinary piloting")
    if (
        not placement.vitals_active
        or placement.incapacitated
        or placement.subsumed
        or placement.custody is not None
    ):
        raise ValueError(
            "The body cannot voluntarily change cockpit control in its current condition"
        )
    if any(
        (x.active and actor in (x.traveler, x.supervisor)) or actor in x.offstage_refs
        for x in state.escort_journeys
    ):
        raise ValueError(
            "Record actual return or recovery from the supervised journey before cockpit entry"
        )
    if placement.frame_instance != view.frame_instance:
        raise ValueError("Recover the new assigned Frame's actual physical source first")
    active_void = next(
        (
            x
            for x in state.void_thresholds
            if x.actor == actor and x.stage not in ("prevented", "escaped", "converted", "dead")
        ),
        None,
    )
    if active_void is not None and void_threshold != active_void.id:
        raise ValueError("Resolve actual Void allure through its original transformation control")
    if occupied_frame(placement) not in (None, (actor, placement.frame_instance)):
        raise ValueError("Leave the other Girl's actual cockpit before entering your own Frame")
    if (
        placement.girl_cell is None
        or placement.frame_cell is None
        or placement.girl_cell != placement.frame_cell
    ):
        raise ValueError(
            "The actual Girl and assigned Frame must already be at the same known cell"
        )
    if cockpit_lock(state, actor, placement.frame_instance) is not None:
        raise ValueError("FRAME_LOCKED: the actual cockpit is closed")
    if pilot and (
        view.frame_scrapped or not any(x.family == "frame" and not x.damaged for x in view.assets)
    ):
        raise ValueError("The unavailable Frame cannot be piloted")
    mode = "piloting" if pilot else "inside_frame"
    if placement.mode == mode:
        raise ValueError("The body already has that actual cockpit control")
    _save(
        state,
        placement.model_copy(update=dict(mode=mode, source_event=source_event, account=account)),
    )
    if pilot:
        from girlframe.engine.m3_frame_control import recover_control

        state = recover_control(state, actor, placement.frame_instance, source_event)
    return _finish(state, actor, source_event, account, "cockpit_enter" if pilot else "cockpit_sit")


def escape_cockpit(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
    *,
    prior_event: str | None = None,
) -> GameState:
    """The printed Defeat escape changes occupancy, without a fabricated map journey."""
    state, placement = original_placement(
        original, bindings, actor, source_event, account, prior_event=prior_event
    )
    _source(state, source_event, account, actor)
    if not any(x.actor == actor for x in original.placements):
        placement = placement.model_copy(update={"mode": "inside_frame"})
        _save(state, placement)
    if placement.mode == "outside_frame":
        raise ValueError("The actual body is already outside the cockpit")
    _save(state, _leave(state, placement, source_event, account))
    return _finish(state, actor, source_event, account, "defeat_escape")


def rescue_to_cockpit(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    rescuer: ActorRef,
    source_event: str,
    account: str,
    *,
    prior_event: str | None = None,
) -> GameState:
    if actor == rescuer:
        raise ValueError("Another actual Girl must perform this rescue")
    state, placement = original_placement(
        original, bindings, actor, source_event, account, prior_event=prior_event
    )
    state, carrier = original_placement(
        state, bindings, rescuer, source_event, account, prior_event=prior_event
    )
    _source(state, source_event, account, actor)
    rescuer_view = resolve(state, rescuer, bindings, require_current_profile=False)
    if (
        rescuer_view.frame_scrapped
        or carrier.incapacitated
        or not carrier.vitals_active
        or not any(x.family == "frame" and not x.damaged for x in rescuer_view.assets)
    ):
        raise ValueError("The actual rescuer needs an available Frame and body")
    if not any(x.actor == rescuer for x in original.placements):
        carrier = carrier.model_copy(update={"mode": "piloting"})
        _save(state, carrier)
    elif (
        carrier.mode == "outside_frame"
        and carrier.custody is None
        and carrier.girl_cell is not None
        and carrier.girl_cell == carrier.frame_cell
        and carrier.frame_instance == rescuer_view.frame_instance
    ):
        carrier = carrier.model_copy(
            update=dict(mode="piloting", source_event=source_event, account=account)
        )
        _save(state, carrier)
    if occupied_frame(carrier) != (rescuer, rescuer_view.frame_instance):
        raise ValueError("The actual rescuer must already occupy her own Frame")
    if cockpit_lock(state, rescuer, carrier.frame_instance) is not None:
        raise ValueError("The actual rescuer's cockpit is locked")
    placement = _leave(state, placement, source_event, account)
    _save(
        state,
        placement.model_copy(
            update=dict(
                mode="inside_frame",
                girl_cell=carrier.frame_cell,
                occupied_frame_owner=rescuer,
                occupied_frame_instance=carrier.frame_instance,
                custody=None,
                source_event=source_event,
                account=account,
            )
        ),
    )
    return _finish(state, actor, source_event, account, "defeat_rescue")


def depart_supervised(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    supervisor: ActorRef,
    source_event: str,
    account: str,
    *,
    prior_event: str | None = None,
) -> GameState:
    state, placement = original_placement(
        original, bindings, actor, source_event, account, prior_event=prior_event
    )
    _source(state, source_event, account, actor)
    if actor == supervisor:
        raise ValueError("An actual different role supervises this departure")
    if any(
        x.guardian in (actor, supervisor)
        and x.protection_release_event is None
        and any(p.actor == x.actor and p.custody == x.guardian for p in state.placements)
        for x in state.void_thresholds
    ):
        raise ValueError("Actually release the existing protective hold before leaving on a trip")
    supervisor_view = resolve(state, supervisor, bindings, require_current_profile=False)
    if any(
        (x.active and {actor, supervisor} & {x.traveler, x.supervisor})
        or bool({actor, supervisor} & set(x.offstage_refs))
        for x in state.escort_journeys
    ):
        raise ValueError("Resolve the actual party's previous supervised journey first")
    if placement.custody is not None:
        raise ValueError("Resolve the original actual custody before a supervised departure")
    supervisor_origin = None
    if supervisor.kind == "pilot":
        state, supervisor_origin = original_placement(
            state, bindings, supervisor, source_event, account, prior_event=prior_event
        )
        if (
            supervisor_origin.custody is not None
            or supervisor_origin.incapacitated
            or not supervisor_origin.vitals_active
            or supervisor_origin.subsumed
        ):
            raise ValueError("The actual supervisor must be physically able to accompany the visit")
        supervisor_body = _leave(state, supervisor_origin, source_event, account)
        _save(state, supervisor_body.model_copy(update={"girl_cell": None}))
    elif supervisor_view.custody not in (None, "free"):
        raise ValueError("The actual captive supervisor cannot accompany this visit")
    state.escort_journeys.append(
        EscortJourney(
            id="escort:" + source_event + ":" + actor.token,
            traveler=actor,
            supervisor=supervisor,
            traveler_origin=placement,
            supervisor_origin=supervisor_origin,
            supervisor_cell=supervisor_view.cell,
            departure_event=source_event,
        )
    )
    placement = _leave(state, placement, source_event, account)
    _save(state, placement.model_copy(update=dict(girl_cell=None, custody=supervisor)))
    return _finish(state, actor, source_event, account, "supervised_departure")


def return_from_visit(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    origin: Placement,
    supervisor: ActorRef,
    source_event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if (
        placement is None
        or origin.actor != actor
        or placement.vessel_id != origin.vessel_id
        or placement.custody != supervisor
        or placement.mode != "outside_frame"
    ):
        raise ValueError("Return only the actual original body from its recorded supervisor")
    journey = next(
        (
            x
            for x in state.escort_journeys
            if x.active and x.traveler == actor and x.supervisor == supervisor
        ),
        None,
    )
    if journey is None or journey.traveler_origin != origin:
        raise ValueError("Return requires the original actual supervised journey source")
    supervisor_view = resolve(state, supervisor, bindings, require_current_profile=False)
    if journey.supervisor_origin is not None:
        current_supervisor = next((x for x in state.placements if x.actor == supervisor), None)
        if (
            current_supervisor is None
            or current_supervisor.vessel_id != journey.supervisor_origin.vessel_id
            or current_supervisor.mode != "outside_frame"
            or current_supervisor.girl_cell is not None
        ):
            raise ValueError("Recover the actual supervisor body before returning the party")
        _save(
            state,
            current_supervisor.model_copy(
                update=dict(
                    girl_cell=journey.supervisor_origin.girl_cell,
                    source_event=source_event,
                    account=account,
                )
            ),
        )
    elif supervisor.kind == "npc":
        npc = (
            next((x for x in state.world.npcs if x.id == supervisor.entity), None)
            if state.world
            else None
        )
        if npc is None or npc.cell != journey.supervisor_cell:
            raise ValueError("Recover the supervisor's changed original map source before return")
    elif supervisor.kind == "external_pilot" and any(
        x.id == supervisor.entity for x in state.harpy_states
    ):
        harpy = next(x for x in state.harpy_states if x.id == supervisor.entity)
        if harpy.cell != journey.supervisor_cell or harpy.custody != "free":
            raise ValueError(
                "Recover the actual original Harpy supervisor's position/custody before return"
            )
    elif supervisor.kind in ("external_pilot", "gorgon"):
        entities = (
            state.world.pilots
            if state.world and supervisor.kind == "external_pilot"
            else state.world.gorgons
            if state.world
            else ()
        )
        entity = next((x for x in entities if x.id == supervisor.entity), None)
        if entity is None or entity.cell != journey.supervisor_cell:
            raise ValueError("Recover the supervisor's changed original map source before return")
    if not supervisor_view.alive:
        raise ValueError("The original supervisor can no longer escort this actual return")
    state.escort_journeys = [
        x.model_copy(update={"active": False, "return_event": source_event})
        if x.id == journey.id
        else x
        for x in state.escort_journeys
    ]
    _save(
        state,
        placement.model_copy(
            update=dict(
                girl_cell=origin.girl_cell, custody=None, source_event=source_event, account=account
            )
        ),
    )
    return _finish(state, actor, source_event, account, "supervised_return")


def handler_rescue(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    handler: ActorRef,
    source_event: str,
    account: str,
    *,
    injured: bool = False,
    prior_event: str | None = None,
) -> GameState:
    if handler.kind != "handler" or type(injured) is not bool:
        raise ValueError("The actual Handler or their agents perform this rescue")
    state, placement = original_placement(
        original, bindings, actor, source_event, account, prior_event=prior_event
    )
    _source(state, source_event, account, actor)
    resolve(state, handler, bindings, require_current_profile=False)
    placement = _leave(state, placement, source_event, account)
    _save(
        state,
        placement.model_copy(
            update=dict(
                girl_cell=None,
                custody=handler,
                incapacitated=True if injured else placement.incapacitated,
            )
        ),
    )
    return _finish(state, actor, source_event, account, "handler_rescue")


def frame_voice(state: GameState, owner: ActorRef, frame_instance: str) -> int:
    from girlframe.engine.m3_janus import bound

    original_core = bound(state, owner, frame_instance)
    if original_core is not None:
        if not original_core.alive or not original_core.attached:
            raise ValueError("Recover this physical JANUS's actual attached living Core voice")
        return original_core.controller
    sheet = state.sheets.get(owner.entity)
    lock = next(
        (
            x
            for x in reversed(state.frame_locks)
            if x.owner == owner and x.frame_instance == frame_instance
        ),
        None,
    )
    same_character = sheet is not None and (
        sheet.character_id is None or sheet.character_id == owner.incarnation
    )
    frame = (
        (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(owner.incarnation))
        if sheet is not None
        else None
    )
    if not same_character or frame != frame_instance:
        if lock is None:
            raise ValueError("Recover the original actual Frame before its consent response")
        core_id = lock.core_id
    else:
        assert sheet is not None
        core_id = sheet.frame_runtime.core_id if sheet.frame_runtime else None
    harpy_core = next((x for x in state.harpy_states if x.id == core_id), None)
    if harpy_core is not None:
        if not harpy_core.alive:
            raise ValueError("The actual linked Core cannot give consent after its death")
        if (
            harpy_core.custody != "core"
            or harpy_core.core_frame_owner != owner
            or harpy_core.core_frame_instance != frame_instance
        ):
            raise ValueError("Recover the actual captured Harpy Core's original Frame binding")
        return harpy_core.controller
    if (
        same_character
        and frame == frame_instance
        and sheet is not None
        and sheet.frame in ("JANUS", "JANUS-B")
    ):
        raise ValueError("CORE_SETUP_REQUIRED: admit this original JANUS's actual Core first")
    if state.world is not None and core_id is not None:
        npc = next((x for x in state.world.npcs if x.id == core_id), None)
        if npc is not None:
            if not npc.alive:
                raise ValueError("The actual linked Core cannot give consent after its death")
            return int(npc.controller)
        core = next((x for x in state.world.pilots if x.id == core_id), None)
        if core is not None:
            if not core.alive:
                raise ValueError("The actual linked Core cannot give consent after its death")
            return int(core.controller)
    if state.handler is None:
        raise ValueError("The ordinary NPC Frame needs its current human Handler voice")
    return int(state.handler)


def lock_cockpit(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    view = resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if placement is None or occupied_frame(placement) != (actor, view.frame_instance):
        raise ValueError("Subsumption requires the Girl to be in her actual linked Frame's cockpit")
    if cockpit_lock(state, actor, placement.frame_instance) is not None:
        raise ValueError("This actual cockpit is already locked")
    runtime = state.sheets[actor.entity].frame_runtime
    state.frame_locks.append(
        FrameLock(
            id="cockpit:" + source_event,
            owner=actor,
            frame_instance=placement.frame_instance,
            subject=actor,
            source_event=source_event,
            core_id=runtime.core_id if runtime else None,
        )
    )
    _save(
        state,
        placement.model_copy(
            update=dict(
                subsumed=True, vitals_active=False, source_event=source_event, account=account
            )
        ),
    )
    return _finish(state, actor, source_event, account, "subsumed")


def consent_to_extract(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    controller: int,
    source_event: str,
    account: str,
    *,
    allowed: bool,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    occupied = occupied_frame(placement) if placement else None
    lock = cockpit_lock(state, *occupied) if occupied else None
    if lock is None or type(allowed) is not bool:
        raise ValueError("The actual occupied cockpit has no active extraction gate")
    if frame_voice(state, lock.owner, lock.frame_instance) != controller:
        raise ValueError("Only the actual Frame's human voice can give its extraction consent")
    consent = ExtractionConsent(
        actor=actor,
        controller=controller,
        allowed=allowed,
        source_event=source_event,
        account=account,
    )
    state.frame_locks = [
        x.model_copy(update={"consents": x.consents + (consent,)}) if x.id == lock.id else x
        for x in state.frame_locks
    ]
    return _finish(state, actor, source_event, account, "frame_extraction_consent")


def extract(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
) -> GameState:
    """A source-authorized extractor removes a body; consent never revives it."""
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if placement is None or placement.mode == "outside_frame":
        raise ValueError("The actual original body must still be inside its cockpit")
    _save(state, _leave(state, placement, source_event, account))
    return _finish(state, actor, source_event, account, "actual_extraction")


def open_cockpit(
    original: GameState,
    owner: ActorRef,
    frame_instance: str,
    controller: int,
    source_event: str,
    account: str,
) -> GameState:
    """An explicit Frame response opens its actual cockpit, even after its Pilot's career ends."""
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, owner)
    lock = cockpit_lock(state, owner, frame_instance)
    if lock is None or frame_voice(state, owner, frame_instance) != controller:
        raise ValueError("Only the actual Frame's human voice can open its active cockpit lock")
    state.frame_locks = [
        x.model_copy(update={"active": False, "released_event": source_event})
        if x.id == lock.id
        else x
        for x in state.frame_locks
    ]
    return _finish(state, owner, source_event, account, "frame_opens_cockpit")


def medical_recovery(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    source_event: str,
    account: str,
    *,
    restore_vitals: bool,
) -> GameState:
    """Record actual waking/medical help; it gives no repairs, resources or cockpit extraction."""
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, actor)
    resolve(state, actor, bindings, require_current_profile=False)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if placement is None or type(restore_vitals) is not bool:
        raise ValueError("Actual medical recovery needs the original recorded body and source")
    if placement.subsumed:
        raise ValueError(
            "Frame consent and actual extraction are required before this medical recovery"
        )
    if not placement.incapacitated and (placement.vitals_active or not restore_vitals):
        raise ValueError("This body has no matching incapacity or inactive vitals to recover")
    _save(
        state,
        placement.model_copy(
            update=dict(
                incapacitated=False,
                vitals_active=True if restore_vitals else placement.vitals_active,
                source_event=source_event,
                account=account,
            )
        ),
    )
    return _finish(state, actor, source_event, account, "actual_medical_recovery")


def interrupt_journeys(
    original: GameState,
    actor: ActorRef,
    source_event: str,
    account: str,
) -> GameState:
    """Career ending interrupts the trip; it cannot teleport its surviving counterpart home."""
    state = interrupt_protective_holds(original, actor, source_event, account)
    affected = [
        x
        for x in state.escort_journeys
        if (x.active and actor in (x.traveler, x.supervisor)) or actor in x.offstage_refs
    ]
    if not affected:
        return state
    _source(state, source_event, account, actor)
    for journey in affected:
        others = (journey.traveler, journey.supervisor) if journey.active else journey.offstage_refs
        remaining = tuple(x for x in others if x != actor)
        changed = journey.model_copy(
            update=dict(active=False, interruption_event=source_event, offstage_refs=remaining)
        )
        state.escort_journeys = [
            changed if x.id == journey.id else x for x in state.escort_journeys
        ]
        for placement in tuple(state.placements):
            if placement.actor == journey.traveler and placement.custody == journey.supervisor:
                _save(state, placement.model_copy(update={"custody": None}))
    return _finish(state, actor, source_event, account, "supervised_journey_interrupted")


def release_protective_hold(
    original: GameState,
    identity: str,
    guardian: ActorRef,
    source_event: str,
    account: str,
) -> GameState:
    """The actual current guardian controller releases only this exact source-created hold."""
    state = GameState.model_validate_json(original.model_dump_json())
    value = next((x for x in state.void_thresholds if x.id == identity), None)
    body = next((x for x in state.placements if value is not None and x.actor == value.actor), None)
    if (
        value is None
        or value.stage != "prevented"
        or value.guardian != guardian
        or value.protection_release_event is not None
        or body is None
        or body.custody != guardian
    ):
        raise ValueError("Release only the actual original guardian's still-active protective hold")
    _source(state, source_event, account, value.actor)
    cell = body.girl_cell
    try:
        actual = resolve(
            state,
            body.actor,
            tuple(
                ProfileBinding(
                    owner=x.owner,
                    character_id=x.character_id,
                    profile_revision=x.source_profile_revision,
                )
                for x in state.sheets.values()
                if x.character_id is not None
            ),
            require_alive=False,
            require_current_profile=False,
        )
        cell = actual.cell
    except ValueError:
        pass
    _save(
        state,
        body.model_copy(
            update=dict(custody=None, girl_cell=cell, source_event=source_event, account=account)
        ),
    )
    state.void_thresholds = [
        x.model_copy(update={"protection_release_event": source_event}) if x.id == identity else x
        for x in state.void_thresholds
    ]
    return _finish(state, value.actor, source_event, account, "protective_hold_released")


def interrupt_protective_holds(
    original: GameState, actor: ActorRef, source_event: str, account: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    for value in tuple(state.void_thresholds):
        if (
            value.guardian == actor
            and value.protection_release_event is None
            and any(x.actor == value.actor and x.custody == actor for x in state.placements)
        ):
            state = release_protective_hold(state, value.id, actor, source_event, account)
    return state


def recover_interrupted_journey(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    identity: str,
    participant: ActorRef,
    cell: tuple[int, int] | None,
    source_event: str,
    account: str,
) -> GameState:
    """A trusted actual-role controller records recovery, never an inferred or timed return."""
    state = GameState.model_validate_json(original.model_dump_json())
    _source(state, source_event, account, participant)
    journey = next((x for x in state.escort_journeys if x.id == identity), None)
    if (
        journey is None
        or journey.active
        or journey.interruption_event is None
        or participant not in journey.offstage_refs
    ):
        raise ValueError("Recover only an actual surviving participant of the interrupted journey")
    actual = resolve(state, participant, bindings, require_current_profile=False)
    if cell is not None and (
        state.world is None or state.world.board is None or not state.world.board.contains(cell)
    ):
        raise ValueError("Record actual recovery at a cell on the current known map")
    if participant.kind == "pilot":
        placement = next((x for x in state.placements if x.actor == participant), None)
        origin = (
            journey.traveler_origin
            if participant == journey.traveler
            else journey.supervisor_origin
        )
        if (
            placement is None
            or origin is None
            or placement.vessel_id != origin.vessel_id
            or placement.mode != "outside_frame"
            or placement.custody is not None
        ):
            raise ValueError("Recover only the original free body; do not waive actual custody")
        _save(
            state,
            placement.model_copy(
                update=dict(girl_cell=cell, source_event=source_event, account=account)
            ),
        )
    elif participant.kind == "external_pilot" and any(
        x.id == participant.entity for x in state.harpy_states
    ):
        harpy = next(x for x in state.harpy_states if x.id == participant.entity)
        if harpy.custody != "free":
            raise ValueError(
                "Resolve actual Harpy custody before recovery from this interrupted trip"
            )
        state.harpy_states = [
            x.model_copy(update={"cell": cell, "frame_cell": cell if x.linked else x.frame_cell})
            if x.id == harpy.id
            else x
            for x in state.harpy_states
        ]
    elif participant.kind in ("npc", "external_pilot", "gorgon"):
        if state.world is None or cell is None:
            raise ValueError("Record the actual recovered world role's known map cell")
        if actual.custody not in (None, "free", "supervised_visit:" + journey.id):
            raise ValueError("Actual custody must be resolved before recovering this world role")
        pool = {"npc": "npcs", "external_pilot": "pilots", "gorgon": "gorgons"}[participant.kind]
        entities = getattr(state.world, pool)
        current = next((x for x in entities if x.id == participant.entity), None)
        if (
            current is None
            or (participant.kind == "npc" and current.captive_of is not None)
            or (participant.kind == "external_pilot" and current.custody != "free")
        ):
            raise ValueError("Actual captivity must be resolved before recovering this role")
        state.world = state.world.model_copy(
            update={
                pool: tuple(
                    x.model_copy(update={"cell": cell}) if x.id == participant.entity else x
                    for x in entities
                )
            }
        )
    else:
        state.facts.append(
            dict(
                kind="recorded_handler_recovery_position",
                actor=participant.model_dump_json(),
                cell=json.dumps(cell),
                source_event=source_event,
            )
        )
    state.escort_journeys = [
        x.model_copy(
            update={"offstage_refs": tuple(ref for ref in x.offstage_refs if ref != participant)}
        )
        if x.id == identity
        else x
        for x in state.escort_journeys
    ]
    return _finish(state, participant, source_event, account, "interrupted_party_recovered")
