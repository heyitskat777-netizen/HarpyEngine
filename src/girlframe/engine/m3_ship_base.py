"""One actual Base as a fast ship; its occupants are proved physical records, not actors."""

import json
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_collateral import Selection, Source, perform
from girlframe.engine.m3_physical import _save
from girlframe.engine.m3_world import damage_gorgon, update
from girlframe.engine.m3_world_state import Cell, Location, ShipPin

RULE = "handler-advancement.handler-advancement.ship-base"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str
    base: str
    original_base_json: str


class Boarding(Model):
    id: str
    acquisition: str
    ship: str
    actor: ActorRef
    controller: int
    parts: Literal["body", "frame", "both"]
    vessel: str | None = None
    frame: str | None = None
    event: str
    account: str
    left_event: str | None = None


class Flight(Model):
    id: str
    acquisition: str
    ship: str
    handler: ActorRef
    origin: Cell
    destination: Cell
    airborne: bool
    manifest: tuple[str, ...]
    event: str
    account: str


class Ram(Model):
    id: str
    acquisition: str
    ship: str
    handler: ActorRef
    appointment: str
    threat: ActorRef
    threat_controller: int
    ship_before: str
    threat_before: str
    basis: Literal["plain", "opportunity", "armoured"]
    opportunity: str | None = None
    faces: tuple[int, int]
    modifier: Literal[0, 2, 4]
    total: int
    tier: Literal["low", "mid", "high"]
    rng: Literal["os", "test_injected"]
    asset: str
    event: str
    account: str
    judge: int
    judge_appointment: str
    cadre: tuple[ActorRef, ...]
    low_grant: str | None = None
    phase: Literal["awaiting_play", "complete"] = "complete"
    completed_event: str | None = None
    loss: str | None = None


def records[T: Model](state: GameState, cls: type[T]) -> tuple[T, ...]:
    kind = {
        Acquisition: "ship_acquisition",
        Boarding: "ship_boarding",
        Flight: "ship_flight",
        Ram: "ship_ram",
    }[cls]
    return tuple(cls.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == kind)


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return records(state, Acquisition)


