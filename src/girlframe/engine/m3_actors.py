"""Resolve actual canonical actors; missing resources remain missing, never copied."""

import hashlib
import json
from typing import Any

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import (
    ActorRef,
    ActorView,
    AssetView,
    IdentityView,
    ProfileBinding,
)
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit


def fingerprint(value: Any) -> str:
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()


def assets(values: Any, *, sheet: PilotSheet | None = None) -> tuple[AssetView, ...]:
    return tuple(
        AssetView(
            id=x.id,
            name=x.name,
            family=x.family,
            damaged=x.damaged,
            void=x.void,
            counts_toward_limit=counts_toward_limit(sheet, x) if sheet else None,
            can_replace_at_limit=can_replace_at_limit(sheet, x) if sheet else None,
            concealed=x.concealed if sheet else None,
        )
        for x in values
    )


def identities(values: Any) -> tuple[IdentityView, ...]:
    return tuple(
        IdentityView(
            id=x.id,
            name=x.name,
            marked=x.marked,
            protected=x.protected,
            paired=x.paired,
            slot=x.slot,
        )
        for x in values
    )


def harpy_resource_view(state: GameState, ref: ActorRef) -> tuple[tuple[AssetView, ...], str]:
    from girlframe.engine.m3_harpy_resources import assets as actual_assets
    from girlframe.engine.m3_items import actual_asset, same_holder

    values = actual_assets(state, ref)
    source = dict(
        assets=[x.model_dump(mode="json") for x in values],
        carried=[
            x.model_dump(mode="json")
            for x in state.held_items
            if same_holder(state, x.holder, ref)
            and x.location_mode == "carried"
            and actual_asset(state, x) is not None
        ],
    )
    return assets(values), hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def physical_cell(
    state: GameState,
    ref: ActorRef,
    profiles: tuple[ProfileBinding, ...],
    *,
    require_alive: bool = True,
    _physical_seen: tuple[ActorRef, ...] = (),
) -> tuple[int, int] | None:
    """Read a real body's pose without granting a stored alias its current Play role."""
    actual = ref
    if ref.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if not same_handler_body(state, ref):
            raise ValueError("This stored Handler body cannot refer to its replacement")
        contexts = [x for x in state.director_contexts if x.active and x.handler == state.handler]
        if len(contexts) > 1:
            raise ValueError("Recover the inconsistent active Handler context")
        if contexts:
            actual = ActorRef(kind="handler", entity=ref.entity, incarnation=contexts[0].id)
    return resolve(
        state,
        actual,
        profiles,
        require_alive=require_alive,
        require_current_profile=False,
        _physical_seen=_physical_seen,
    ).cell


