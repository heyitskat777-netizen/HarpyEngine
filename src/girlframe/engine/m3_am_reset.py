"""One source-specific AM factory reset preserves the person and actual hardware."""

import json

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState, IdentityState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model
from girlframe.engine.m3_physical_state import ParkedFrame, Placement
from girlframe.engine.m3_world_state import NPC_JOBS, Npc, WorldTag

JOBS = tuple(x for x in NPC_JOBS if x != "director")


class FactoryReset(Model):
    id: str = Field(min_length=1)
    original: ActorRef
    actor: ActorRef
    archive: str = Field(min_length=1)
    discovery: str = Field(min_length=1)
    installation_event: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    controller: int = Field(gt=0)
    body: Placement
    assets: tuple[AssetState, ...]
    identities: tuple[IdentityState, ...]
    retained_tag_sources: tuple[TagState, ...]
    account: str = Field(min_length=1, max_length=1200)


def records(state: GameState) -> tuple[FactoryReset, ...]:
    return tuple(
        FactoryReset.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "am_factory_reset"
    )


def body(state: GameState, actor: ActorRef) -> FactoryReset | None:
    found = [x for x in records(state) if x.actor == actor]
    if len(found) > 1:
        raise ValueError("An original reset person has one actual NPC body authority")
    return found[0] if found else None


def origin(state: GameState, actor: ActorRef) -> ActorRef:
    actual = body(state, actor) if actor.kind == "npc" else None
    return actual.original if actual else actor


def eligible(state: GameState, actor: ActorRef) -> bool:
    sheet = state.sheets.get(actor.entity)
    placement = next((x for x in state.placements if x.actor == actor), None)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.girl != "AM"
        or int(actor.entity) not in state.order
        or state.world is None
        or placement is None
        or placement.mode != "outside_frame"
        or placement.frame_instance
        != (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation))
        or placement.girl_cell is None
        or placement.custody is not None
        or placement.incapacitated
        or placement.subsumed
        or not placement.vitals_active
        or sheet.medical_state != "fit"
        or any(x.active and actor in (x.traveler, x.supervisor) for x in state.escort_journeys)
        or any(actor in x.offstage_refs for x in state.escort_journeys)
        or any(x.held and actor in (x.actor, x.target) for x in state.enforcer_grasps)
        or any(x.occupied_frame_owner == actor for x in state.placements)
        or any(
            x.actor == actor or x.carrier == actor for x in state.passengers if x.state == "boarded"
        )
        or any(x.frame_instance == placement.frame_instance for x in state.parked_frames)
    ):
        return False
    # An active neural episode needs its real unplug/ending; reset grants no unplug action.
    if any(
        x.phase == "connected" and actor in (x.caster, x.battery) for x in state.neural_connections
    ):
        return False
    return True