def put(state: GameState, value: Acquisition | Boarding | Flight | Ram) -> None:
    kind = {
        Acquisition: "ship_acquisition",
        Boarding: "ship_boarding",
        Flight: "ship_flight",
        Ram: "ship_ram",
    }[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def base(state: GameState, identity: str) -> Location:
    value = (
        next((x for x in state.world.locations if x.id == identity), None) if state.world else None
    )
    if value is None or value.ship is None:
        raise ValueError("Recover the actual source-owned Ship-Base")
    return value


def position_fact(
    state: GameState, boarding: Boarding, cell: Cell, event: str, account: str
) -> None:
    state.facts.append(
        dict(
            kind="ship_base_actual_position",
            actor=boarding.actor.model_dump_json(),
            cell=json.dumps(cell),
            ship=boarding.ship,
            boarding=boarding.id,
            event=event,
            account=account,
        )
    )


def move(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    source: Acquisition,
    destination: Cell,
    airborne: bool,
    identity: str,
    event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    ship = base(state, source.base)
    if (
        not ship.operational
        or state.world is None
        or not state.world.board.contains(destination)
        or not account.strip()
    ):
        raise ValueError("Fly the actual operational Base to an actual map cell")
    manifest = [x for x in records(state, Boarding) if x.ship == ship.id and x.left_event is None]
    for entry in manifest:
        actor = resolve(state, entry.actor, bindings, require_current_profile=False)
        if (
            actor.controller != entry.controller
            or actor.offstage_source
            or actor.custody not in (None, "free")
        ):
            raise ValueError("Resolve changed/offstage/custodied cargo before flying")
        if entry.actor.kind == "pilot":
            physical = next((x for x in state.placements if x.actor == entry.actor), None)
            if (
                physical is None
                or physical.vessel_id != entry.vessel
                or physical.occupied_frame_owner is not None
                or any(x.state == "boarded" and x.carrier == entry.actor for x in state.passengers)
                or entry.parts in ("body", "both")
                and physical.girl_cell != ship.cell
                or entry.parts in ("frame", "both")
                and (physical.frame_instance != entry.frame or physical.frame_cell != ship.cell)
                or physical.mode != "outside_frame"
                and entry.parts != "both"
            ):
                raise ValueError(
                    "Prove the actual contained original body and Frame, never same-cell bystanders"
                )
            _save(
                state,
                physical.model_copy(
                    update=dict(
                        girl_cell=destination
                        if entry.parts in ("body", "both")
                        else physical.girl_cell,
                        frame_cell=destination
                        if entry.parts in ("frame", "both")
                        else physical.frame_cell,
                        source_event=event,
                        account=account,
                    )
                ),
            )
        elif entry.actor.kind == "handler":
            if actor.rules != "handler" or actor.cell != ship.cell:
                raise ValueError("Use the actual original Handler's genuinely boarded body")
            position_fact(state, entry, destination, event, account)
        elif entry.actor.kind == "npc":
            if actor.cell != ship.cell or "director" in actor.jobs:
                raise ValueError("Use the actual boarded ordinary NPC at this Base")
            state.world = update(
                state.world,
                npcs=tuple(
                    x.model_copy(update=dict(cell=destination)) if x.id == entry.actor.entity else x
                    for x in state.world.npcs
                ),
            )
        else:
            raise ValueError("SOURCE_PORT_REQUIRED: this body's actual ship containment adapter")
    assert ship.ship is not None and state.world is not None
    state.world = update(
        state.world,
        locations=tuple(
            x.model_copy(
                update=dict(
                    cell=destination, ship=ship.ship.model_copy(update=dict(airborne=airborne))
                )
            )
            if x.id == ship.id
            else x
            for x in state.world.locations
        ),
    )
    put(
        state,
        Flight(
            id=identity,
            acquisition=source.id,
            ship=ship.id,
            handler=source.handler,
            origin=ship.cell,
            destination=destination,
            airborne=airborne,
            manifest=tuple(x.id for x in manifest),
            event=event,
            account=account,
        ),
    )
    return state


def damage_armour(state: GameState, ship_id: str) -> None:
    ship = base(state, ship_id)
    assert ship.ship is not None and state.world is not None
    if ship.ship.armoured:
        hull = ship.ship.model_copy(
            update=dict(armoured=False, damage_count=ship.ship.damage_count + 1)
        )
        state.world = update(
            state.world,
            locations=tuple(
                x.model_copy(update=dict(ship=hull)) if x.id == ship_id else x
                for x in state.world.locations
            ),
        )


def rearm(state: GameState, period: str, event: str) -> bool:
    if state.world is None:
        return False
    changed = False
    locations = []
    for location in state.world.locations:
        hull = location.ship
        if (
            hull is not None
            and not hull.armoured
            and location.operational
            and hull.rearm_period != period
        ):
            location = location.model_copy(
                update=dict(
                    ship=hull.model_copy(
                        update=dict(armoured=True, rearm_period=period, rearm_event=event)
                    )
                )
            )
            changed = True
        locations.append(location)
    if changed:
        state.world = update(state.world, locations=tuple(locations))
    return changed


def apply_ram(state: GameState, value: Ram) -> GameState:
    result = GameState.model_validate_json(state.model_dump_json())
    assert result.world is not None
    if value.tier == "low":
        damage_armour(result, value.ship)
    else:
        result.world = update(
            result.world,
            gorgons=tuple(
                x.model_copy(update=dict(exposed=True)) if x.id == value.threat.entity else x
                for x in result.world.gorgons
            ),
        )
        pin = ShipPin(
            id="ship-pin:" + value.id,
            ship=value.ship,
            threat=value.threat.entity,
            ram=value.id,
            source_event=value.event,
        )
        result.world = update(result.world, ship_pins=result.world.ship_pins + (pin,))
        if value.tier == "high":
            result.world = damage_gorgon(
                result.world, value.threat.entity, value.asset, indirect=False
            )
            hull = base(result, value.ship).ship
            assert hull is not None
            if hull.armoured:
                damage_armour(result, value.ship)
            else:
                result, loss = perform(
                    result,
                    Source(
                        id=value.id,
                        action=value.id,
                        choice=value.id + ":high",
                        event=value.event,
                        actor=value.handler,
                        actor_controller=int(value.handler.entity),
                        judge=value.judge,
                        appointment=value.judge_appointment,
                        handler=value.handler,
                    ),
                    Selection(structures=(value.ship,), account=value.account, reach=value.account),
                    value.event,
                )
                if loss:
                    value = value.model_copy(update=dict(loss=loss.id))
    put(result, value)
    return result


def release_pin(state: GameState, threat: str, ship: str, event: str, action: str) -> None:
    if state.world is None:
        return
    state.world = update(
        state.world,
        ship_pins=tuple(
            x.model_copy(update=dict(released_event=event, release_action=action))
            if x.threat == threat and x.ship == ship and x.released_event is None
            else x
            for x in state.world.ship_pins
        ),
    )


def low_grant_id(ram: str) -> str:
    return "ship-low:" + str(uuid5(NAMESPACE_URL, ram))