def frame_position(
    state: GameState,
    owner: ActorRef,
    instance: str,
    *,
    fallback: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """Follow one actual Frame body through parking or transformation, never its controller."""
    from girlframe.engine.m3_am_branch import frame_owner_alias

    branch_owner = frame_owner_alias(state, owner, instance)
    if branch_owner is not None and branch_owner != owner:
        return frame_position(state, branch_owner, instance, fallback=fallback)
    from girlframe.engine.m3_handler_conversion import converted_frame_owner

    converted = converted_frame_owner(state, owner, instance)
    if converted is not None and converted != owner:
        return frame_position(state, converted, instance, fallback=fallback)
    if owner.kind == "gorgon" and any(
        x.state == "offstage" and x.actor == owner for x in state.harpy_travels
    ):
        return None
    if any(
        x.state == "offstage"
        and x.travels_frame
        and x.frame_instance == instance
        and (
            x.actor == owner
            or any(
                h.origin == owner
                and h.id == x.actor.entity
                and h.frame_instance == instance
                and x.actor.kind == "external_pilot"
                for h in state.harpy_states
            )
        )
        for x in state.harpy_travels
    ):
        return None
    pose = next((x for x in state.external_poses if x.actor == owner and x.frame == instance), None)
    if pose is not None:
        return pose.frame_cell
    transformed = next(
        (
            x
            for x in state.void_thresholds
            if x.actor == owner and x.frame_instance == instance and x.gorgon is not None
        ),
        None,
    )
    if transformed is not None:
        if any(
            x.state == "offstage" and x.actor == transformed.gorgon for x in state.harpy_travels
        ):
            return None
        body = (
            next((x for x in state.world.gorgons if x.id == transformed.gorgon.entity), None)
            if state.world and transformed.gorgon
            else None
        )
        return body.cell if body else None
    harpy = next(
        (x for x in state.harpy_states if x.origin == owner and x.frame_instance == instance), None
    )
    if harpy is not None:
        ref = ActorRef(kind="external_pilot", entity=harpy.id)
        if harpy.linked and any(
            (x.active and ref in (x.traveler, x.supervisor)) or ref in x.offstage_refs
            for x in state.escort_journeys
        ):
            return None
        return harpy.frame_cell
    native = next(
        (
            x
            for x in state.native_harpies
            if owner.kind == "external_pilot"
            and x.id == owner.entity
            and x.frame_instance == instance
        ),
        None,
    )
    if native is not None:
        if native.linked and any(
            (x.active and owner in (x.traveler, x.supervisor)) or owner in x.offstage_refs
            for x in state.escort_journeys
        ):
            return None
        return native.frame_cell
    placed = next(
        (x for x in state.placements if x.actor == owner and x.frame_instance == instance), None
    )
    if placed is not None:
        return placed.frame_cell
    parked = next(
        (x for x in state.parked_frames if x.owner == owner and x.frame_instance == instance), None
    )
    return parked.cell if parked else fallback


def resolve(
    state: GameState,
    ref: ActorRef,
    profiles: tuple[ProfileBinding, ...],
    *,
    require_alive: bool = True,
    require_current_profile: bool = True,
    _physical_seen: tuple[ActorRef, ...] = (),
) -> ActorView:
    """Resolve resources once, then apply actual reviewed unknown-position travel."""
    from girlframe.engine.m3_harpy_defeat import offstage_travel

    actual = _resolve(
        state,
        ref,
        profiles,
        require_alive=require_alive,
        require_current_profile=require_current_profile,
        _physical_seen=_physical_seen,
    )
    from girlframe.engine.m3_janus_storage import active as stored_void

    stored = stored_void(state, ref)
    if stored:
        asset_ids = {x.asset for x in stored}
        actual = actual.model_copy(
            update={
                "assets": tuple(
                    x.model_copy(update={"void": True}) if x.id in asset_ids else x
                    for x in actual.assets
                ),
                "source_sha256": hashlib.sha256(
                    (actual.source_sha256 + "".join(x.model_dump_json() for x in stored)).encode()
                ).hexdigest(),
            }
        )
    if state.external_poses or state.leviathan_arrivals:
        from girlframe.engine.m3_leviathan_arrival import body_pose, external_pose

        pose = external_pose(state, ref)
        arrival = body_pose(state, ref)
        if pose is not None:
            actual = actual.model_copy(
                update={
                    "cell": pose.girl_cell,
                    "frame_cell": pose.frame_cell,
                    "inside_frame": pose.mode != "outside_frame",
                    "piloting": pose.mode == "piloting",
                    "frame_instance": pose.frame,
                    "occupied_frame_instance": pose.frame if pose.mode != "outside_frame" else None,
                    "position_sha256": fingerprint(pose),
                    "source_sha256": hashlib.sha256(
                        (actual.source_sha256 + fingerprint(pose)).encode()
                    ).hexdigest(),
                }
            )
        elif arrival is not None and ref.kind == "npc" and arrival.custody == actual.custody:
            actual = actual.model_copy(
                update={
                    "cell": arrival.cell,
                    "position_sha256": fingerprint(arrival),
                    "source_sha256": hashlib.sha256(
                        (actual.source_sha256 + fingerprint(arrival)).encode()
                    ).hexdigest(),
                }
            )
    if state.leviathan_identity_authorities:
        from girlframe.engine.m3_leviathan_obsession import authority, pool

        imported = authority(state, ref)
        if imported is not None:
            imported_values = (
                actual.identities
                if imported.role == "harpy_review"
                else tuple(
                    IdentityView(
                        id=x.id,
                        name=x.name,
                        marked=x.marked,
                        protected=x.protected,
                        paired=x.paired,
                        slot=x.slot,
                    )
                    for x in pool(state, ref)
                )
            )
            actual = actual.model_copy(
                update={
                    "identities": imported_values,
                    "source_sha256": hashlib.sha256(
                        (actual.source_sha256 + fingerprint(imported)).encode()
                    ).hexdigest(),
                }
            )
    if state.passengers:
        from girlframe.engine.m3_passengers import passenger_view
        from girlframe.engine.m3_passengers import same_body as same_passenger_body

        passenger = passenger_view(state, ref)
        if passenger is not None:
            if passenger.controller != actual.controller:
                raise ValueError("Recover the actual original passenger's controller")
            cell = frame_position(
                state, passenger.carrier, passenger.frame, fallback=passenger.cell
            )
            actual = actual.model_copy(
                update=dict(
                    cell=cell,
                    inside_frame=True,
                    piloting=False,
                    occupied_frame_instance=passenger.frame,
                    subsumed=passenger.subsumed,
                    vitals_active=passenger.vitals_active,
                    position_sha256=fingerprint(passenger),
                    source_sha256=hashlib.sha256(
                        (actual.source_sha256 + fingerprint(passenger) + str(cell)).encode()
                    ).hexdigest(),
                )
            )
        elif ref.kind not in ("pilot", "external_pilot"):
            extracted = next(
                (
                    x
                    for x in reversed(state.passengers)
                    if same_passenger_body(state, x.actor, ref) and x.state == "left"
                ),
                None,
            )
            if extracted is not None and not extracted.vitals_active:
                actual = actual.model_copy(
                    update={
                        "vitals_active": False,
                        "cell": extracted.cell,
                        "position_sha256": fingerprint(extracted),
                        "source_sha256": hashlib.sha256(
                            (actual.source_sha256 + fingerprint(extracted)).encode()
                        ).hexdigest(),
                    }
                )
    from girlframe.engine.m3_appearance_matrix import absence as matrix_absence

    matrix = matrix_absence(state, ref)
    if matrix is not None:
        actual = actual.model_copy(
            update={
                "cell": None,
                "frame_cell": None if matrix.travels_frame else actual.frame_cell,
                "offstage_source": matrix.id,
                "position_sha256": fingerprint(matrix),
                "source_sha256": hashlib.sha256(
                    (actual.source_sha256 + fingerprint(matrix)).encode()
                ).hexdigest(),
            }
        )
    travel = offstage_travel(state, ref)
    if travel is None:
        return actual
    from girlframe.engine.m3_handler_consequences import same_handler_body

    def same_body(candidate: ActorRef) -> bool:
        return candidate == ref or (
            candidate.kind == ref.kind == "handler"
            and same_handler_body(state, candidate)
            and same_handler_body(state, ref)
        )

    if travel.controller != actual.controller or any(
        x.active and any(same_body(y) for y in (x.traveler, x.supervisor))
        for x in state.escort_journeys
    ):
        raise ValueError("Recover this original body's inconsistent real travel sources")
    return actual.model_copy(
        update={
            "cell": None,
            "frame_cell": None if travel.travels_frame else actual.frame_cell,
            "offstage_source": travel.id,
            "position_sha256": fingerprint(travel),
            "source_sha256": hashlib.sha256(
                (actual.source_sha256 + fingerprint(travel)).encode()
            ).hexdigest(),
        }
    )


def _resolve(
    state: GameState,
    ref: ActorRef,
    profiles: tuple[ProfileBinding, ...],
    *,
    require_alive: bool = True,
    require_current_profile: bool = True,
    _physical_seen: tuple[ActorRef, ...] = (),
) -> ActorView:
    ref = ActorRef.model_validate_json(ref.model_dump_json())
    if ref.kind == "clone_am":
        from girlframe.engine.m3_clone_am import current, owner
        from girlframe.engine.m3_clone_residency import residence, residence_token

        copy = current(state, ref)
        clone_sheet = owner(state, ref)
        original = resolve(
            state,
            copy.original,
            profiles,
            require_alive=require_alive,
            require_current_profile=require_current_profile,
        )
        current_frame = residence(state, ref)
        located = frame_position(state, copy.original, current_frame, fallback=original.frame_cell)
        return ActorView(
            ref=ref,
            controller=clone_sheet.owner,
            label="Clone AM",
            alive=original.alive,
            rules="clone_am",
            frame=clone_sheet.frame,
            frame_instance=current_frame,
            inside_frame=True,
            piloting=False,
            heat=clone_sheet.heat,
            identities=identities((copy.identity,)),
            cell=located,
            frame_cell=located,
            offstage_source=original.offstage_source if located is None else None,
            source_sha256=hashlib.sha256(
                (fingerprint(copy) + residence_token(state, ref) + original.source_sha256).encode()
            ).hexdigest(),
        )
    if ref in _physical_seen:
        raise ValueError("Recover the actual inconsistent physical custody cycle")

    def same_physical_role(candidate: ActorRef) -> bool:
        if candidate == ref:
            return True
        if ref.kind != "handler" or candidate.kind != "handler":
            return False
        from girlframe.engine.m3_handler_consequences import same_handler_body

        return same_handler_body(state, ref) and same_handler_body(state, candidate)

    journeys = [
        x
        for x in state.escort_journeys
        if (x.active and any(same_physical_role(y) for y in (x.traveler, x.supervisor)))
        or any(same_physical_role(y) for y in x.offstage_refs)
    ]
    if len(journeys) > 1:
        raise ValueError("Recover the actual actor's inconsistent supervised journey")
    journey = journeys[0] if journeys else None
    handler_position = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind")
            in (
                "recorded_handler_recovery_position",
                "cute_uniform_actual_dressing_position",
                "hidden_sidearm_actual_position",
                "reign_terror_actual_position",
                "handler_transport_arrived",
                "leviathan_actual_arrival",
            )
            and same_physical_role(ActorRef.model_validate_json(x["actor"]))
        ),
        None,
    )
    handler_cell = None
    if ref.kind == "handler" and journey is None and handler_position is not None:
        recorded = json.loads(handler_position["cell"])
        if recorded is not None:
            if (
                not isinstance(recorded, list)
                or len(recorded) != 2
                or any(type(x) is not int for x in recorded)
            ):
                raise ValueError("Recover the actual Handler's recorded physical source")
            handler_cell = (recorded[0], recorded[1])
    from girlframe.engine.m3_janus import find as find_core
    from girlframe.engine.m3_janus import has_tag
    from girlframe.engine.m3_janus import position as core_position

    janus = find_core(state, ref)
    if janus is not None:
        if require_alive and not janus.alive:
            raise ValueError("Use the actual living original JANUS Core")
        resource_view, resource_source = harpy_resource_view(state, ref)
        located = core_position(state, janus)
        return ActorView(
            ref=ref,
            controller=janus.controller,
            label="Harpy Core",
            alive=janus.alive,
            rules="external_pilot",
            girl="harpy",
            frame="JANUS-B" if janus.attached or janus.linked else None,
            frame_instance=janus.frame_instance if janus.attached or janus.linked else None,
            heat=janus.heat,
            assets=resource_view,
            identities=identities(janus.identities),
            cell=located,
            vessel_id=janus.body_vessel,
            frame_cell=located if janus.attached else janus.frame_cell if janus.linked else None,
            inside_frame=janus.attached,
            piloting=janus.linked
            and janus.takeover_event is not None
            and not has_tag(janus, "restrained")
            and not janus.frame_shutdown,
            subsumed=janus.subsumed,
            vitals_active=janus.vitals_active,
            occupied_frame_instance=janus.frame_instance if janus.attached else None,
            core_exposed=janus.exposed,
            custody=janus.custody,
            position_sha256=hashlib.sha256(
                (fingerprint(janus) + str(located)).encode()
            ).hexdigest(),
            source_sha256=hashlib.sha256(
                (fingerprint(janus) + resource_source).encode()
            ).hexdigest(),
        )
    if ref.kind == "pilot":
        uid = int(ref.entity)
        sheet = state.sheets.get(ref.entity)
        profile = next((x for x in profiles if x.owner == uid), None)
        if (
            sheet is None
            or sheet.owner != uid
            or uid not in state.order
            or profile is None
            or (sheet.character_id or (profile.source_character_id if profile else None))
            != ref.incarnation
            or profile.character_id != ref.incarnation
            or (
                require_current_profile
                and profile.profile_revision != sheet.source_profile_revision
            )
            or (
                sheet.character_id is None
                and profile.source_profile_revision != sheet.source_profile_revision
                and not (
                    profile.source_profile_revision is None
                    and profile.profile_revision == sheet.source_profile_revision
                )
            )
        ):
            raise ValueError("STALE_ACTOR: use the actual current character/profile incarnation")
        frame_instance = (
            sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + profile.character_id
        )
        placement = next((x for x in state.placements if x.actor == ref), None)
        same_frame = placement is not None and placement.frame_instance == frame_instance
        from girlframe.engine.m3_handler_conversion import frame_shutdown

        shutdown = frame_shutdown(state, ref, frame_instance)
        cell = placement.girl_cell if placement else None
        occupied_instance = None
        if placement and placement.mode != "outside_frame":
            occupied_owner = placement.occupied_frame_owner or ref
            occupied_instance = placement.occupied_frame_instance or placement.frame_instance
            cell = frame_position(
                state, occupied_owner, occupied_instance, fallback=placement.girl_cell
            )
        if journey is not None:
            cell = None
        hold = next(
            (
                x
                for x in state.void_thresholds
                if x.actor == ref
                and x.guardian is not None
                and x.protection_release_event is None
                and placement is not None
                and placement.custody == x.guardian
            ),
            None,
        )
        if hold is not None and hold.guardian is not None:
            guardian_cell = physical_cell(
                state,
                hold.guardian,
                profiles,
                require_alive=require_alive,
                _physical_seen=(*_physical_seen, ref),
            )
            from girlframe.engine.m3_harpy_defeat import offstage_travel

            moved_offstage = (
                offstage_travel(state, hold.guardian) is not None
                or any(
                    (x.active and hold.guardian in (x.traveler, x.supervisor))
                    or hold.guardian in x.offstage_refs
                    for x in state.escort_journeys
                )
                or any(
                    x.escaped and hold.guardian in (x.actor, *x.departed)
                    for x in state.harpy_defeats
                )
            )
            if guardian_cell is not None or moved_offstage:
                cell = guardian_cell
        return ActorView(
            ref=ref,
            controller=uid,
            label=sheet.callsign,
            alive=True,
            rules="girl_frame",
            girl=sheet.girl,
            frame=sheet.frame,
            frame_instance=frame_instance,
            frame_scrapped=sheet.frame_scrapped,
            frame_shutdown=shutdown,
            heat=sheet.heat,
            assets=assets(sheet.assets, sheet=sheet),
            identities=identities(sheet.identities),
            cell=cell,
            vessel_id=placement.vessel_id if placement else None,
            frame_cell=frame_position(state, ref, frame_instance)
            if placement and same_frame
            else None,
            inside_frame=placement.mode != "outside_frame" if placement else None,
            piloting=(
                placement.mode == "piloting"
                and placement.occupied_frame_owner is None
                and not placement.incapacitated
                and not sheet.frame_scrapped
                and not shutdown
            )
            if placement and same_frame
            else None,
            occupied_frame_instance=occupied_instance,
            custody="supervised_visit:" + journey.id
            if journey is not None
            else (placement.custody.kind + ":" + placement.custody.entity)
            if placement and placement.custody
            else None,
            position_sha256=fingerprint(placement) if placement else None,
            source_sha256=hashlib.sha256(
                (fingerprint(sheet) + ":frame_shutdown").encode()
            ).hexdigest()
            if shutdown
            else fingerprint(sheet),
        )
    if ref.kind == "handler":
        if state.handler != int(ref.entity):
            raise ValueError("STALE_ACTOR: use the actual current Handler")
        from girlframe.engine.m3_handler_consequences import active_handler

        body = active_handler(state)
        if body is None:
            raise ValueError("Create the actual new Handler persona before acting as its body")
        active = [x for x in state.director_contexts if x.active and x.handler == state.handler]
        if len(active) > 1:
            raise ValueError("Recover the inconsistent active Handler context")
        if active:
            context = active[0]
            if ref.incarnation != context.id:
                raise ValueError("Use the Handler's actual current Girl-rules context")
            from girlframe.engine.m3_items import actual_asset, mechanical_assets, same_holder

            mechanical = mechanical_assets(state, ref)
            passengers = [
                entry
                for entry in state.passengers
                if entry.state == "boarded" and same_physical_role(entry.actor)
            ]
            if len(passengers) > 1:
                raise ValueError(
                    "Recover the original Handler's contradictory actual passenger records"
                )
            carried = [
                item.model_dump(mode="json")
                for item in state.held_items
                if item.location_mode == "carried"
                and same_holder(state, item.holder, ref)
                and actual_asset(state, item) is not None
            ]
            return ActorView(
                ref=ref,
                controller=state.handler,
                label="Handler",
                alive=True,
                rules="handler_girl",
                cell=None if passengers else handler_cell,
                custody="supervised_visit:" + journey.id if journey is not None else None,
                heat=state.handler_heat,
                identities=identities(context.identities),
                assets=assets(mechanical),
                position_sha256=fingerprint(passengers[0]) if passengers else None,
                source_sha256=hashlib.sha256(
                    json.dumps(
                        {
                            "context": context.model_dump(mode="json"),
                            "persona": state.handler_persona.id if state.handler_persona else None,
                            "heat": state.handler_heat,
                            "tags": [x.model_dump(mode="json") for x in state.handler_tags],
                            **(
                                {
                                    "assets": [x.model_dump(mode="json") for x in mechanical],
                                    "carried": carried,
                                }
                                if mechanical
                                else {}
                            ),
                            **(
                                {"passenger": passengers[0].model_dump(mode="json")}
                                if passengers
                                else {}
                            ),
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
            )
        context_alias = next(
            (
                x
                for x in state.director_contexts
                if not x.active and x.id == ref.incarnation and x.body_actor == body
            ),
            None,
        )
        if (
            context_alias is None
            and ref.incarnation is not None
            and (state.handler_persona is None or ref.incarnation != state.handler_persona.id)
        ):
            raise ValueError("This old Director context no longer grants Girl-rule authority")
        if state.handler_archives and ref != body and context_alias is None:
            raise ValueError("This original Handler body does not identify the new persona")
        return ActorView(
            ref=ref,
            controller=state.handler,
            label="Handler",
            alive=True,
            rules="handler",
            cell=handler_cell,
            custody="supervised_visit:" + journey.id if journey is not None else None,
            heat=None,
            source_sha256=hashlib.sha256(
                json.dumps(
                    {
                        "handler": state.handler,
                        "persona": state.handler_persona.id if state.handler_persona else None,
                        "heat": state.handler_heat,
                        "tags": [x.model_dump(mode="json") for x in state.handler_tags],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        )
    harpy = next(
        (x for x in state.harpy_states if ref.kind == "external_pilot" and x.id == ref.entity),
        None,
    )
    if harpy is not None:
        if require_alive and not harpy.alive:
            raise ValueError("The actual original Harpy is no longer alive")
        resource_view, resource_source = harpy_resource_view(state, ref)
        return ActorView(
            ref=ref,
            controller=harpy.controller,
            label=harpy.name,
            alive=harpy.alive,
            rules="external_pilot",
            girl="harpy",
            frame="harpy",
            frame_instance=harpy.frame_instance,
            heat=harpy.heat,
            assets=resource_view,
            identities=identities(harpy.identities),
            cell=None if journey else harpy.cell,
            vessel_id=harpy.body_vessel,
            frame_cell=None if journey is not None and harpy.linked else harpy.frame_cell,
            inside_frame=harpy.linked,
            piloting=harpy.linked
            and harpy.custody == "free"
            and not harpy.frame_shutdown
            and not harpy.body_incapacitated,
            subsumed=harpy.subsumed,
            vitals_active=harpy.vitals_active,
            occupied_frame_instance=harpy.frame_instance if harpy.linked else None,
            core_exposed=harpy.exposed,
            custody="supervised_visit:" + journey.id if journey else harpy.custody,
            position_sha256=fingerprint(harpy),
            source_sha256=hashlib.sha256(
                (fingerprint(harpy) + resource_source).encode()
            ).hexdigest(),
        )
    world = state.world
    if world is None:
        raise ValueError("The actual world actor has not been introduced")
    if ref.kind == "npc":
        npc = next((x for x in world.npcs if x.id == ref.entity), None)
        if npc is None or (require_alive and not npc.alive):
            raise ValueError("Choose a living actual NPC")
        case = next((x for x in reversed(state.enforcer_accusations) if x.subject == ref), None)
        detained = case is not None and case.detained
        unknown_release = case is not None and not case.detained and case.position_event is None
        sources = [fingerprint(npc)]
        from girlframe.engine.m3_am_reset import body as reset_body
        from girlframe.engine.m3_am_reset import prove as prove_reset

        reset = reset_body(state, ref)
        reset_assets: tuple[AssetView, ...] = ()
        if reset is not None:
            prove_reset(state, reset)
            from girlframe.engine.m3_items import mechanical_assets

            combined = {x.id: x for x in reset.assets}
            combined.update({x.id: x for x in mechanical_assets(state, ref)})
            reset_assets = assets(tuple(combined.values()))
            sources.append(fingerprint(reset))
            sources.extend(fingerprint(x) for x in state.held_items if x.holder == ref)
        if case is not None:
            sources.append(fingerprint(case))
        if journey is not None:
            sources.append(fingerprint(journey))
        view = ActorView(
            ref=ref,
            controller=npc.controller,
            label=npc.name,
            alive=npc.alive,
            rules="director" if "director" in npc.jobs else "npc",
            jobs=npc.jobs,
            assets=reset_assets,
            identities=identities(reset.identities) if reset else (),
            vessel_id=reset.body.vessel_id if reset else None,
            inside_frame=False if reset else None,
            piloting=False if reset else None,
            vitals_active=bool(npc.alive and reset.body.vitals_active) if reset else None,
            subsumed=False if reset else None,
            cell=None if journey is not None or detained or unknown_release else npc.cell,
            custody="foundation_detention:" + case.id
            if detained and case is not None
            else "supervised_visit:" + journey.id
            if journey is not None
            else "gorgon_captive"
            if npc.captive_of
            else None,
            source_sha256=sources[0]
            if len(sources) == 1
            else hashlib.sha256("|".join(sources).encode()).hexdigest(),
        )
        from girlframe.engine.m3_am_branch import npc_view

        return npc_view(state, view)
    if ref.kind == "external_pilot":
        pilot = next((x for x in world.pilots if x.id == ref.entity), None)
        if pilot is None or (require_alive and not pilot.alive):
            raise ValueError("Choose a living actual external Pilot")
        native = next((x for x in state.native_harpies if x.id == ref.entity), None)
        if native is not None:
            from girlframe.engine.m3_harpy_defeat import harpy as actual_harpy

            actual_harpy(state, ref)
            resource_view, resource_source = harpy_resource_view(state, ref)
            source = hashlib.sha256(
                (fingerprint(pilot) + fingerprint(native) + resource_source).encode()
            ).hexdigest()
            return ActorView(
                ref=ref,
                controller=pilot.controller,
                label=pilot.name,
                alive=pilot.alive,
                rules="external_pilot",
                girl="harpy",
                frame="harpy",
                frame_instance=native.frame_instance,
                heat=native.heat,
                assets=resource_view,
                identities=identities(native.identities),
                cell=None if journey else native.cell,
                vessel_id=native.body_vessel,
                frame_cell=None if journey and native.linked else native.frame_cell,
                inside_frame=native.linked,
                piloting=native.linked
                and native.custody == "free"
                and not native.frame_shutdown
                and not native.body_incapacitated,
                subsumed=native.subsumed,
                vitals_active=native.vitals_active,
                occupied_frame_instance=native.frame_instance if native.linked else None,
                core_exposed=pilot.exposed,
                custody="supervised_visit:" + journey.id if journey else native.custody,
                position_sha256=fingerprint(native),
                source_sha256=source,
            )
        from girlframe.engine.m3_actor_resources import rebel_inventory

        rebel = rebel_inventory(state, ref)
        return ActorView(
            ref=ref,
            controller=pilot.controller,
            label=pilot.name,
            alive=pilot.alive,
            rules="external_pilot",
            girl=pilot.girl,
            heat=rebel.heat if rebel else 0,
            identities=identities(rebel.identities) if rebel else (),
            frame=pilot.frame,
            frame_instance="initial:" + pilot.id,
            assets=assets(pilot.assets),
            cell=None if journey is not None else pilot.cell,
            core_exposed=pilot.exposed,
            custody="supervised_visit:" + journey.id if journey is not None else pilot.custody,
            source_sha256=fingerprint(pilot),
        )
    gorgon = next((x for x in world.gorgons if x.id == ref.entity), None)
    if gorgon is None or state.handler is None or (require_alive and not gorgon.alive):
        raise ValueError("Choose a living actual Gorgon under the current facilitator")
    from girlframe.engine.m3_janus_pandora import child_record, newborn_controller

    birth = child_record(state, ref)
    controller = newborn_controller(state, ref) or state.handler
    return ActorView(
        ref=ref,
        controller=controller,
        label=gorgon.name,
        alive=gorgon.alive,
        rules="gorgon",
        assets=assets(gorgon.assets),
        cell=None if journey is not None else gorgon.cell,
        custody="supervised_visit:" + journey.id if journey is not None else None,
        core_exposed=gorgon.exposed,
        source_sha256=hashlib.sha256(
            (fingerprint(gorgon) + fingerprint(birth) + str(controller)).encode()
        ).hexdigest()
        if birth
        else fingerprint(gorgon),
    )


def owned_refs(
    state: GameState, controller: int, profiles: tuple[ProfileBinding, ...]
) -> tuple[ActorRef, ...]:
    refs: list[ActorRef] = []
    from girlframe.engine.m3_clone_am import copies, current

    for copy in copies(state):
        if copy.original.entity == str(controller):
            try:
                current(state, copy.ref)
            except ValueError:
                continue
            refs.append(copy.ref)
    refs.extend(
        ActorRef(kind="external_pilot", entity=x.id)
        for x in state.janus_cores
        if x.controller == controller and x.alive
    )
    refs.extend(
        ActorRef(kind="external_pilot", entity=x.id)
        for x in state.harpy_states
        if x.controller == controller and x.alive
    )
    for profile in profiles:
        if (
            profile.owner == controller
            and str(controller) in state.sheets
            and controller in state.order
        ):
            refs.append(
                ActorRef(kind="pilot", entity=str(controller), incarnation=profile.character_id)
            )
    from girlframe.engine.m3_handler_consequences import active_handler

    if state.handler == controller and active_handler(state) is not None:
        context = next(
            (x for x in state.director_contexts if x.active and x.handler == controller), None
        )
        refs.append(
            ActorRef(
                kind="handler",
                entity=str(controller),
                incarnation=context.id
                if context
                else (state.handler_persona.id if state.handler_persona else None),
            )
        )
    if state.world:
        refs.extend(
            ActorRef(kind="npc", entity=x.id)
            for x in state.world.npcs
            if x.controller == controller and x.alive
        )
        refs.extend(
            ActorRef(kind="external_pilot", entity=x.id)
            for x in state.world.pilots
            if x.controller == controller and x.alive
        )
        refs.extend(
            ActorRef(kind="gorgon", entity=x.id)
            for x in state.world.gorgons
            if x.alive
            and resolve(state, ActorRef(kind="gorgon", entity=x.id), profiles).controller
            == controller
        )
    return tuple(refs)


def owned(
    state: GameState, controller: int, profiles: tuple[ProfileBinding, ...]
) -> tuple[ActorView, ...]:
    return tuple(resolve(state, ref, profiles) for ref in owned_refs(state, controller, profiles))
