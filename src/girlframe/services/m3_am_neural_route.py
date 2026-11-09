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


def _code_birth(game: GameService, c: Connection, state: GameState, value: rules.Route) -> None:
    from girlframe.engine import m3_am_code as code

    source = code.session(state, value.code_maintenance or "")
    audit = _audit(game, c, source.proposed_event)
    if (
        source.actor != value.actor
        or source.owner != value.controller
        or source.phase != "proposed"
        or source.root
        or source.action
        or audit["kind"] != "m3.am_code_proposed"
        or audit["actor_id"] != str(source.owner)
        or json.loads(audit["payload_json"]).get("maintenance") != source.id
    ):
        raise WorkflowError("Prove the actual idle Code proposal, not a Jailbroken entitlement")


def _code_step(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Route,
    move: rules.Move,
    index: int,
) -> None:
    from girlframe.engine import m3_am_code as code
    from girlframe.services.m3_dose_up import _roll_source

    swap = hardware.swap(state, move.swap or "")
    source = code.session(state, value.code_maintenance or "")
    action = game.action(c, swap.action)
    _roll_source(game, c, action)
    rows, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    raw = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            rows,
            sa.and_(
                rows.c.campaign_id == responses.c.campaign_id,
                rows.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == swap.event,
            responses.c.actor_id == str(source.controller),
            rows.c.action_id == swap.action,
            rows.c.kind == "am_code_body",
        )
    )
    answer = json.loads(raw) if raw else {}
    born = hardware.swap(_history(game, c, swap.event), swap.id)
    audit = _audit(game, c, move.event)
    if (
        swap.neural_route != value.id
        or swap.maintenance != source.id
        or swap.actor != value.actor
        or swap.operator != source.operator
        or swap.controller != source.controller
        or swap.preparation != value.preparation
        or source.body_swap != swap.id
        or source.action != swap.action
        or "body" not in source.selected_options
        or born != swap.model_copy(update=dict(returned_event=None))
        or answer.get("options") != [value.preparation]
        or answer.get("fields", {}).get("neural_route") != value.id
        or action["data"].get("am_code", {}).get("maintenance") != source.id
        or action["data"]["result"]["tier"] not in ("mid", "high")
        or hardware._pose(state, value.actor).vessel_id != move.vessel
    ):
        raise WorkflowError("Prove the actual Code receipt, operator choice and immutable Swap")
    if index == 0:
        if (
            (move.previous, move.vessel, move.event)
            != (swap.original_vessel, swap.new_vessel, swap.event)
            or audit["kind"] != "m3.choice_resolved"
            or audit["actor_id"] != str(source.controller)
        ):
            raise WorkflowError("Preserve the actual operator's canonical Code Body response")
    elif (
        index != 1
        or swap.returned_event != move.event
        or (move.previous, move.vessel) != (swap.new_vessel, swap.original_vessel)
        or audit["kind"] != "m3.am_body_returned"
        or audit["actor_id"] != value.actor.entity
        or json.loads(audit["payload_json"]).get("swap") != swap.id
    ):
        raise WorkflowError("Prove only the original AM's real hooked return")


