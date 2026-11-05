"""Source-proved civic restoration; no repair, teleport, funds or automatic dialogue."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_anarchy as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class AnarchyService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Anarchy:
        value = rules.get(state, identity)
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = rules.get(GameState.model_validate_json(raw), identity) if raw else None
        if (
            event is None
            or original is None
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != value.handler.entity
            or json.loads(event["payload_json"]).get("rule_id") != "strain.budget.high.5.1"
            or json.loads(event["payload_json"]).get("work_id") != identity
            or any(
                getattr(original, k) != getattr(value, k)
                for k in ("id", "source_event", "handler", "city", "account")
            )
        ):
            raise WorkflowError("Recover the original selected city's anarchy source")
        return value

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id)
            for x in rules.cases(state)
            if x.restored_event is None
            and int(x.handler.entity) == viewer.user_id
            and same_handler_body(state, x.handler)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "world")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if viewer.user_id != int(value.handler.entity) or not same_handler_body(
                state, value.handler
            ):
                raise WorkflowError("Only the original Handler reviews actual civic restoration")
            city = (
                next((x for x in state.world.locations if x.id == value.city), None)
                if state.world
                else None
            )
            return dict(
                id=identity,
                revision=state.revision,
                city=city.name if city else "Original city",
                restored=bool(value.restored_event),
            )

    def restore(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        method: str,
        result: str,
    ) -> dict[str, Any]:
        if any(not x.strip() or len(x) > 1200 for x in (method, result)):
            raise WorkflowError("Describe the actual method and established restoration of order")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "world")
            value = self._proof(c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id != int(value.handler.entity):
                raise WorkflowError("Only the original Handler records this actual civic result")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if state.revision != expected:
                raise WorkflowError("STALE_ANARCHY: reopen the actual city and source")
            event = str(uuid4())
            changed = rules.restore(state, value, method, result, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.city_order_restored",
                changed,
                event_id=event,
                source_work=identity,
                city=value.city,
            )
            return dict(id=identity, restored=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.city_order_restored",
                dict(id=identity, expected=expected, method=method, result=result),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
