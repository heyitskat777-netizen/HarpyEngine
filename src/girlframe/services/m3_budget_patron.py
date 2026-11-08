"""Actual patron controller reports witnessed evidence; no automatic secret reading."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_budget_patron import Interest, interests
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class PatronService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> Interest:
        record = next((x for x in interests(state) if x.id == identity), None)
        raw = (
            c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == record.source_event,
                )
            )
            if record
            else None
        )
        original = GameState.model_validate_json(raw) if raw else None
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == record.source_event,
                )
            )
            .mappings()
            .first()
            if record
            else None
        )
        if (
            record is None
            or original is None
            or event is None
            or record not in interests(original)
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != record.handler.entity
            or json.loads(event["payload_json"]).get("work_id") != record.id
            or json.loads(event["payload_json"]).get("rule_id") != "strain.budget.low.1.2"
        ):
            raise WorkflowError("Recover the actual original patron-interest source")
        return record

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        rows = []
        for case in interests(state):
            if not same_handler_body(state, case.handler):
                continue
            npc = (
                next((x for x in state.world.npcs if x.id == case.patron.entity and x.alive), None)
                if state.world
                else None
            )
            girl = state.sheets.get(case.girl.entity)
            if (
                npc
                and npc.controller == viewer.user_id
                and girl
                and girl.character_id == case.girl.incarnation
            ):
                rows.append(dict(id=case.id, patron=npc.name, girl=girl.callsign))
        return rows

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            record = self._proof(c, state, identity)
            row = next((x for x in self.available(c, viewer) if x["id"] == identity), None)
            if row is None:
                raise WorkflowError(
                    "Only this actual living patron's controller reports its visits"
                )
            return row | dict(revision=state.revision, handler=int(record.handler.entity))

    def visit(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        witnessed: bool,
        account: str,
        label: str = "",
    ) -> dict[str, Any]:
        if (
            not account.strip()
            or len(account) > 1200
            or (witnessed and not label.strip())
            or len(label) > 120
        ):
            raise WorkflowError("Report the actual visit and, if evidence was seen, author its Tag")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            record = self._proof(c, state, identity)
            if state.revision != expected or not any(
                x["id"] == identity for x in self.available(c, viewer)
            ):
                raise WorkflowError("STALE_PATRON: reopen the actual original patron and Girl")
            # The source controller explicitly attests evidence seen during a real visit.
            # Do not query private Punishment records or infer fictional knowledge from SQL.
            event, tag_id = str(uuid4()), None
            if witnessed:
                tag_id = str(uuid4())
                patron = resolve(state, record.patron, ())
                state.handler_tags.append(
                    TagState(
                        id=tag_id,
                        label=label.strip(),
                        giver=patron.controller,
                        giver_actor=record.patron,
                        observers=tuple(
                            dict.fromkeys((patron.controller, int(record.handler.entity)))
                        ),
                    )
                )
            state.facts.append(
                dict(
                    kind="budget_patron_visit",
                    interest=identity,
                    event=event,
                    account=account,
                    witnessed=str(witnessed),
                    tag=tag_id or "",
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_patron_visit",
                state,
                event_id=event,
                interest=identity,
                witnessed=witnessed,
                tag=tag_id,
            )
            return dict(id=identity, tag=tag_id, event=event)

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            self._proof(c, state, identity)
            if not any(x["id"] == identity for x in self.available(c, viewer)):
                raise WorkflowError("Only the actual patron's controller can report this visit")

        return self.store._write(
            viewer,
            key,
            "m3.budget_patron_visit",
            dict(id=identity, expected=expected, witnessed=witnessed, account=account, label=label),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