def require_code_move(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    route_id: str,
) -> rules.Route:
    from girlframe.services.m3_am_code import source as code_source
    from girlframe.services.m3_janus_play import prove_link

    value = prove_route(game, c, state, route_id)
    source = code_source(game, c, state, action["data"]["am_code"]["maintenance"])
    rows, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    staged = action["data"].get("choices", {}).get(f"am_code_body:{source.controller}", {})
    response_event = action["data"].get("response_event")
    if (
        value.code_maintenance != source.id
        or source.actor != value.actor
        or source.action != action["id"]
        or source.body_swap
        or value.moves
        or staged.get("options") != [value.preparation]
        or staged.get("fields", {}).get("neural_route") != route_id
        or not response_event
        or c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == response_event,
            )
        )
        is not None
        or not c.scalar(
            sa.select(rows.c.id).where(
                rows.c.campaign_id == game.store.campaign_id,
                rows.c.action_id == action["id"],
                rows.c.kind == "am_code_body",
                rows.c.actor_id == str(source.controller),
                # Game.respond owns/claims the pending row before dispatching this reducer.
                # Its actual response is inserted only after effects and the canonical event.
                rows.c.state == "answered",
                ~sa.exists(
                    sa.select(responses.c.event_id).where(
                        responses.c.campaign_id == rows.c.campaign_id,
                        responses.c.choice_id == rows.c.id,
                    )
                ),
            )
        )
    ):
        raise WorkflowError("Use only this actual operator's currently applied Code Body source")
    for link in state.battery_links:
        if link.caster == value.actor and link.connection in {
            x.connection for x in value.endpoints
        }:
            prove_link(game, c, state, link.id)
    try:
        return rules.validate_move(state, value.actor, value.destination, route_id)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def prove_route(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Route:
    from girlframe.services.m3_frame_control import connection_endpoints
    from girlframe.services.m3_frame_control import prove as prove_contact

    value = rules.get(state, identity)
    born_state = _history(game, c, value.event)
    born = rules.get(born_state, identity)
    audit = _audit(game, c, value.event)
    ready: hardware.Preparation | occupancy.ReadyBody
    if value.code_maintenance is not None:
        from girlframe.services.m3_am_body import prove_preparation as code_preparation

        _code_birth(game, c, born_state, value)
        ready = code_preparation(game, c, born_state, value.preparation)
    else:
        ready = prove_preparation(game, c, born_state, value.preparation)
    if (
        born.moves
        or value != born.model_copy(update=dict(moves=value.moves))
        or audit["kind"]
        != (
            "m3.am_code_route_proposed" if value.code_maintenance else "m3.am_neural_route_proposed"
        )
        or audit["actor_id"] != str(value.controller)
        or json.loads(audit["payload_json"]).get("route") != identity
        or ready.actor != value.actor
        or (not value.code_maintenance and ready.controller != value.controller)
        or (
            value.code_maintenance is not None
            and (
                not isinstance(ready, hardware.Preparation)
                or ready.maintenance != value.code_maintenance
            )
        )
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
        recorded = rules.get(source_state, identity)
        if value.code_maintenance is not None:
            if recorded != born.model_copy(update=dict(moves=value.moves[: index + 1])):
                raise WorkflowError("Preserve every canonical Code route transition")
            _code_step(game, c, source_state, value, move, index)
            continue
        if move.occupancy is None:
            raise WorkflowError("The intrinsic source requires its actual occupancy")
        actual = occupancy.get(source_state, move.occupancy)
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
    if value.code_maintenance is not None:
        raise WorkflowError("Use the actual Code body choice/return, not intrinsic occupancy")
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

    def code_menu(self, viewer: GuildViewer) -> dict[str, Any]:
        from girlframe.engine import m3_am_code as code
        from girlframe.services.m3_am_code import access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            self.game.character_binding(c, state, viewer.user_id)
            return dict(
                revision=state.revision,
                preparations=[
                    dict(id=x.id, maintenance=x.maintenance, label=x.spec.label)
                    for x in hardware.preparations(state)
                    if x.actor == actor
                    and code.session(state, x.maintenance).phase == "proposed"
                    and code.session(state, x.maintenance).root is None
                    and hardware.spinal_links(state, actor)
                    and not any(
                        r.code_maintenance == x.maintenance and r.preparation == x.id
                        for r in rules.records(state)
                    )
                ],
                routes=[
                    dict(id=x.id, label="Actual Code continuous interface")
                    for x in rules.records(state)
                    if x.actor == actor and x.code_maintenance
                ],
            )

    def propose_code(
        self,
        viewer: GuildViewer,
        key: str,
        maintenance: str,
        preparation: str,
        expected: int,
        account: str,
    ) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access

        def change(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_am_body import prove_preparation as code_preparation
            from girlframe.services.m3_am_code import actual, source
            from girlframe.services.m3_frame_control import _bodies, connection_endpoints
            from girlframe.services.m3_frame_control import prove as prove_contact
            from girlframe.services.m3_requisitions import RequisitionService

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, maintenance)
            actual(self.game, c, state, value)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            ready = code_preparation(self.game, c, state, preparation)
            if (
                state.revision != expected
                or viewer.user_id != value.owner
                or current_ref(state, viewer.user_id) != value.actor
                or value.phase != "proposed"
                or value.root
                or value.action
                or ready.maintenance != value.id
                or ready.actor != value.actor
                or ready.operator != value.operator
                or any(
                    x.actor == value.actor
                    and (
                        rules.active_route(state, value.actor) == x
                        or (x.code_maintenance == value.id and x.preparation == preparation)
                    )
                    for x in rules.records(state)
                )
                or any(x.vessel == ready.spec.vessel for x in hardware.bodies(state))
                or state.sheets[value.actor.entity].medical_state != "fit"
            ):
                raise WorkflowError("Record the actual idle Code source and its prepared hardware")
            endpoints = []
            for identity in hardware.spinal_links(state, value.actor):
                contact = prove_contact(self.game, c, state, identity)
                _bodies(self.game, c, state, contact)
                caster, battery = connection_endpoints(self.game, c, contact)
                side: Literal["caster", "battery"] = (
                    "caster" if contact.caster == value.actor else "battery"
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
            route = rules.Route(
                id=event,
                actor=value.actor,
                controller=value.owner,
                from_vessel=hardware._pose(state, value.actor).vessel_id,
                destination=ready.spec.vessel,
                preparation=ready.id,
                preparation_event=ready.event,
                endpoints=tuple(endpoints),
                event=event,
                account=account.strip(),
                code_maintenance=value.id,
            )
            hardware.put(state, "am_neural_route", route.id, route)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_code_route_proposed",
                state,
                event_id=event,
                route=route.id,
                maintenance=value.id,
            )
            return dict(id=route.id)

        return self.store._write(
            viewer,
            key,
            "m3.am_code_route_propose",
            dict(
                maintenance=maintenance,
                preparation=preparation,
                expected=expected,
                account=account,
            ),
            change,
            auto_audit=False,
            authorize=lambda c: access(self.game, c, viewer),
        )

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
            if any(
                x.actor == actor
                and rules._connected(state, x)
                and (x.code_maintenance is None or rules.active_route(state, actor) == x)
                for x in rules.records(state)
            ):
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
                if x.actor == actor and x.code_maintenance is None
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
                and not any(
                    rules._connected(state, x)
                    and (x.code_maintenance is None or rules.active_route(state, actor) == x)
                    for x in values
                ),
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_am_body import carried_options

        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            saved = rules.get(state, identity)
            if saved.code_maintenance is not None:
                from girlframe.services.m3_am_code import access

                access(self.game, c, viewer)
                actor = current_ref(state, viewer.user_id)
                self.game.character_binding(c, state, viewer.user_id)
            else:
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
                phase="returned"
                if value.code_maintenance and len(value.moves) == 2
                else "active"
                if active
                else "ready"
                if live and not value.moves
                else "unavailable"
                if live
                else "ended",
                can_move=not value.code_maintenance and live and rules._available(state, value),
                carried_items=carried_options(self.game, c, state, actor),
                destinations=[]
                if value.code_maintenance
                else [
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
