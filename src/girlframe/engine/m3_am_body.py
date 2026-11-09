"""One AM mind, actual prepared hardware, and a source-owned hooked return."""

from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

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
    carried_items: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)


class Preparation(Model):
    id: str
    maintenance: str
    actor: ActorRef
    operator: ActorRef
    controller: int
    cell: tuple[int, int]
    spec: BodySpec
    event: str
    fact_author: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    fact_appointment: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def factual_source(self) -> "Preparation":
        if (self.fact_author is None) != (self.fact_appointment is None) or (
            self.fact_author is not None and self.fact_author.kind != "handler"
        ):
            raise ValueError("Record the actual original Handler and appointment together")
        return self


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
    carried_items: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    neural_route: str | None = Field(default=None, exclude_if=lambda value: value is None)


class Conveyance(Model):
    id: str
    actor: ActorRef
    previous: str
    vessel: str
    items: tuple[str, ...]
    assets: tuple[AssetState, ...]
    source: str
    kind: Literal["code", "return", "jailbroken"]
    controller: int
    event: str
    account: str = Field(min_length=1, max_length=1200)


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


def carried_assets(
    state: GameState, actor: ActorRef, items: tuple[str, ...]
) -> tuple[AssetState, ...]:
    """Exact current physical objects, never a mental classification or an alias."""
    from girlframe.engine.m3_items import actual_asset

    owned = tuple(x for x in state.held_items if x.asset_owner == actor)
    if len(set(items)) != len(items) or set(items) != {x.id for x in owned}:
        raise ValueError(
            "SOURCE_BODY_CLASSIFICATION_REQUIRED: select every actual owned held object"
        )
    assets = []
    for identity in items:
        item = next(x for x in owned if x.id == identity)
        asset = actual_asset(state, item)
        if (
            item.holder != actor
            or item.location_mode != "carried"
            or asset is None
            or asset.family != "girl"
            or asset.battery_asset is not None
            or asset.intrinsic
        ):
            raise ValueError("Convey only genuinely carried own physical Girl Assets")
        assets.append(asset)
    if len({x.id for x in assets}) != len(assets):
        raise ValueError("One actual physical Asset cannot have duplicated object bindings")
    return tuple(assets)


def carried_ids(state: GameState, actor: ActorRef) -> set[str]:
    return {
        x.id
        for x in carried_assets(
            state, actor, tuple(x.id for x in state.held_items if x.asset_owner == actor)
        )
    }


def conveyances(state: GameState) -> tuple[Conveyance, ...]:
    return values(state, "am_body_conveyance", Conveyance)


def record_conveyance(
    state: GameState,
    actor: ActorRef,
    previous: str,
    vessel: str,
    items: tuple[str, ...],
    assets: tuple[AssetState, ...],
    source: str,
    kind: Literal["code", "return", "jailbroken"],
    controller: int,
    event: str,
    account: str | None,
) -> None:
    if not items:
        if account:
            raise ValueError("Conveyance account needs actual selected physical objects")
        return
    if not account or not account.strip() or len(account) > 1200:
        raise ValueError(
            "Record the actual performed physical conveyance separately from the mind move"
        )
    value = Conveyance(
        id=event,
        actor=actor,
        previous=previous,
        vessel=vessel,
        items=items,
        assets=assets,
        source=source,
        kind=kind,
        controller=controller,
        event=event,
        account=account.strip(),
    )
    put(state, "am_body_conveyance", event, value)


def spinal_links(state: GameState, actor: ActorRef) -> tuple[str, ...]:
    """Actual connected spinal sources; a mind move is not a physical unplug."""
    return tuple(
        x.id
        for x in state.neural_connections
        if x.phase == "connected" and actor in (x.caster, x.battery)
    )


def _ordinary(
    state: GameState,
    actor: ActorRef,
    assets: tuple[AssetState, ...],
    *,
    carried_items: tuple[str, ...] = (),
    neural_route: str | None = None,
    destination: str | None = None,
) -> None:
    retained: tuple[AssetState, ...] = ()
    if neural_route is not None:
        from girlframe.engine.m3_am_neural_route import retained_mental_assets, validate_move

        if destination is None:
            raise ValueError("Select the actual continuous route's prepared destination")
        validate_move(state, actor, destination, neural_route)
        retained = retained_mental_assets(state, actor, neural_route)
    if spinal_links(state, actor) and neural_route is None:
        raise ValueError(
            "SOURCE_NEURAL_ROUTE_REQUIRED: actually unplug before this supported body move; "
            "continuous physical relay needs its own proven source route"
        )
    if (
        any(
            x.family != "girl" or (x.battery_asset is not None and x not in retained) or x.intrinsic
            for x in assets
        )
        or any(not x.id.strip() or not x.name.strip() for x in assets)
        or len({x.id for x in assets}) != len(assets)
        or len([x for x in assets if x.battery_asset is None]) > 5
    ):
        raise ValueError("Use actual distinct ordinary Girl Assets within the printed capacity")
    # Requisite processing is separately source-proved by BodySpec. Asset absence/condition
    # alone is not battle depletion. Actual occupation/return materializes real Void consequences.
    if any(
        x.battery_asset is not None and x not in retained for x in state.sheets[actor.entity].assets
    ):
        raise ValueError("SOURCE_BODY_CLASSIFICATION_REQUIRED: preserve temporary mental sources")
    from girlframe.engine.m3_janus_storage import active

    if active(state, actor) and neural_route is None:
        raise ValueError("SOURCE_BODY_CLASSIFICATION_REQUIRED: preserve actual stored Void sources")
    portable = carried_assets(state, actor, carried_items)
    if any(x not in assets for x in portable):
        raise ValueError("Preserve the exact current condition of the actually conveyed objects")


