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


def frame_position(
    state: GameState,
    owner: ActorRef,
    instance: str,
    *,
    fallback: tuple[int, int] | None = None,
) -> tuple[int, int] | None:
    """Follow one actual Frame body through parking or transformation, never its controller."""
    transformed = next(
        (
            x
            for x in state.void_thresholds
            if x.actor == owner and x.frame_instance == instance and x.gorgon is not None
        ),
        None,
    )
    if transformed is not None:
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
    ref = ActorRef.model_validate_json(ref.model_dump_json())
    if ref in _physical_seen:
        raise ValueError("Recover the actual inconsistent physical custody cycle")
    journeys = [
        x
        for x in state.escort_journeys
        if (x.active and ref in (x.traveler, x.supervisor)) or ref in x.offstage_refs
    ]
    if len(journeys) > 1:
        raise ValueError("Recover the actual actor's inconsistent supervised journey")
    journey = journeys[0] if journeys else None
    handler_position = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "recorded_handler_recovery_position"
            and x.get("actor") == ref.model_dump_json()
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
            guardian = resolve(
                state,
                hold.guardian,
                profiles,
                require_alive=require_alive,
                require_current_profile=False,
                _physical_seen=(*_physical_seen, ref),
            )
            if guardian.cell is not None:
                cell = guardian.cell
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
            source_sha256=fingerprint(sheet),
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
            return ActorView(
                ref=ref,
                controller=state.handler,
                label="Handler",
                alive=True,
                rules="handler_girl",
                cell=handler_cell,
                custody="supervised_visit:" + journey.id if journey is not None else None,
                heat=state.handler_heat,
                identities=identities(context.identities),
                source_sha256=hashlib.sha256(
                    json.dumps(
                        {
                            "context": context.model_dump(mode="json"),
                            "persona": state.handler_persona.id if state.handler_persona else None,
                            "heat": state.handler_heat,
                            "tags": [x.model_dump(mode="json") for x in state.handler_tags],
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
            )
        if ref.incarnation is not None and (
            state.handler_persona is None or ref.incarnation != state.handler_persona.id
        ):
            raise ValueError("This old Director context no longer grants Girl-rule authority")
        if state.handler_archives and ref != body:
            raise ValueError("This original Handler body does not identify the new persona")
        return ActorView(
            ref=ref,
            controller=state.handler,
            label="Handler",
            alive=True,
            rules="handler",
            cell=handler_cell,
            custody="supervised_visit:" + journey.id if journey is not None else None,
            heat=state.handler_heat,
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
            assets=assets(harpy.assets),
            identities=identities(harpy.identities),
            cell=None if journey else harpy.cell,
            vessel_id=harpy.body_vessel,
            frame_cell=None if journey is not None and harpy.linked else harpy.frame_cell,
            inside_frame=harpy.linked,
            piloting=harpy.linked and harpy.custody == "free",
            occupied_frame_instance=harpy.frame_instance if harpy.linked else None,
            core_exposed=harpy.exposed,
            custody="supervised_visit:" + journey.id if journey else harpy.custody,
            position_sha256=fingerprint(harpy),
            source_sha256=fingerprint(harpy),
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
        if case is not None:
            sources.append(fingerprint(case))
        if journey is not None:
            sources.append(fingerprint(journey))
        return ActorView(
            ref=ref,
            controller=npc.controller,
            label=npc.name,
            alive=npc.alive,
            rules="director" if "director" in npc.jobs else "npc",
            jobs=npc.jobs,
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
    if ref.kind == "external_pilot":
        pilot = next((x for x in world.pilots if x.id == ref.entity), None)
        if pilot is None or (require_alive and not pilot.alive):
            raise ValueError("Choose a living actual external Pilot")
        return ActorView(
            ref=ref,
            controller=pilot.controller,
            label=pilot.name,
            alive=pilot.alive,
            rules="external_pilot",
            girl=pilot.girl,
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
    return ActorView(
        ref=ref,
        controller=state.handler,
        label=gorgon.name,
        alive=gorgon.alive,
        rules="gorgon",
        assets=assets(gorgon.assets),
        cell=None if journey is not None else gorgon.cell,
        custody="supervised_visit:" + journey.id if journey is not None else None,
        core_exposed=gorgon.exposed,
        source_sha256=fingerprint(gorgon),
    )


def owned_refs(
    state: GameState, controller: int, profiles: tuple[ProfileBinding, ...]
) -> tuple[ActorRef, ...]:
    refs: list[ActorRef] = []
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
        if state.handler == controller:
            refs.extend(
                ActorRef(kind="gorgon", entity=x.id) for x in state.world.gorgons if x.alive
            )
    return tuple(refs)


def owned(
    state: GameState, controller: int, profiles: tuple[ProfileBinding, ...]
) -> tuple[ActorView, ...]:
    return tuple(resolve(state, ref, profiles) for ref in owned_refs(state, controller, profiles))