def convert(
    before: GameState,
    ended: GameState,
    actor: ActorRef,
    *,
    identity: str,
    discovery: str,
    installation_event: str,
    archive: str,
    event: str,
    controller: int,
    job: str,
    account: str,
) -> GameState:
    from girlframe.engine import m3_am
    from girlframe.engine.m3_actor_bonds import rebind
    from girlframe.engine.m3_items import actual_asset

    if not eligible(before, actor) or len(m3_am.limiters(before, actor)) != 4 or job not in JOBS:
        raise ValueError("Use the actual fourth-Limited AM's supported source body once")
    sheet = before.sheets[actor.entity]
    original_body = next(x for x in before.placements if x.actor == actor)
    saved = next((x for x in ended.career_archives if x.id == archive), None)
    if (
        saved is None
        or saved.actor != actor
        or saved.ending != "factory_reset"
        or saved.source_event != event
        or actor.entity in ended.sheets
        or controller != before.handler
        or not account.strip()
    ):
        raise ValueError("The actual Handler claims the real NPC after the original PC ending")
    state = GameState.model_validate_json(ended.model_dump_json())
    assert state.world is not None and original_body.girl_cell is not None
    npc = ActorRef(kind="npc", entity=identity)
    if any(x.actor == npc or x.original == actor for x in records(state)) or any(
        x.id == identity
        for x in (
            *state.world.npcs,
            *state.world.pilots,
            *state.world.gorgons,
            *state.world.factions,
            *state.world.locations,
        )
    ):
        raise ValueError("Factory reset does not overwrite another actual original")
    held_assets: set[str] = set()
    items = []
    for item in state.held_items:
        if item.holder != actor:
            items.append(item)
            continue
        asset = actual_asset(before, item)
        if asset is not None:
            held_assets.add(asset.id)
        items.append(
            item.model_copy(
                update=dict(
                    holder=npc,
                    asset_owner=npc if item.asset_owner == actor else item.asset_owner,
                    asset_json=asset.model_dump_json() if asset else item.asset_json,
                    state_event=event,
                )
            )
        )
    state.held_items = items
    retained = tuple(sheet.tags)
    tags = tuple(
        WorldTag(
            id=x.id,
            label=x.label,
            marked=x.marked,
            rejection_pending=x.rejection_pending,
            giver_entity=(
                "gm:" + x.gm_setter_appointment
                if x.gm_setter_appointment
                else x.giver_actor.model_dump_json()
                if x.giver_actor
                else ActorRef(
                    kind="pilot", entity=str(x.giver), incarnation=x.giver_character
                ).model_dump_json()
            ),
            trigger_scene=x.scene_used,
        )
        for x in retained
    )
    introduced = Npc(
        id=identity,
        name=sheet.callsign,
        cell=original_body.girl_cell,
        jobs=(job,),
        detail=account,
        controller=controller,
        revealed=True,
        tags=tags,
    )
    state.world = state.world.model_copy(update={"npcs": state.world.npcs + (introduced,)})
    state.parked_frames.append(
        ParkedFrame(
            owner=actor,
            frame_instance=original_body.frame_instance,
            cell=original_body.frame_cell,
            source_event=event,
            prior_event=original_body.source_event,
            core_id=sheet.frame_runtime.core_id if sheet.frame_runtime else None,
            frame_json=sheet.model_dump_json(),
        )
    )
    value = FactoryReset(
        id=identity,
        original=actor,
        actor=npc,
        archive=archive,
        discovery=discovery,
        installation_event=installation_event,
        source_event=event,
        controller=controller,
        body=original_body,
        identities=tuple(sheet.identities),
        retained_tag_sources=retained,
        assets=tuple(
            x
            for x in sheet.assets
            if x.family == "girl" and x.id not in held_assets and x.battery_asset is None
        ),
        account=account,
    )
    state.facts.append(dict(kind="am_factory_reset", id=identity, body=value.model_dump_json()))
    state = rebind(state, actor, npc, event)
    links = json.loads(saved.links_json)
    links["am_factory_reset"] = dict(
        resulting_actor=npc.model_dump(mode="json"),
        event=event,
        vessel=original_body.vessel_id,
        discovery=discovery,
    )
    state.career_archives = [
        x.model_copy(update={"links_json": json.dumps(links, sort_keys=True)})
        if x.id == archive
        else x
        for x in state.career_archives
    ]
    incident = m3_am.discovery(state, discovery)
    m3_am.put(state, incident.model_copy(update={"phase": "reset", "factory_reset": identity}))
    # This actual scene contains the same body under its newly accepted NPC authority.
    state.scene_casts = [
        x.model_copy(
            update={
                "roles": x.roles
                + (CastRole(actor=npc, controller=controller, source_event=event),),
                "revision": x.revision + 1,
            }
        )
        if x.id == incident.cast.id and x.open
        else x
        for x in state.scene_casts
    ]
    return GameState.model_validate_json(state.model_dump_json())


def prove(state: GameState, value: FactoryReset) -> None:
    saved = next((x for x in state.career_archives if x.id == value.archive), None)
    if (
        saved is None
        or saved.actor != value.original
        or saved.ending != "factory_reset"
        or saved.source_event != value.source_event
        or value.actor.kind != "npc"
        or value.body.actor != value.original
        or value.body.mode != "outside_frame"
    ):
        raise ValueError("Recover the actual original factory-reset body and career source")
    links = json.loads(saved.links_json)
    marker = links.get("am_factory_reset", {})
    old = PilotSheet.model_validate_json(saved.sheet_json)
    original_placements = [
        Placement.model_validate_json(json.dumps(x)) for x in links.get("placements", ())
    ]
    original_assets = {x.id: x for x in old.assets if x.family == "girl"}
    if (
        marker.get("resulting_actor") != value.actor.model_dump(mode="json")
        or marker.get("vessel") != value.body.vessel_id
        or marker.get("event") != value.source_event
        or tuple(old.identities) != value.identities
        or tuple(old.tags) != value.retained_tag_sources
        or value.body not in original_placements
        or len({x.id for x in value.assets}) != len(value.assets)
        or any(original_assets.get(x.id) != x for x in value.assets)
        or not any(
            x.owner == value.original
            and x.frame_instance == value.body.frame_instance
            and x.source_event == value.source_event
            and x.frame_json == saved.sheet_json
            for x in state.parked_frames
        )
    ):
        raise ValueError("An NPC cannot borrow another original's body or factory reset")
