"""One AM mind, actual prepared hardware, and a source-owned hooked return."""

from typing import Literal
from uuid import uuid4

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_am_code import Maintenance
from girlframe.engine.m3_physical_state import Placement


class BodySpec(Model):
    vessel: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=1200)
    processing_confirmed: Literal[True]
    unoccupied_confirmed: Literal[True]
    medical: Literal["fit", "unconscious_injured"]
    assets: tuple[AssetState, ...]
    mind_assets: tuple[str, ...] = ()


class Preparation(Model):
    id: str
    maintenance: str
    actor: ActorRef
    operator: ActorRef
    controller: int
    cell: tuple[int, int]
    spec: BodySpec
    event: str


class Body(Model):
    vessel: str
    actor: ActorRef
    label: str
    cell: tuple[int, int]
    assets: tuple[AssetState, ...]
    medical: Literal["fit", "unconscious_injured"]
    occupant: ActorRef | None = None
    origin_event: str
    event: str


class Swap(Model):
    id: str
    maintenance: str
    actor: ActorRef
    operator: ActorRef
    controller: int
    action: str
    preparation: str
    original_vessel: str
    new_vessel: str
    mind_assets: tuple[str, ...]
    original_pose: Placement
    active_pose: Placement
    event: str
    returned_event: str | None = None


class Connection(Model):
    swap: str
    actor: ActorRef
    vessels: tuple[str, str]
    connected: bool
    controller: int
    event: str


def values[T: Model](state: GameState, kind: str, model: type[T]) -> tuple[T, ...]:
    return tuple(model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == kind)


def put(state: GameState, kind: str, identity: str, value: Model) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def preparations(state: GameState) -> tuple[Preparation, ...]:
    return values(state, "am_body_prepared", Preparation)


def bodies(state: GameState) -> tuple[Body, ...]:
    return values(state, "am_body_hardware", Body)


def swaps(state: GameState) -> tuple[Swap, ...]:
    return values(state, "am_body_swap", Swap)


