"""Real factual vehicle classification and genuine source-owned destruction."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vehicles as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Vehicle:
    from girlframe.services.m3_dose_up import _audit

    value = next((x for x in rules.vehicles(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual assessed regular vehicle")
    birth = _history(c, game, value.event)
    original = next((x for x in rules.vehicles(birth) if x.id == value.id), None)
    if original is None or any(
        getattr(original, k) != getattr(value, k)
        for k in ("id", "name", "description", "cell", "scene", "assessed_by", "event", "occupancy")
    ):
        raise WorkflowError("Preserve the vehicle's genuine factual classification and position")
    _audit(game, c, value.event, ("m3.regular_vehicle_assessed",), value.assessed_by)
    if birth.handler != value.assessed_by:
        raise WorkflowError("Use the actual source Handler's vehicle classification")
    if value.destroyed_event:
        saved = _history(c, game, value.destroyed_event)
        actual = next((x for x in rules.vehicles(saved) if x.id == value.id), None)
        if actual != value or not value.source_action:
            raise WorkflowError("Recover the real destroyed vehicle source")
        from girlframe.services.m3_dose_up import _roll_source

        action = game.action(c, value.source_action)
        _roll_source(game, c, action)
        response, choices = t.m2["m2_responses"], t.m2["m2_choices"]
        rows = (
            c.execute(
                sa.select(response.c.answer_json, choices.c.actor_id)
                .select_from(
                    response.join(
                        choices,
                        sa.and_(
                            choices.c.campaign_id == response.c.campaign_id,
                            choices.c.id == response.c.choice_id,
                        ),
                    )
                )
                .where(
                    response.c.campaign_id == game.store.campaign_id,
                    response.c.event_id == value.destroyed_event,
                    choices.c.action_id == value.source_action,
                    choices.c.kind == "engage_maneuvers",
                    response.c.actor_id == action["actor_id"],
                    choices.c.actor_id == action["actor_id"],
                )
            )
            .mappings()
            .all()
        )
        matching = [json.loads(x["answer_json"]) for x in rows]
        if action["data"].get("play") != "engage" or not any(
            "crush_small" in x.get("options", [])
            and x.get("fields", {}).get("wyvern_vehicle") == value.id
            and x.get("fields", {}).get("crush_small")
            for x in matching
        ):
            raise WorkflowError("Recover the actual owner's exact vehicle-crushing choice")
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == value.destroyed_event,
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(audit["payload_json"]) if audit else {}
        if (
            audit is None
            or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
            or audit["actor_id"] != action["actor_id"]
            or payload.get("action_id") != action["id"]
        ):
            raise WorkflowError("Preserve the canonical source-owned destruction event")
    return value


def vehicle_options(
    game: GameService,
    c: Connection,
    state: GameState,
    cast: SceneCast,
    actor: ActorRef | None = None,
) -> list[dict[str, Any]]:
    cell = (
        resolve(
            state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        ).cell
        if actor
        else None
    )
    result = []
    for value in rules.vehicles(state):
        if (
            value.scene != cast.id
            or value.destroyed_event
            or cell is not None
            and value.cell != cell
        ):
            continue
        prove(game, c, state, value.id)
        result.append(dict(id=value.id, label=value.name, cell=list(value.cell)))
    return result


def destroy_vehicle(
    game: GameService,
    c: Connection,
    state: GameState,
    vehicle_id: str,
    actor: ActorRef,
    action: str,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.engine import m3_wyvern as wyvern
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_enforcement_initiative import _cast
    from girlframe.services.m3_wyvern import require_rule

    require_rule(game, c, state, actor, wyvern.CRUSH)
    actual = game.action(c, action)
    _, _ = _roll_source(game, c, actual)
    value = prove(game, c, state, vehicle_id)
    cast = _cast(game, c, state, int(actual["channel_id"]))
    body = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    if (
        actual["data"]["play"] != "engage"
        or actual["actor_id"] != actor.entity
        or not body.piloting
        or frame_position(state, actor, wyvern.frame(state, actor)) != value.cell
        or vehicle_id not in {x["id"] for x in vehicle_options(game, c, state, cast, actor)}
    ):
        raise WorkflowError(
            "Crush only a genuinely present regular vehicle through the actual Engage source"
        )
    changed = GameState.model_validate_json(state.model_dump_json())
    rules.put(changed, value.model_copy(update=dict(destroyed_event=event, source_action=action)))
    return changed, ()


class VehicleService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "world", director_response=True)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            if state.world is None or viewer.user_id not in scene["participants"]:
                raise WorkflowError("Use the actual mapped source scene")
            return dict(
                revision=state.revision,
                channel=channel,
                minimum=state.world.board.minimum,
                maximum=state.world.board.maximum,
                can_assess=state.handler == viewer.user_id,
                vehicles=[
                    dict(
                        id=x.id,
                        name=x.name,
                        occupancy=x.occupancy,
                        destroyed=bool(x.destroyed_event),
                    )
                    for x in rules.vehicles(state)
                    if x.scene == scene["id"]
                ],
            )

    def assess(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        name: str,
        description: str,
        cell: tuple[int, int],
        occupancy: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_physical import PhysicalService

            Access(self.store).authorize(c, viewer, "world", director_response=True)
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)
            PhysicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            if (
                state.handler != viewer.user_id
                or state.revision != revision
                or state.world is None
                or viewer.user_id not in scene["participants"]
                or not state.world.board.contains(cell)
                or not name.strip()
                or len(name) > 120
                or not description.strip()
                or len(description) > 1200
                or occupancy not in ("empty", "occupied", "unknown")
            ):
                raise WorkflowError(
                    "Record actual regular-vehicle facts through the original Handler"
                )
            event, identity = str(uuid4()), "vehicle:" + str(uuid4())
            value = rules.Vehicle(
                id=identity,
                name=name.strip(),
                description=description.strip(),
                cell=cell,
                scene=scene["id"],
                assessed_by=viewer.user_id,
                event=event,
                occupancy=cast(Literal["empty", "occupied", "unknown"], occupancy),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.regular_vehicle_assessed",
                state,
                event_id=event,
                vehicle_id=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.regular_vehicle_assessed",
            dict(
                revision=revision,
                channel=channel,
                name=name,
                description=description,
                cell=list(cell),
                occupancy=cast(Literal["empty", "occupied", "unknown"], occupancy),
            ),
            operation,
            auto_audit=False,
        )
