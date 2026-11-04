"""Resolve actual canonical actors; missing resources remain missing, never copied."""

import hashlib
import json
from typing import Any

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import (
    ActorRef,
    ActorView,
    AssetView,
    IdentityView,
    ProfileBinding,
)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()


def assets(values: Any) -> tuple[AssetView, ...]:
    return tuple(
        AssetView(id=x.id, name=x.name, family=x.family, damaged=x.damaged, void=x.void)
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


def resolve(
    state: GameState,
    ref: ActorRef,
    profiles: tuple[ProfileBinding, ...],
    *,
    require_alive: bool = True,
    require_current_profile: bool = True,
) -> ActorView:
    ref = ActorRef.model_validate_json(ref.model_dump_json())
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
            assets=assets(sheet.assets),
            identities=identities(sheet.identities),
            cell=placement.girl_cell if placement else None,
            vessel_id=placement.vessel_id if placement else None,
            frame_cell=placement.frame_cell if placement and same_frame else None,
            inside_frame=placement.mode != "outside_frame" if placement else None,
            piloting=(placement.mode == "piloting" and not sheet.frame_scrapped)
            if placement and same_frame
            else None,
            occupied_frame_instance=placement.frame_instance
            if placement and placement.mode != "outside_frame"
            else None,
            position_sha256=fingerprint(placement) if placement else None,
            source_sha256=fingerprint(sheet),
        )
    if ref.kind == "handler":
        if state.handler != int(ref.entity):
            raise ValueError("STALE_ACTOR: use the actual current Handler")
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
                heat=state.handler_heat,
                identities=identities(context.identities),
                source_sha256=hashlib.sha256(
                    json.dumps(
                        {
                            "context": context.model_dump(mode="json"),
                            "heat": state.handler_heat,
                            "tags": [x.model_dump(mode="json") for x in state.handler_tags],
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
            )
        if ref.incarnation is not None:
            raise ValueError("This old Director context no longer grants Girl-rule authority")
        return ActorView(
            ref=ref,
            controller=state.handler,
            label="Handler",
            alive=True,
            rules="handler",
            heat=state.handler_heat,
            source_sha256=hashlib.sha256(
                json.dumps(
                    {
                        "handler": state.handler,
                        "heat": state.handler_heat,
                        "tags": [x.model_dump(mode="json") for x in state.handler_tags],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        )
    world = state.world
    if world is None:
        raise ValueError("The actual world actor has not been introduced")
    if ref.kind == "npc":
        npc = next((x for x in world.npcs if x.id == ref.entity), None)
        if npc is None or (require_alive and not npc.alive):
            raise ValueError("Choose a living actual NPC")
        return ActorView(
            ref=ref,
            controller=npc.controller,
            label=npc.name,
            alive=npc.alive,
            rules="director" if "director" in npc.jobs else "npc",
            jobs=npc.jobs,
            cell=npc.cell,
            custody="gorgon_captive" if npc.captive_of else None,
            source_sha256=fingerprint(npc),
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
            cell=pilot.cell,
            core_exposed=pilot.exposed,
            custody=pilot.custody,
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
        cell=gorgon.cell,
        core_exposed=gorgon.exposed,
        source_sha256=fingerprint(gorgon),
    )


def owned_refs(
    state: GameState, controller: int, profiles: tuple[ProfileBinding, ...]
) -> tuple[ActorRef, ...]:
    refs: list[ActorRef] = []
    for profile in profiles:
        if (
            profile.owner == controller
            and str(controller) in state.sheets
            and controller in state.order
        ):
            refs.append(
                ActorRef(kind="pilot", entity=str(controller), incarnation=profile.character_id)
            )
    if state.handler == controller:
        context = next(
            (x for x in state.director_contexts if x.active and x.handler == controller), None
        )
        refs.append(
            ActorRef(
                kind="handler", entity=str(controller), incarnation=context.id if context else None
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