def swap(state: GameState, identity: str) -> Swap:
    value = next((x for x in swaps(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the original AM body-transfer source")
    return value


def connection(state: GameState, identity: str) -> Connection:
    found = [x for x in values(state, "am_body_connection", Connection) if x.swap == identity]
    if len(found) != 1:
        raise ValueError("Recover the actual pair's current physical hookup")
    return found[0]


def _pose(state: GameState, actor: ActorRef) -> Placement:
    pose = next((x for x in state.placements if x.actor == actor), None)
    sheet = state.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.girl != "AM"
        or pose is None
        or pose.girl_cell is None
        or pose.mode != "outside_frame"
        or pose.custody
        or pose.subsumed
    ):
        raise ValueError("Use the same actual free original AM and known outside body")
    return pose


def _ordinary(state: GameState, actor: ActorRef, assets: tuple[AssetState, ...]) -> None:
    if (
        any(x.family != "girl" or x.battery_asset is not None or x.intrinsic for x in assets)
        or any(not x.id.strip() or not x.name.strip() for x in assets)
        or len({x.id for x in assets}) != len(assets)
        or len(assets) > 5
    ):
        raise ValueError("Use actual distinct ordinary Girl Assets within the printed capacity")
    if not assets or not any(not x.damaged for x in assets) or all(x.void for x in assets):
        raise ValueError("SOURCE_BODY_CONSEQUENCE_REQUIRED: actual full-Void/last-usable body port")
    if any(x.battery_asset is not None for x in state.sheets[actor.entity].assets):
        raise ValueError("SOURCE_BODY_CLASSIFICATION_REQUIRED: preserve temporary mental sources")
    from girlframe.engine.m3_janus_storage import active

    if active(state, actor):
        raise ValueError("SOURCE_BODY_CLASSIFICATION_REQUIRED: preserve actual stored Void sources")
    if any(x.asset_owner == actor for x in state.held_items):
        raise ValueError("SOURCE_BODY_CLASSIFICATION_REQUIRED: preserve actual held-object sources")


def prepare(state: GameState, value: Maintenance, spec: BodySpec, event: str) -> Preparation:
    pose = _pose(state, value.actor)
    sheet = state.sheets[value.actor.entity]
    if (
        not event
        or not spec.source.strip()
        or not spec.label.strip()
        or not spec.vessel.strip()
        or spec.vessel in {x.vessel_id for x in state.placements}
        or spec.vessel in {x.vessel for x in bodies(state)}
        or spec.vessel in {x.spec.vessel for x in preparations(state)}
        or any(x.actor == value.actor and not x.returned_event for x in swaps(state))
    ):
        raise ValueError(
            "Confirm genuine available empty hardware, not another body or active swap"
        )
    girls = {x.id: x for x in sheet.assets if x.family == "girl"}
    if (
        len(set(spec.mind_assets)) != len(spec.mind_assets)
        or not set(spec.mind_assets) <= girls.keys()
    ):
        raise ValueError("Explicitly classify only the actual original mind-linked Girl Assets")
    known_assets = {x.id for s in state.sheets.values() for x in s.assets}
    known_assets.update(x.id for body in bodies(state) for x in body.assets)
    known_assets.update(x.id for body in preparations(state) for x in body.spec.assets)
    if {x.id for x in spec.assets} & known_assets:
        raise ValueError(
            "A prepared body's actual Asset IDs cannot alias existing person's resources"
        )
    _ordinary(state, value.actor, tuple(girls[x] for x in spec.mind_assets) + spec.assets)
    assert pose.girl_cell is not None
    prepared = Preparation(
        id=str(uuid4()),
        maintenance=value.id,
        actor=value.actor,
        operator=value.operator,
        controller=value.controller,
        cell=pose.girl_cell,
        spec=spec,
        event=event,
    )
    put(state, "am_body_prepared", prepared.id, prepared)
    return prepared


def _body(
    state: GameState,
    actor: ActorRef,
    pose: Placement,
    ids: set[str],
    event: str,
    label: str,
    occupant: ActorRef | None,
    origin: str,
) -> Body:
    assert pose.girl_cell is not None
    return Body(
        vessel=pose.vessel_id,
        actor=actor,
        label=label,
        cell=pose.girl_cell,
        assets=tuple(x for x in state.sheets[actor.entity].assets if x.id in ids),
        medical=state.sheets[actor.entity].medical_state,
        occupant=occupant,
        origin_event=origin,
        event=event,
    )


def transfer(state: GameState, value: Maintenance, preparation: str, event: str) -> Swap:
    old = _pose(state, value.actor)
    source = next((x for x in preparations(state) if x.id == preparation), None)
    sheet = state.sheets[value.actor.entity]
    if (
        source is None
        or source.maintenance != value.id
        or source.actor != value.actor
        or source.operator != value.operator
        or source.cell != old.girl_cell
        or value.phase not in ("active", "complete")
        or not value.action
        or "body" not in value.selected_options
        or value.body_swap
        or not event
        or any(
            x.preparation == preparation or (x.actor == value.actor and not x.returned_event)
            for x in swaps(state)
        )
    ):
        raise ValueError("Use this actual operator-selected prepared body once")
    from girlframe.engine.m3_am_branch import uses_vessel

    if uses_vessel(state, source.spec.vessel):
        raise ValueError("This actual prepared vessel already contains an AM branch")
    mind = tuple(x for x in sheet.assets if x.id in source.spec.mind_assets)
    if len(mind) != len(source.spec.mind_assets):
        raise ValueError("Recover the original mind-linked Asset classification")
    _ordinary(state, value.actor, mind + source.spec.assets)
    old_body = _body(
        state,
        value.actor,
        old,
        {x.id for x in sheet.assets if x.family == "girl"} - set(source.spec.mind_assets),
        event,
        "Original AM body",
        None,
        old.proposed_event,
    )
    put(state, "am_body_hardware", old_body.vessel, old_body)
    sheet.assets = (
        [x for x in sheet.assets if x.family == "frame"] + list(mind) + list(source.spec.assets)
    )
    sheet.medical_state = source.spec.medical
    sheet.revision += 1
    new = old.model_copy(
        update=dict(
            vessel_id=source.spec.vessel,
            girl_cell=source.cell,
            proposed_event=source.event,
            source_event=event,
            account=source.spec.source,
            incapacitated=source.spec.medical != "fit",
            vitals_active=True,
        )
    )
    state.placements = [new if x.actor == value.actor else x for x in state.placements]
    hardware = _body(
        state,
        value.actor,
        new,
        {x.id for x in source.spec.assets},
        event,
        source.spec.label,
        value.actor,
        source.event,
    )
    put(state, "am_body_hardware", hardware.vessel, hardware)
    result = Swap(
        id=str(uuid4()),
        maintenance=value.id,
        actor=value.actor,
        operator=value.operator,
        controller=value.controller,
        action=value.action,
        preparation=source.id,
        original_vessel=old.vessel_id,
        new_vessel=new.vessel_id,
        mind_assets=source.spec.mind_assets,
        original_pose=old,
        active_pose=new,
        event=event,
    )
    put(state, "am_body_swap", result.id, result)
    link = Connection(
        swap=result.id,
        actor=value.actor,
        vessels=(old.vessel_id, new.vessel_id),
        connected=True,
        controller=value.controller,
        event=event,
    )
    put(state, "am_body_connection", result.id, link)
    return result


def current(state: GameState, actor: ActorRef) -> Body | None:
    history = [x for x in swaps(state) if x.actor == actor]
    active = [x for x in history if not x.returned_event]
    if len(active) > 1:
        raise ValueError("One mind occupies one actual body")
    if not history:
        return None
    value = active[0] if active else history[-1]
    pose = _pose(state, actor)
    vessel = value.original_vessel if value.returned_event else value.new_vessel
    saved = next(x for x in bodies(state) if x.vessel == vessel)
    if pose.vessel_id != saved.vessel or saved.occupant != actor:
        raise ValueError("Recover the same AM's actual occupied hardware")
    return _body(
        state,
        actor,
        pose,
        {x.id for x in state.sheets[actor.entity].assets if x.family == "girl"}
        - set(value.mind_assets),
        saved.event,
        saved.label,
        actor,
        saved.origin_event,
    )


def return_to_origin(state: GameState, identity: str, event: str) -> Swap:
    value = swap(state, identity)
    pose = _pose(state, value.actor)
    link = connection(state, identity)
    old = next(x for x in bodies(state) if x.vessel == value.original_vessel)
    occupied = current(state, value.actor)
    sheet = state.sheets[value.actor.entity]
    prep = next(x for x in preparations(state) if x.id == value.preparation)
    if (
        value.returned_event
        or not event
        or occupied is None
        or not link.connected
        or link.vessels != (value.original_vessel, value.new_vessel)
        or pose.vessel_id != value.new_vessel
        or pose.girl_cell != old.cell
        or old.occupant is not None
        or {x.id for x in sheet.assets if x.family == "girl"}
        != set(value.mind_assets) | {x.id for x in prep.spec.assets}
    ):
        raise ValueError(
            "Return only while this actual original pair is still hooked up and colocated"
        )
    mind = tuple(x for x in sheet.assets if x.id in value.mind_assets)
    _ordinary(state, value.actor, mind + old.assets)
    put(
        state,
        "am_body_hardware",
        occupied.vessel,
        occupied.model_copy(update=dict(occupant=None, event=event)),
    )
    put(
        state,
        "am_body_hardware",
        old.vessel,
        old.model_copy(update=dict(occupant=value.actor, event=event)),
    )
    sheet.assets = [x for x in sheet.assets if x.family == "frame"] + list(mind) + list(old.assets)
    sheet.medical_state = old.medical
    sheet.revision += 1
    restored = pose.model_copy(
        update=dict(
            vessel_id=old.vessel,
            girl_cell=old.cell,
            proposed_event=old.origin_event,
            source_event=event,
            account="Actual AM-owned hooked return",
            incapacitated=old.medical != "fit",
        )
    )
    state.placements = [restored if x.actor == value.actor else x for x in state.placements]
    result = value.model_copy(update=dict(returned_event=event))
    put(state, "am_body_swap", result.id, result)
    return result
