"""Original-AM-authored continuous access, bound to actual hardware and occupancy."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_body as hardware
from girlframe.engine import m3_am_jailbroken as occupancy
from girlframe.engine import m3_am_neural_route as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_am_jailbroken import JailbrokenService, prove_preparation
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(game: GameService, c: Connection, event: str) -> GameState:
    from girlframe.services.m3_am_jailbroken import _history as history

    return history(game, c, event)


def _audit(game: GameService, c: Connection, event: str) -> dict[str, Any]:
    value = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    if value is None:
        raise WorkflowError("Recover the actual AM neural-route source event")
    return dict(value)


def prove_route(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Route:
    from girlframe.services.m3_frame_control import connection_endpoints
    from girlframe.services.m3_frame_control import prove as prove_contact

    value = rules.get(state, identity)
    born_state = _history(game, c, value.event)
    born = rules.get(born_state, identity)
    audit = _audit(game, c, value.event)
    ready = prove_preparation(game, c, born_state, value.preparation)
    if (
        born.moves
        or value != born.model_copy(update=dict(moves=value.moves))
        or audit["kind"] != "m3.am_neural_route_proposed"
        or audit["actor_id"] != str(value.controller)
        or json.loads(audit["payload_json"]).get("route") != identity
        or ready.actor != value.actor
        or ready.controller != value.controller
        or ready.spec.vessel != value.destination
        or ready.event != value.preparation_event
        or hardware._pose(born_state, value.actor).vessel_id != value.from_vessel
        or set(hardware.spinal_links(born_state, value.actor))
        != {x.connection for x in value.endpoints}
    ):
        raise WorkflowError("Preserve the original human, hardware and complete interface source")
    for endpoint in value.endpoints:
        contact = prove_contact(game, c, born_state, endpoint.connection)
        caster, battery = connection_endpoints(game, c, contact)
        source = rules.Endpoint(
            connection=contact.id,
            side="caster" if contact.caster == value.actor else "battery",
            vessel=caster if contact.caster == value.actor else battery,
            peer=contact.battery if contact.caster == value.actor else contact.caster,
            peer_vessel=battery if contact.caster == value.actor else caster,
            source_event=str(contact.connected_event),
        )
        if endpoint != source or contact.phase != "connected":
            raise WorkflowError("Keep the actual reviewed fixed original spinal endpoints")
    for index, move in enumerate(value.moves):
        source_state = _history(game, c, move.event)
        actual = occupancy.get(source_state, move.occupancy)
        recorded = rules.get(source_state, identity)
        move_audit = _audit(game, c, move.event)
        if (
            recorded != born.model_copy(update=dict(moves=value.moves[: index + 1]))
            or (actual.actor, actual.previous, actual.vessel, actual.event)
            != (value.actor, move.previous, move.vessel, move.event)
            or getattr(actual, "neural_route", None) != identity
            or move_audit["kind"] != "m3.am_jailbroken_occupied"
            or move_audit["actor_id"] != str(value.controller)
            or json.loads(move_audit["payload_json"]).get("occupancy") != move.occupancy
            or json.loads(move_audit["payload_json"]).get("neural_route") != identity
            or hardware._pose(source_state, value.actor).vessel_id != move.vessel
        ):
            raise WorkflowError("Prove every actual same-source occupancy and canonical route step")
        if actual.preparation:
            target = prove_preparation(game, c, source_state, actual.preparation)
            if target.actor != value.actor or target.spec.vessel != move.vessel:
                raise WorkflowError("Preserve genuine destination processing/hardware provenance")
    return value


def require_move(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    actor: ActorRef,
    destination: str,
    route_id: str,
) -> rules.Route:
    JailbrokenService(game)._actor(c, viewer, state, actor)
    value = prove_route(game, c, state, route_id)
    from girlframe.services.m3_janus_play import prove_link

    for link in state.battery_links:
        if link.caster == actor and link.connection in {x.connection for x in value.endpoints}:
            prove_link(game, c, state, link.id)
    target = next(
        (
            x
            for x in occupancy.preparations(state)
            if x.actor == actor and x.spec.vessel == destination
        ),
        None,
    )
    if target:
        prove_preparation(game, c, state, target.id)
    try:
        return rules.validate_move(state, actor, destination, route_id)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def require_connection_route(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    connection: str,
) -> rules.Route | None:
    value = rules.active_route(state, actor, connection)
    return prove_route(game, c, state, value.id) if value else None


class RouteService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _own(self, c: Connection, viewer: GuildViewer) -> tuple[GameState, ActorRef]:
        state = load_state(c, self.store.campaign_id)
        actor = current_ref(state, viewer.user_id)
        JailbrokenService(self.game)._actor(c, viewer, state, actor)
        return state, actor

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        destination: str,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_frame_control import (
                _bodies,
                connection_endpoints,
            )
            from girlframe.services.m3_frame_control import (
                prove as prove_contact,
            )
            from girlframe.services.m3_requisitions import RequisitionService

            self.game.unpaused(c)
            state, actor = self._own(c, viewer)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if state.revision != expected:
                raise WorkflowError("STALE_AM_ROUTE: reopen the original current hardware")
            pose = hardware._pose(state, actor)
            if state.sheets[actor.entity].medical_state != "fit":
                raise WorkflowError(
                    "SOURCE_PROCESSING_ROUTE_REQUIRED: review actual powered hardware"
                )
            if any(x.actor == actor and rules._connected(state, x) for x in rules.records(state)):
                raise WorkflowError(
                    "Use the existing source route; new interface changes need review"
                )
            ready = next(
                (
                    x
                    for x in occupancy.preparations(state)
                    if x.actor == actor and x.spec.vessel == destination
                ),
                None,
            )
            if ready is None or destination not in dict(occupancy.available(state, actor)):
                raise WorkflowError(
                    "Prepare genuine empty processing-capable hardware before contact"
                )
            prove_preparation(self.game, c, state, ready.id)
            endpoints = []
            for identity in hardware.spinal_links(state, actor):
                contact = prove_contact(self.game, c, state, identity)
                _bodies(self.game, c, state, contact)
                caster, battery = connection_endpoints(self.game, c, contact)
                side: Literal["caster", "battery"] = (
                    "caster" if contact.caster == actor else "battery"
                )
                endpoints.append(
                    rules.Endpoint(
                        connection=contact.id,
                        side=side,
                        vessel=caster if side == "caster" else battery,
                        peer=contact.battery if side == "caster" else contact.caster,
                        peer_vessel=battery if side == "caster" else caster,
                        source_event=str(contact.connected_event),
                    )
                )
            event = str(uuid4())
            value = rules.Route(
                id=event,
                actor=actor,
                controller=viewer.user_id,
                from_vessel=pose.vessel_id,
                destination=destination,
                preparation=ready.id,
                preparation_event=ready.event,
                endpoints=tuple(endpoints),
                event=event,
                account=account.strip(),
            )
            hardware.put(state, "am_neural_route", value.id, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_neural_route_proposed",
                state,
                event_id=event,
                route=value.id,
            )
            return dict(id=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.am_neural_route_propose",
            dict(
                expected=expected,
                destination=destination,
                account=account,
            ),
            change,
            auto_audit=False,
        )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, actor = self._own(c, viewer)
            destinations = []
            for ready in occupancy.preparations(state):
                if ready.actor == actor and ready.spec.vessel in dict(
                    occupancy.available(state, actor)
                ):
                    prove_preparation(self.game, c, state, ready.id)
                    destinations.append(dict(vessel=ready.spec.vessel, label=ready.spec.label))
            values = [
                prove_route(self.game, c, state, x.id)
                for x in rules.records(state)
                if x.actor == actor
            ]
            return dict(
                actor=actor.model_dump(mode="json"),
                revision=state.revision,
                connected=bool(hardware.spinal_links(state, actor)),
                destinations=destinations,
                routes=[
                    dict(
                        id=x.id,
                        label="Actual continuous neural route",
                        active=rules.active_route(state, actor) == x,
                    )
                    for x in values
                ],
                can_propose=bool(hardware.spinal_links(state, actor))
                and not any(rules._connected(state, x) for x in values),
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_am_body import carried_options

        with self.store.engine.connect() as c:
            state, actor = self._own(c, viewer)
            value = prove_route(self.game, c, state, identity)
            if value.actor != actor or value.controller != viewer.user_id:
                raise WorkflowError("This processing/continuity source belongs to its original AM")
            live = bool(rules._connected(state, value))
            active = rules.active_route(state, actor) == value
            return dict(
                id=identity,
                revision=state.revision,
                route=value.model_dump(mode="json"),
                phase="active"
                if active
                else "ready"
                if live and not value.moves
                else "unavailable"
                if live
                else "ended",
                can_move=live and rules._available(state, value),
                carried_items=carried_options(self.game, c, state, actor),
                destinations=[
                    dict(vessel=vessel, label=label)
                    for vessel, label in occupancy.available(state, actor)
                    if value.moves or vessel == value.destination
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                phase="saved",
                pending=False,
                label="Actual AM continuous interface source",
            )
            for x in rules.records(state)
            if x.controller == viewer.user_id
        ]