def prepare(
    state: GameState,
    value: Maintenance,
    spec: BodySpec,
    event: str,
    *,
    fact_author: ActorRef | None = None,
    fact_appointment: str | None = None,
) -> Preparation:
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
    portable = carried_assets(state, value.actor, spec.carried_items)
    if set(spec.mind_assets) & {x.id for x in portable}:
        raise ValueError("A physical held object is not a mind-linked Asset")
    _ordinary(
        state,
        value.actor,
        tuple(girls[x] for x in spec.mind_assets) + spec.assets + portable,
        carried_items=spec.carried_items,
    )
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
        fact_author=fact_author,
        fact_appointment=fact_appointment,
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
        assets=tuple(
            x for x in state.sheets[actor.entity].assets if x.id in ids and x.battery_asset is None
        ),
        medical=state.sheets[actor.entity].medical_state,
        occupant=occupant,
        origin_event=origin,
        event=event,
    )


def transfer(
    state: GameState,
    value: Maintenance,
    preparation: str,
    event: str,
    *,
    carried_items: tuple[str, ...] = (),
    carry_account: str | None = None,
    neural_route: str | None = None,
) -> Swap:
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
    if carried_items != source.spec.carried_items:
        raise ValueError("Actually select the original prepared physical objects for this move")
    portable = carried_assets(state, value.actor, carried_items)
    if set(source.spec.mind_assets) & {x.id for x in portable}:
        raise ValueError("A physical object cannot follow the mind without actual conveyance")
    from girlframe.engine.m3_am_neural_route import retained_mental_assets

    retained = retained_mental_assets(state, value.actor, neural_route) if neural_route else ()
    _ordinary(
        state,
        value.actor,
        mind + source.spec.assets + portable + retained,
        carried_items=carried_items,
        neural_route=neural_route,
        destination=source.spec.vessel,
    )
    if carried_items and (not carry_account or not carry_account.strip()):
        raise ValueError("Record actual physical conveyance before changing occupied bodies")
    old_body = _body(
        state,
        value.actor,
        old,
        {x.id for x in sheet.assets if x.family == "girl"}
        - set(source.spec.mind_assets)
        - {x.id for x in portable},
        event,
        "Original AM body",
        None,
        old.proposed_event,
    )
    put(state, "am_body_hardware", old_body.vessel, old_body)
    sheet.assets = (
        [x for x in sheet.assets if x.family == "frame"]
        + list(mind)
        + list(source.spec.assets)
        + list(portable)
        + list(retained)
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
        carried_items=carried_items,
        neural_route=neural_route,
        original_pose=old,
        active_pose=new,
        event=event,
    )
    put(state, "am_body_swap", result.id, result)
    record_conveyance(
        state,
        value.actor,
        old.vessel_id,
        new.vessel_id,
        carried_items,
        portable,
        result.id,
        "code",
        value.controller,
        event,
        carry_account,
    )
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
    from girlframe.engine.m3_am_jailbroken import current as self_occupied

    actual = self_occupied(state, actor)
    if actual is not None:
        return actual
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
        - set(value.mind_assets)
        - carried_ids(state, actor),
        saved.event,
        saved.label,
        actor,
        saved.origin_event,
    )


def return_to_origin(
    state: GameState,
    identity: str,
    event: str,
    *,
    carried_items: tuple[str, ...] = (),
    carry_account: str | None = None,
) -> Swap:
    value = swap(state, identity)
    pose = _pose(state, value.actor)
    link = connection(state, identity)
    old = next(x for x in bodies(state) if x.vessel == value.original_vessel)
    occupied = current(state, value.actor)
    sheet = state.sheets[value.actor.entity]
    prep = next(x for x in preparations(state) if x.id == value.preparation)
    portable = carried_assets(state, value.actor, carried_items)
    from girlframe.engine.m3_am_neural_route import retained_mental_assets

    retained = (
        retained_mental_assets(state, value.actor, value.neural_route) if value.neural_route else ()
    )
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
        != (
            set(value.mind_assets)
            | {x.id for x in prep.spec.assets}
            | {x.id for x in portable}
            | {x.id for x in retained}
        )
    ):
        raise ValueError(
            "Return only while this actual original pair is still hooked up and colocated"
        )
    mind = tuple(x for x in sheet.assets if x.id in value.mind_assets)
    _ordinary(
        state,
        value.actor,
        mind + old.assets + portable + retained,
        carried_items=carried_items,
        neural_route=value.neural_route,
        destination=old.vessel,
    )
    if carried_items and (not carry_account or not carry_account.strip()):
        raise ValueError("Record actual physical conveyance on this return too")
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
    sheet.assets = (
        [x for x in sheet.assets if x.family == "frame"]
        + list(mind)
        + list(old.assets)
        + list(portable)
        + list(retained)
    )
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
    record_conveyance(
        state,
        value.actor,
        pose.vessel_id,
        old.vessel,
        carried_items,
        portable,
        value.id,
        "return",
        int(value.actor.entity),
        event,
        carry_account,
    )
    result = value.model_copy(update=dict(returned_event=event))
    put(state, "am_body_swap", result.id, result)
    return result
