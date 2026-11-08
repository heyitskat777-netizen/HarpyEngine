"""Private regulation review and Handler-authored breaches with real discipline work."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_regulations as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_missions import Mission
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_regulation_state import Regulation
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class RegulationService:
    def __init__(self, missions: MissionService):
        self.missions, self.game, self.store = missions, missions.game, missions.store

    def _ref(self, c: Connection, state: GameState, owner: int) -> ActorRef | None:
        try:
            return rules.actor_ref(
                state,
                owner,
                {owner: self.game.character_binding(c, state, owner, require_current_profile=False)}
                if owner != state.handler
                else None,
            )
        except (ValueError, WorkflowError):
            return None

    def _visible(
        self, c: Connection, state: GameState, viewer: GuildViewer, rule: Regulation
    ) -> bool:
        ref = self._ref(c, state, viewer.user_id)
        return bool(
            ref is not None
            and (
                ref in (rule.inflictor, rule.knowing_handler)
                or (rule.disclosed and ref == rule.subject)
            )
        )

    def _due(self, c: Connection) -> list[tuple[str, str]]:
        result = [("next_off_duty", "Next Off-Duty")]
        periods, missions = t.m3["m3_off_duty"], t.m3["m3_missions"]
        for body in c.scalars(
            sa.select(periods.c.body_json).where(
                periods.c.campaign_id == self.store.campaign_id,
                periods.c.phase != "complete",
            )
        ):
            period = Period.model_validate_json(body)
            result.append(("period:" + period.id, "Current Off-Duty"))
        for body in c.scalars(
            sa.select(missions.c.body_json).where(
                missions.c.campaign_id == self.store.campaign_id,
                missions.c.phase.in_(("active", "ending", "awaiting_consequences")),
            )
        ):
            mission = Mission.model_validate_json(body)
            result.append(("mission:" + mission.id, "Current mission " + mission.id[:8]))
        return result

    def list(self, viewer: GuildViewer) -> list[dict[str, str]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return [
                {"id": x.id, "label": "Behavioural rule " + x.id[:8]}
                for x in state.regulations
                if self._visible(c, state, viewer, x)
            ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            rule = next((x for x in state.regulations if x.id == identity), None)
            if rule is None or not self._visible(c, state, viewer, rule):
                raise WorkflowError("This regulation is unavailable to your actual role.")
            return {
                "id": rule.id,
                "rule": rule.rule,
                "disclosed": rule.disclosed,
                "game_revision": state.revision,
                "breach_count": len(rule.breaches),
                "may_record": self._ref(c, state, viewer.user_id) == rule.knowing_handler,
                "due_options": self._due(c) if viewer.user_id == state.handler else [],
            }

    def record(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, evidence: str, due: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "discipline")
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            rule = next((x for x in state.regulations if x.id == identity), None)
            locks = t.m2["m2_locks"]
            if (
                state.revision != expected
                or rule is None
                or not self._visible(c, state, viewer, rule)
            ):
                raise WorkflowError("STALE_REGULATION: reopen an available current rule.")
            if self.game.pending_actions(c) or c.scalar(
                sa.select(locks.c.channel_id)
                .where(
                    locks.c.campaign_id == self.store.campaign_id,
                    locks.c.state != "released",
                )
                .limit(1)
            ):
                raise WorkflowError(
                    "Finish the pending Play and restore chat before recording a breach."
                )
            if due not in dict(self._due(c)):
                raise WorkflowError(
                    "Choose the actual current discipline context or next Off-Duty."
                )
            subject = int(rule.subject.entity)
            event_id, obligation_id = str(uuid4()), str(uuid4())
            bindings = {
                subject: self.game.character_binding(
                    c, state, subject, require_current_profile=False
                )
            }
            updated = rules.breach(
                state, identity, viewer.user_id, evidence, event_id, obligation_id, bindings
            )
            debt = updated.obligations[-1]
            if due == "next_off_duty":
                period = t.m3["m3_off_duty"]
                debt.details["after_period"] = (
                    c.scalar(
                        sa.select(period.c.id).where(
                            period.c.campaign_id == self.store.campaign_id,
                            period.c.phase != "complete",
                        )
                    )
                    or ""
                )
            elif due.startswith("mission:"):
                debt.details["mission"] = due.removeprefix("mission:")
            # Save the actual source event before a required-work foreign key.
            # Existing Off-Duty synchronization binds current-period work atomically.
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.regulation_breach_recorded",
                updated,
                event_id=event_id,
                regulation=identity,
                due=due.split(":")[0],
            )
            if due.startswith("mission:"):
                mission = self.missions._mission(c, due.removeprefix("mission:"))
                if mission.handler != updated.handler:
                    raise WorkflowError("Recover the changed mission Handler first.")
                from girlframe.engine import m3_intracadre_marriage as marriage

                allocation = next(
                    (
                        x
                        for x in marriage.records(updated, marriage.Allocation)
                        if x.source_id == obligation_id
                    ),
                    None,
                )
                recipient = allocation.subject if allocation else rule.subject
                self.missions._work(
                    c,
                    mission,
                    allocation.work_id if allocation else str(uuid4()),
                    viewer.user_id,
                    int(recipient.entity),
                    "punishment",
                    {
                        "reason": "strict_regulations",
                        "source_pdf": 17,
                        "obligation_id": obligation_id,
                        "source_action": event,
                        "regulation": identity,
                        "character": recipient.incarnation,
                        **marriage.allocation_fields(updated, obligation_id),
                    },
                    event,
                )
            return {"id": identity, "state": "breach_recorded", "cause": obligation_id}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.regulation_breach_recorded",
                {
                    "id": identity,
                    "expected": expected,
                    "evidence": evidence,
                    "due": due,
                },
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
