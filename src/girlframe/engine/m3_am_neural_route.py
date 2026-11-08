"""One real AM mind retains access through its actual fixed spinal interfaces."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine import m3_am_body as bodies
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model


class Endpoint(Model):
    connection: str
    side: Literal["caster", "battery"]
    vessel: str = Field(min_length=1)
    peer: ActorRef
    peer_vessel: str = Field(min_length=1)
    source_event: str


class Move(Model):
    occupancy: str
    previous: str
    vessel: str
    event: str


class Route(Model):
    id: str
    actor: ActorRef
    controller: int
    from_vessel: str
    destination: str
    preparation: str
    preparation_event: str
    endpoints: tuple[Endpoint, ...] = Field(min_length=1)
    event: str
    account: str = Field(min_length=1, max_length=1200)
    moves: tuple[Move, ...] = ()

    @model_validator(mode="after")
    def original_source(self) -> "Route":
        if (
            self.actor.kind != "pilot"
            or self.actor.entity != str(self.controller)
            or self.from_vessel == self.destination
            or len({x.connection for x in self.endpoints}) != len(self.endpoints)
            or any(x.vessel != self.from_vessel for x in self.endpoints)
            or not self.account.strip()
            or len({x.occupancy for x in self.moves}) != len(self.moves)
        ):
            raise ValueError("Keep the actual original AM, fixed interfaces and each genuine move")
        previous = self.from_vessel
        for index, move in enumerate(self.moves):
            if (
                move.previous != previous
                or move.vessel == previous
                or (index == 0 and move.vessel != self.destination)
            ):
                raise ValueError("Preserve the actual source-owned body-movement chain")
            previous = move.vessel
        return self

    @property
    def current_vessel(self) -> str:
        return self.moves[-1].vessel if self.moves else self.from_vessel


def records(state: GameState) -> tuple[Route, ...]:
    return bodies.values(state, "am_neural_route", Route)


def get(state: GameState, identity: str) -> Route:
    value = next((x for x in records(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the original AM's actual neural continuity source")
    return value


def _connected(state: GameState, value: Route) -> tuple[Endpoint, ...]:
    return tuple(
        x
        for x in value.endpoints
        if any(
            c.id == x.connection
            and c.phase == "connected"
            and (
                (x.side == "caster" and c.caster == value.actor and c.battery == x.peer)
                or (x.side == "battery" and c.battery == value.actor and c.caster == x.peer)
            )
            for c in state.neural_connections
        )
    )


def _available(state: GameState, value: Route) -> bool:
    sheet = state.sheets.get(value.actor.entity)
    if sheet is None or sheet.character_id != value.actor.incarnation:
        return False
    pose = next((x for x in state.placements if x.actor == value.actor), None)
    if pose is None or pose.vessel_id != value.current_vessel:
        return False
    if not _connected(state, value):
        return False
    if pose.vessel_id == value.from_vessel:
        return sheet.medical_state == "fit"
    hardware = next((x for x in bodies.bodies(state) if x.vessel == value.from_vessel), None)
    return bool(
        hardware
        and hardware.actor == value.actor
        and hardware.occupant is None
        and hardware.medical == "fit"
    )


def active_route(state: GameState, actor: ActorRef, connection: str | None = None) -> Route | None:
    values = tuple(
        x
        for x in records(state)
        if x.actor == actor
        and x.moves
        and _available(state, x)
        and (connection is None or any(e.connection == connection for e in _connected(state, x)))
    )
    if len(values) > 1:
        raise ValueError("Recover the unique actual AM processing route")
    return values[0] if values else None


def route_endpoint(state: GameState, actor: ActorRef, connection: str) -> Endpoint | None:
    value = active_route(state, actor, connection)
    return next((x for x in value.endpoints if x.connection == connection), None) if value else None


def validate_move(state: GameState, actor: ActorRef, destination: str, route_id: str) -> Route:
    from girlframe.engine import m3_am_jailbroken as occupancy

    value = get(state, route_id)
    if value.actor != actor or not _available(state, value):
        raise ValueError("Use this original AM's actual live processing/interface route")
    actual = set(bodies.spinal_links(state, actor))
    if actual != {x.connection for x in _connected(state, value)}:
        raise ValueError(
            "SOURCE_ROUTE_REFRESH_REQUIRED: prove every actual newly connected endpoint"
        )
    if not value.moves and destination != value.destination:
        raise ValueError("Use the genuine initially prepared destination of this source")
    if destination not in dict(occupancy.available(state, actor)):
        raise ValueError("Use actual available processing-capable hardware, not an invented body")
    return value


def retained_mental_assets(
    state: GameState, actor: ActorRef, route_id: str
) -> tuple[AssetState, ...]:
    value = get(state, route_id)
    if value.actor != actor or not _available(state, value):
        raise ValueError("Preserve the actual AM's live source-owned mental channel")
    links = {
        x.id
        for x in state.battery_links
        if x.caster == actor
        and x.connection in {e.connection for e in _connected(state, value)}
        and x.phase not in ("unplugged", "ended")
    }
    return tuple(
        x
        for x in state.sheets[actor.entity].assets
        if x.battery_asset is not None and x.battery_asset.link in links
    )


def stage_move(
    state: GameState,
    route_id: str,
    actor: ActorRef,
    previous: str,
    vessel: str,
    occupancy: str,
    event: str,
) -> None:
    from girlframe.engine.m3_am_jailbroken import get as actual_occupancy

    value = get(state, route_id)
    actual = actual_occupancy(state, occupancy)
    if (
        value.actor != actor
        or previous != value.current_vessel
        or (actual.actor, actual.previous, actual.vessel, actual.event)
        != (actor, previous, vessel, event)
        or not any(x.actor == actor and x.vessel_id == vessel for x in state.placements)
        or any(x.occupancy == occupancy for x in value.moves)
    ):
        raise ValueError("Bind only the original human's actual canonical occupancy transition")
    changed = value.model_copy(
        update=dict(
            moves=value.moves
            + (Move(occupancy=occupancy, previous=previous, vessel=vessel, event=event),)
        )
    )
    bodies.put(
        state, "am_neural_route", value.id, Route.model_validate_json(changed.model_dump_json())
    )
