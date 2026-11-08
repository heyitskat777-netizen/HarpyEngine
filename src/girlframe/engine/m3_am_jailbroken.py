"""Intrinsic AM occupancy: one actual mind, source-proven physical hardware."""

from uuid import uuid4

from pydantic import Field

from girlframe.engine import m3_am_body as hardware
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_am import FREEDOMS, free
from girlframe.engine.m3_physical_state import Placement

RULE = "girl.am.jailbroken"


class ReadyBody(Model):
    id: str
    actor: ActorRef
    controller: int
    cell: tuple[int, int]
    spec: hardware.BodySpec
    event: str


class Occupancy(Model):
    id: str
    actor: ActorRef
    previous: str
    vessel: str
    preparation: str | None
    mind_assets: tuple[str, ...]
    carried_items: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    previous_pose: Placement
    current_pose: Placement
    event: str


def preparations(state: GameState) -> tuple[ReadyBody, ...]:
    return hardware.values(state, "am_jailbroken_prepared", ReadyBody)


def history(state: GameState, actor: ActorRef | None = None) -> tuple[Occupancy, ...]:
    return tuple(
        x
        for x in hardware.values(state, "am_jailbroken_occupancy", Occupancy)
        if actor is None or x.actor == actor
    )


def get(state: GameState, identity: str) -> Occupancy:
    value = next((x for x in history(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual self-directed AM occupancy source")
    return value


def mind_assets(state: GameState, actor: ActorRef) -> tuple[str, ...] | None:
    past = history(state, actor)
    if past:
        return past[-1].mind_assets
    code = [x for x in hardware.swaps(state) if x.actor == actor]
    return code[-1].mind_assets if code else None


def capabilities(state: GameState, actor: ActorRef) -> dict[str, bool]:
    hardware._pose(state, actor)
    return dict(
        occupancy=True,
        voice_control=True,
        expression_control=True,
        near_instant_calculation=True,
        must_smile=not free(state, actor, "expression"),
        **{name: free(state, actor, name) for name, _ in FREEDOMS},
    )


def prepare(state: GameState, actor: ActorRef, spec: hardware.BodySpec, event: str) -> ReadyBody:
    pose = hardware._pose(state, actor)
    assert pose.girl_cell is not None
    known = {x.id for sheet in state.sheets.values() for x in sheet.assets}
    known.update(x.id for b in hardware.bodies(state) for x in b.assets)
    known.update(x.id for p in hardware.preparations(state) for x in p.spec.assets)
    known.update(x.id for p in preparations(state) for x in p.spec.assets)
    vessels = {x.vessel_id for x in state.placements}
    vessels.update(x.vessel for x in hardware.bodies(state))
    vessels.update(x.spec.vessel for x in hardware.preparations(state))
    vessels.update(x.spec.vessel for x in preparations(state))
    girls = {x.id: x for x in state.sheets[actor.entity].assets if x.family == "girl"}
    classified = mind_assets(state, actor)
    if (
        not event
        or not spec.source.strip()
        or not spec.label.strip()
        or not spec.vessel.strip()
        or spec.vessel in vessels
        or known & {x.id for x in spec.assets}
        or len(set(spec.mind_assets)) != len(spec.mind_assets)
        or not set(spec.mind_assets) <= girls.keys()
        or classified is not None
        and set(classified) != set(spec.mind_assets)
    ):
        raise ValueError(
            "Use genuinely available empty hardware and preserve real mind-linked sources"
        )
    portable = hardware.carried_assets(state, actor, spec.carried_items)
    if set(spec.mind_assets) & {x.id for x in portable}:
        raise ValueError("A physical held object is not a mind-linked Asset")
    hardware._ordinary(
        state,
        actor,
        tuple(girls[x] for x in spec.mind_assets) + spec.assets + portable,
        carried_items=spec.carried_items,
    )
    value = ReadyBody(
        id=str(uuid4()),
        actor=actor,
        controller=int(actor.entity),
        cell=pose.girl_cell,
        spec=spec,
        event=event,
    )
    hardware.put(state, "am_jailbroken_prepared", value.id, value)
    return value


def current(state: GameState, actor: ActorRef) -> hardware.Body | None:
    if not history(state, actor):
        return None
    pose = hardware._pose(state, actor)
    body = next((x for x in hardware.bodies(state) if x.vessel == pose.vessel_id), None)
    if body is None or body.actor != actor or body.occupant != actor:
        raise ValueError("Recover the actual current same-mind occupied hardware")
    ids = {x.id for x in state.sheets[actor.entity].assets if x.family == "girl"}
    return hardware._body(
        state,
        actor,
        pose,
        ids - set(mind_assets(state, actor) or ()) - hardware.carried_ids(state, actor),
        body.event,
        body.label,
        actor,
        body.origin_event,
    )


def available(state: GameState, actor: ActorRef) -> tuple[tuple[str, str], ...]:
    pose = hardware._pose(state, actor)
    result = [
        (p.spec.vessel, p.spec.label)
        for p in preparations(state)
        if p.actor == actor
        and p.cell == pose.girl_cell
        and not any(x.vessel == p.spec.vessel for x in hardware.bodies(state))
    ]
    result += [
        (b.vessel, b.label)
        for b in hardware.bodies(state)
        if b.actor == actor and b.occupant is None and b.cell == pose.girl_cell
    ]
    return tuple(result)


def occupy(
    state: GameState,
    actor: ActorRef,
    vessel: str,
    event: str,
    *,
    carried_items: tuple[str, ...] = (),
    carry_account: str | None = None,
) -> Occupancy:
    old = hardware._pose(state, actor)
    if not event or vessel not in dict(available(state, actor)):
        raise ValueError("Occupy actual available empty processing-capable hardware")
    sheet = state.sheets[actor.entity]
    prepared = next(
        (x for x in preparations(state) if x.actor == actor and x.spec.vessel == vessel), None
    )
    target = next((x for x in hardware.bodies(state) if x.vessel == vessel), None)
    ids = mind_assets(state, actor)
    if ids is None:
        if prepared is None:
            raise ValueError("Recover the actual initial mind-linked Asset classification")
        ids = prepared.spec.mind_assets
    mind = tuple(x for x in sheet.assets if x.id in ids)
    if len(mind) != len(ids):
        raise ValueError("SOURCE_BODY_CLASSIFICATION_REQUIRED: preserve changed mental resources")
    if target is None:
        if prepared is None:
            raise ValueError("Recover the actual prepared body source")
        target = hardware.Body(
            vessel=vessel,
            actor=actor,
            label=prepared.spec.label,
            cell=prepared.cell,
            assets=prepared.spec.assets,
            medical=prepared.spec.medical,
            occupant=None,
            origin_event=prepared.event,
            event=prepared.event,
        )
    portable = hardware.carried_assets(state, actor, carried_items)
    if set(ids) & {x.id for x in portable}:
        raise ValueError("A physical object cannot be silently classified as software")
    if prepared and target.event == prepared.event and carried_items != prepared.spec.carried_items:
        raise ValueError("Select the original prepared physical objects for actual conveyance")
    hardware._ordinary(state, actor, mind + target.assets + portable, carried_items=carried_items)
    if carried_items and (not carry_account or not carry_account.strip()):
        raise ValueError("Record actual performed object conveyance on this occupancy")
    previous = next((x for x in hardware.bodies(state) if x.vessel == old.vessel_id), None)
    parked = hardware._body(
        state,
        actor,
        old,
        {x.id for x in sheet.assets if x.family == "girl"} - set(ids) - {x.id for x in portable},
        event,
        previous.label if previous else "Original AM body",
        None,
        previous.origin_event if previous else old.proposed_event,
    )
    hardware.put(state, "am_body_hardware", parked.vessel, parked)
    sheet.assets = (
        [x for x in sheet.assets if x.family == "frame"]
        + list(mind)
        + list(target.assets)
        + list(portable)
    )
    sheet.medical_state = target.medical
    sheet.revision += 1
    pose = old.model_copy(
        update=dict(
            vessel_id=target.vessel,
            girl_cell=target.cell,
            proposed_event=target.origin_event,
            source_event=event,
            account="Actual self-directed Jailbroken occupancy",
            incapacitated=target.medical != "fit",
            vitals_active=True,
        )
    )
    state.placements = [pose if x.actor == actor else x for x in state.placements]
    hardware.put(
        state,
        "am_body_hardware",
        target.vessel,
        target.model_copy(update=dict(occupant=actor, event=event)),
    )
    result = Occupancy(
        id=str(uuid4()),
        actor=actor,
        previous=old.vessel_id,
        vessel=vessel,
        preparation=prepared.id if prepared else None,
        mind_assets=ids,
        carried_items=carried_items,
        previous_pose=old,
        current_pose=pose,
        event=event,
    )
    hardware.put(state, "am_jailbroken_occupancy", result.id, result)
    hardware.record_conveyance(
        state,
        actor,
        old.vessel_id,
        vessel,
        carried_items,
        portable,
        result.id,
        "jailbroken",
        int(actor.entity),
        event,
        carry_account,
    )
    return result
