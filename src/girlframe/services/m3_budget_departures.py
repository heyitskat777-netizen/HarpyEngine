"""Original Handler applies the authenticated NPC Bond departure source once."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_departures as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DepartureService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[dict[str, Any], GameState, rules.Record | None]:
        Access(self.store).authorize(c, viewer, "strain")
        Access(self.store).authorize(c, viewer, "world")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        handler = active_handler(original)
        if (
            handler is None
            or row["owner_id"] != handler.entity
            or viewer.user_id != int(handler.entity)
        ):
            raise WorkflowError("Only the original Handler owns this private NPC Bond consequence")
        state = load_state(c, self.store.campaign_id)
        value = next((x for x in rules.records(state) if x.id == identity), None)
        if value is not None:
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == value.event,
                )
            )
            proof = GameState.model_validate_json(raw) if raw else None
            record = (
                next((x for x in rules.records(proof) if x.id == identity), None) if proof else None
            )
            event = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == value.event,
                    )
                )
                .mappings()
                .first()
            )
            first_event = c.scalar(
                sa.select(t.m3["m3_required_work"].c.event_id)
                .where(
                    t.m3["m3_required_work"].c.campaign_id == self.store.campaign_id,
                    t.m3["m3_required_work"].c.id == identity,
                )
                .order_by(t.m3["m3_required_work"].c.revision)
                .limit(1)
            )
            if (
                record != value
                or value.handler != handler
                or value.source_event != first_event
                or event is None
                or event["kind"] != "m3.budget_bonds_departed"
                or event["actor_id"] != handler.entity
            ):
                raise WorkflowError("Recover the actual immutable NPC departure source")
        return row, state, value

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, value = self._source(c, viewer, identity)
            return dict(
                id=identity,
                revision=state.revision,
                work_revision=row["revision"],
                phase="complete" if value else "select",
                record=value.model_dump(mode="json") if value else None,
                candidates=[
                    dict(id=x.id, label=x.name, jobs=x.jobs, employment=x.employment)
                    for x in rules.eligible(state)
                ],
            )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        work_revision: int,
        selected: tuple[rules.Departure, ...],
        account: str,
    ) -> dict[str, Any]:
        selected = tuple(rules.Departure.model_validate_json(x.model_dump_json()) for x in selected)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, value = self._source(c, viewer, identity)
            original = active_handler(state)
            if (
                value is not None
                or row["state"] != "pending"
                or state.revision != expected
                or row["revision"] != work_revision
                or original is None
                or original.entity != str(viewer.user_id)
            ):
                raise WorkflowError("Reopen the original pending NPC departure request")
            _, source = _selection(c, self.game, identity, rule=rules.RULE)
            source_handler = active_handler(source)
            if source_handler is None or not same_handler_body(state, source_handler):
                raise WorkflowError("Recover the original actual source Handler body")
            from girlframe.services.m3_battle import synchronize_casts
            from girlframe.services.m3_handler_plays import _ordinary_scene_idle

            _ordinary_scene_idle(c, self.game)
            event = str(uuid4())
            changed = rules.apply(state, identity, row["event_id"], event, selected, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_bonds_departed",
                changed,
                event_id=event,
                work_id=identity,
                affected_count=len(selected),
            )
            if any(x.outcome == "die" for x in selected):
                synchronize_casts(self.game, c, event)
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, state="resolved")

        def authorize(c: Connection) -> None:
            self._source(c, viewer, identity)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_bonds_departure",
                dict(
                    id=identity,
                    expected=expected,
                    work_revision=work_revision,
                    selected=[x.model_dump(mode="json") for x in selected],
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
