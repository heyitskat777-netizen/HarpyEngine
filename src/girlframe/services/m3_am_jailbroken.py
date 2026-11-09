"""Original player's voluntary AM occupancy, independent of discovery and circuits."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_body as hardware
from girlframe.engine import m3_am_jailbroken as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(game: GameService, c: Connection, event: str) -> GameState:
    table = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id, table.c.event_id == event
        )
    )
    if raw is None:
        raise WorkflowError("Recover the original voluntary occupancy hardware source")
    return GameState.model_validate_json(raw)


def _audit(game: GameService, c: Connection, event: str, kind: str, actor: int) -> None:
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if row is None or (row.kind, row.actor_id) != (kind, str(actor)):
        raise WorkflowError("Recover this actual original AM's voluntary source event")


def prove_preparation(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.ReadyBody:
    value = next((x for x in rules.preparations(state) if x.id == identity), None)
    if value is None or value not in rules.preparations(_history(game, c, value.event)):
        raise WorkflowError("Recover the actual empty processing-capable hardware preparation")
    _audit(game, c, value.event, "m3.am_jailbroken_prepared", value.controller)
    if value.actor.kind != "pilot" or value.actor.entity != str(value.controller):
        raise WorkflowError("The actual original AM records her own prepared hardware facts")
    from girlframe.services.m3_am_body import _prove_items

    _prove_items(game, c, _history(game, c, value.event), value.actor, value.spec.carried_items)
    return value


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Occupancy:
    value = rules.get(state, identity)
    original = _history(game, c, value.event)
    if value != rules.get(original, identity):
        raise WorkflowError("Recover the actual immutable same-mind occupancy record")
    _audit(game, c, value.event, "m3.am_jailbroken_occupied", int(value.actor.entity))
    if value.preparation:
        ready = prove_preparation(game, c, state, value.preparation)
        if ready.actor != value.actor or ready.spec.vessel != value.vessel:
            raise WorkflowError("Preserve the actual appropriate-body source")
    if next((x for x in original.placements if x.actor == value.actor), None) != value.current_pose:
        raise WorkflowError("Recover the actual occupied physical vessel")
    for body in hardware.bodies(state):
        if body.actor == value.actor and body not in hardware.bodies(_history(game, c, body.event)):
            raise WorkflowError("Recover actual saved hardware conditions without healing")
    if value.neural_route is not None:
        from girlframe.services.m3_am_neural_route import prove_route

        route = prove_route(game, c, state, value.neural_route)
        if not any(
            x.occupancy == value.id
            and x.event == value.event
            and x.previous == value.previous
            and x.vessel == value.vessel
            for x in route.moves
        ):
            raise WorkflowError("Preserve the actual occupancy's canonical continuous route")
    if value.carried_items:
        from girlframe.services.m3_am_body import prove_conveyance

        prove_conveyance(game, c, state, value.event)
    return value


class JailbrokenService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        assert access.registry is not None
        access.registry.require_available(rules.RULE)

    def _actor(self, c: Connection, viewer: GuildViewer, state: GameState, actor: ActorRef) -> None:
        self._access(c, viewer)
        if actor.kind != "pilot" or actor.entity != str(viewer.user_id):
            raise WorkflowError("Only the actual current AM chooses her own occupancy")
        self.game.character_binding(c, state, viewer.user_id)
        actual = resolve(state, actor, profiles(c, self.store.campaign_id))
        if actual.controller != viewer.user_id or actual.girl != "AM":
            raise WorkflowError("Use the same actual current AM")
        from girlframe.engine.m3_am_branch import branch
        from girlframe.services.m3_am_branch import prove as prove_branch

        source = branch(state, actor)
        if source:
            prove_branch(self.game, c, state, source.id)
        hardware._pose(state, actor)
        for entry in rules.history(state, actor):
            prove(self.game, c, state, entry.id)

    def view(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            actor = (
                rules.get(state, identity).actor if identity else current_ref(state, viewer.user_id)
            )
            self._actor(c, viewer, state, actor)
            body = hardware.current(state, actor)
            pose = hardware._pose(state, actor)
            girls = [x for x in state.sheets[actor.entity].assets if x.family == "girl"]
            from girlframe.services.m3_am_body import (
                carried_options,
                project_hardware,
                prove_conveyance,
            )

            return dict(
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                capabilities=rules.capabilities(state, actor),
                current=project_hardware(state, body)
                if body
                else dict(
                    vessel=pose.vessel_id,
                    cell=pose.girl_cell,
                    assets=[x.model_dump(mode="json") for x in girls],
                    medical=state.sheets[actor.entity].medical_state,
                ),
                mind_assets=[
                    x.model_dump(mode="json")
                    for x in girls
                    if x.id not in hardware.carried_ids(state, actor)
                ],
                carried_items=carried_options(self.game, c, state, actor),
                conveyances=[
                    prove_conveyance(self.game, c, state, x.event).model_dump(mode="json")
                    for x in hardware.conveyances(state)
                    if x.actor == actor
                ],
                classified=rules.mind_assets(state, actor),
                available=[
                    dict(vessel=vessel, label=label)
                    for vessel, label in rules.available(state, actor)
                ],
                history=[x.model_dump(mode="json") for x in rules.history(state, actor)],
                bodies=[
                    project_hardware(state, x) for x in hardware.bodies(state) if x.actor == actor
                ],
            )

    def prepare(
        self, viewer: GuildViewer, key: str, actor: ActorRef, expected: int, spec: hardware.BodySpec
    ) -> dict[str, Any]:
        from girlframe.services.m3_requisitions import RequisitionService

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._actor(c, viewer, state, actor)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if state.revision != expected:
                raise WorkflowError("STALE_AM_OCCUPANCY: refresh the actual current body")
            event = str(uuid4())
            from girlframe.services.m3_am_body import _prove_items

            _prove_items(self.game, c, state, actor, spec.carried_items)
            value = rules.prepare(state, actor, spec, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_jailbroken_prepared",
                state,
                event_id=event,
                preparation=value.id,
            )
            return dict(id=value.id, vessel=value.spec.vessel)

        return self.store._write(
            viewer,
            key,
            "m3.am_jailbroken_prepare",
            dict(
                actor=actor.model_dump(mode="json"),
                expected=expected,
                spec=spec.model_dump(mode="json"),
            ),
            change,
            auto_audit=False,
        )

    def occupy(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: int,
        vessel: str,
        *,
        carried_items: tuple[str, ...] = (),
        carry_account: str | None = None,
        neural_route: str | None = None,
    ) -> dict[str, Any]:
        from girlframe.services.m3_requisitions import RequisitionService

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._actor(c, viewer, state, actor)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if state.revision != expected:
                raise WorkflowError("STALE_AM_OCCUPANCY: refresh the actual current body")
            target = next((x for x in rules.preparations(state) if x.spec.vessel == vessel), None)
            if target:
                prove_preparation(self.game, c, state, target.id)
            if neural_route is not None:
                from girlframe.services.m3_am_neural_route import require_move

                require_move(self.game, c, state, viewer, actor, vessel, neural_route)
            event = str(uuid4())
            from girlframe.services.m3_am_body import _prove_items

            _prove_items(self.game, c, state, actor, carried_items)
            value = rules.occupy(
                state,
                actor,
                vessel,
                event,
                carried_items=carried_items,
                carry_account=carry_account,
                neural_route=neural_route,
            )
            if neural_route is not None:
                from girlframe.engine.m3_am_neural_route import stage_move

                stage_move(
                    state, neural_route, actor, value.previous, value.vessel, value.id, event
                )
            audit: dict[str, Any] = (
                {"neural_route": neural_route} if neural_route is not None else {}
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_jailbroken_occupied",
                state,
                event_id=event,
                occupancy=value.id,
                **audit,
            )
            from girlframe.services.m3_am_body_consequences import synchronize

            synchronize(self.game, c, event)
            return dict(id=value.id, vessel=value.vessel)

        return self.store._write(
            viewer,
            key,
            "m3.am_jailbroken_occupy",
            dict(
                actor=actor.model_dump(mode="json"),
                expected=expected,
                vessel=vessel,
                **({"neural_route": neural_route} if neural_route is not None else {}),
                **(
                    dict(carried_items=carried_items, carry_account=carry_account)
                    if carried_items or carry_account is not None
                    else {}
                ),
            ),
            change,
            auto_audit=False,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                pending=False,
                label="Actual self-directed AM occupancy history",
                phase="saved",
            )
            for x in rules.history(state)
            if x.actor.entity == str(viewer.user_id)
        ]
