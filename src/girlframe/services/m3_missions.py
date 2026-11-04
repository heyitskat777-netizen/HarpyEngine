"""Transactional mission authority with private immutable histories and mandatory work."""

import builtins
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_missions as rules
from girlframe.engine.rules_registry import Registry
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class MissionService:
    def __init__(self, store: OnboardingStore, registry: Registry | None = None):
        self.store = store
        self.access = Access(store, registry)
        self.game = GameService(store)

    def _authorize(self, c: Connection, viewer: GuildViewer, *, write: bool = True) -> None:
        if write:
            self.access.authorize(c, viewer, "missions")
            self.game.unpaused(c)
        else:
            self.game.authorize(c, viewer, game=False)

    def _handler(self, c: Connection, viewer: GuildViewer) -> int:
        HandlerService(self.store).authorize(c, viewer)
        state = load_state(c, self.store.campaign_id)
        if state.handler != viewer.user_id:
            raise WorkflowError("Canonical Handler replacement requires explicit resolution.")
        return viewer.user_id

    def _current_handler(self, c: Connection) -> int:
        value = HandlerService(self.store).current(c)[1].handler_id
        if value is None:
            raise WorkflowError("Appoint a campaign Handler first.")
        return value

    def _mission(self, c: Connection, identity: str) -> rules.Mission:
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("Unknown mission.") from None
        table = t.m3["m3_missions"]
        body = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id, table.c.id == identity
            )
        )
        if body is None:
            raise WorkflowError("Unknown mission.")
        return rules.Mission.model_validate_json(body)

    def _view(self, c: Connection, viewer: GuildViewer, mission: rules.Mission) -> None:
        self._authorize(c, viewer, write=False)
        if viewer.user_id not in mission.offered_to and viewer.user_id != self._current_handler(c):
            raise WorkflowError(
                "This mission is visible only to its invited players and current Handler."
            )

    def _save(self, c: Connection, mission: rules.Mission, event: str) -> None:
        table = t.m3["m3_missions"]
        where = sa.and_(table.c.campaign_id == self.store.campaign_id, table.c.id == mission.id)
        values = {
            "handler_id": str(mission.handler),
            "revision": mission.revision,
            "phase": mission.phase,
            "body_json": mission.model_dump_json(),
        }
        if c.scalar(sa.select(table.c.revision).where(where)) is None:
            c.execute(
                table.insert().values(campaign_id=self.store.campaign_id, id=mission.id, **values)
            )
        else:
            c.execute(table.update().where(where).values(**values))
        c.execute(
            t.m3["m3_mission_history"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=mission.id,
                revision=mission.revision,
                body_json=mission.model_dump_json(),
                event_id=event,
            )
        )

    def _work(
        self,
        c: Connection,
        mission: rules.Mission,
        identity: str,
        owner: int,
        subject: int,
        kind: str,
        body: dict[str, Any],
        event: str,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=identity,
                revision=1,
                mission_id=mission.id,
                owner_id=str(owner),
                subject_id=str(subject),
                kind=kind,
                state="pending",
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
            )
        )

    def _pending(self, c: Connection, identity: str) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        rows = c.execute(
            sa.select(table)
            .where(table.c.campaign_id == self.store.campaign_id, table.c.mission_id == identity)
            .order_by(table.c.revision)
        ).mappings()
        latest = {x["id"]: dict(x) for x in rows}
        return [x for x in latest.values() if x["state"] != "resolved"]

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
        authorize: Callable[[Connection], None] | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._authorize(c, viewer)
            if authorize:
                authorize(c)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=access
            )
        except ValidationError:
            raise WorkflowError("Mission validation failed; reopen the current mission.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def offer(
        self, viewer: GuildViewer, key: str, objective: str, players: tuple[int, ...]
    ) -> dict[str, Any]:
        if not objective.strip() or len(objective) > 1200:
            raise WorkflowError("Describe the mission objective in 1–1200 characters.")

        def operation(c: Connection) -> dict[str, Any]:
            self._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if not players or len(players) > 25 or len(set(players)) != len(players):
                raise WorkflowError("Select one to 25 distinct active Pilots.")
            setup = HandlerService(self.store)
            if any(
                str(uid) not in state.sheets or uid == viewer.user_id or not setup._member(c, uid)
                for uid in players
            ):
                raise WorkflowError(
                    "Offer missions only to active campaign Pilots with canonical sheets."
                )
            mission = rules.Mission(
                id=str(uuid4()),
                handler=viewer.user_id,
                objective=objective.strip(),
                offered_to=players,
            )
            event = self.game.event(
                c, viewer.user_id, key, "m3.mission_offered", mission_id=mission.id, revision=1
            )
            self._save(c, mission, event)
            return {"id": mission.id, "revision": mission.revision, "phase": mission.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_offered",
            {"objective": objective, "players": list(players)},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, write=False)
            mission = self._mission(c, identity)
            self._view(c, viewer, mission)
            # Work details remain private to their owner/subject; other invitees see a count only.
            pending = self._pending(c, identity)
            return {
                "mission": mission.model_dump(mode="json"),
                "pending_count": len(pending),
                "work": [
                    {
                        "id": x["id"],
                        "kind": x["kind"],
                        "subject": int(x["subject_id"]),
                        "revision": x["revision"],
                    }
                    for x in pending
                    if str(viewer.user_id) in (x["owner_id"], x["subject_id"])
                ],
            }

    def list(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, write=False)
            current_handler = HandlerService(self.store).current(c)[1].handler_id
            table = t.m3["m3_missions"]
            result = []
            for body in c.scalars(
                sa.select(table.c.body_json)
                .where(table.c.campaign_id == self.store.campaign_id)
                .order_by(table.c.id)
            ):
                mission = rules.Mission.model_validate_json(body)
                if viewer.user_id in mission.offered_to or viewer.user_id == current_handler:
                    result.append(
                        {
                            "id": mission.id,
                            "revision": mission.revision,
                            "phase": mission.phase,
                            "objective": mission.objective,
                            "needs_response": mission.phase == "offered"
                            and viewer.user_id in mission.offered_to
                            and str(viewer.user_id) not in mission.responses,
                        }
                    )
            return result

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, response: rules.Response
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._view(c, viewer, self._mission(c, identity))

        def operation(c: Connection) -> dict[str, Any]:
            mission = self._mission(c, identity)
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) not in state.sheets:
                raise WorkflowError("A current canonical Pilot is required to respond.")
            updated = rules.respond(mission, viewer.user_id, expected, response)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_response",
                mission_id=identity,
                revision=updated.revision,
            )
            self._save(c, updated, event)
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_response",
            {"id": identity, "expected": expected, "response": response},
            operation,
            authorize,
        )

    def start(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            mission = self._mission(c, identity)
            self._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            setup = HandlerService(self.store)
            active = frozenset(int(uid) for uid in state.sheets if setup._member(c, int(uid)))
            updated = rules.dispatch(
                mission, viewer.user_id, self._current_handler(c), expected, active
            )
            # A Pilot cannot be dispatched into two active missions at once.
            table = t.m3["m3_missions"]
            for other_body in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id != identity,
                    table.c.phase.in_(("active", "ending", "awaiting_consequences")),
                )
            ):
                other = rules.Mission.model_validate_json(other_body)
                if set(updated.participants) & set(other.participants):
                    raise WorkflowError("A participant already has an unfinished mission.")
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_started",
                mission_id=identity,
                revision=updated.revision,
            )
            self._save(c, updated, event)
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_started",
            {"id": identity, "expected": expected},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def end(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, success: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            mission = self._mission(c, identity)
            self._handler(c, viewer)
            rules.handler(mission, viewer.user_id, self._current_handler(c))
            rules.revision(mission, expected)
            if mission.phase != "active":
                raise WorkflowError("Only an active mission can be ended.")
            if type(success) is not bool:
                raise WorkflowError("Record an explicit mission success or failure.")
            state = load_state(c, self.store.campaign_id)
            # These reactions must occur before taking the final reward/Status snapshot.
            reactions = []
            for uid, sheet in state.sheets.items():
                if sheet.girl == "PRINCESS":
                    reactions.append((int(uid), "princess_mission_end", 32))
                if sheet.frame == "DOCTORDOCTOR MK. II" and not success:
                    reactions.append((int(uid), "doctor_obsolescence", 71))
            if reactions:
                updated = rules.changed(mission, phase="ending", success=success)
                event = self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.mission_end_reactions_required",
                    mission_id=identity,
                    revision=updated.revision,
                )
                self._save(c, updated, event)
                for subject_uid, kind, pdf in reactions:
                    self._work(
                        c,
                        updated,
                        identity + ":" + kind + ":" + str(subject_uid),
                        viewer.user_id,
                        subject_uid,
                        kind,
                        {"source_pdf": pdf},
                        event,
                    )
                return {
                    "id": identity,
                    "revision": updated.revision,
                    "phase": updated.phase,
                    "rewards_committed": False,
                }
            return self._finish_rewards(c, viewer, key, mission, success)

        return self._write(
            viewer,
            key,
            "m3.mission_ended",
            {"id": identity, "expected": expected, "success": success},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def _finish_rewards(
        self, c: Connection, viewer: GuildViewer, key: str, mission: rules.Mission, success: bool
    ) -> dict[str, Any]:
        state = load_state(c, self.store.campaign_id)
        rulings = self.store.policy.owner_m3_rulings
        if rulings is None:
            raise WorkflowError("M3 campaign rulings are missing.")
        plan = rules.end(
            mission,
            viewer.user_id,
            self._current_handler(c),
            mission.revision,
            success=success,
            status_order=state.order,
            ace_policy=rulings.ace_bonus,
        )
        changed = set()
        for grant in plan.grants:
            sheet = state.sheets.get(str(grant.owner))
            if sheet is None:
                raise WorkflowError(
                    "A reward recipient has no current sheet; resolve the roster first."
                )
            sheet.permissions += grant.amount
            changed.add(str(grant.owner))
        for uid in changed:
            state.sheets[uid].revision += 1
        event = self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.mission_rewards_committed",
            state,
            mission_id=mission.id,
            revision=plan.mission.revision,
        )
        self._save(c, plan.mission, event)
        for work in plan.consequences:
            self._work(
                c,
                plan.mission,
                work.id,
                work.decision_owner,
                work.owner,
                "punishment",
                work.model_dump(mode="json"),
                event,
            )
        return {
            "id": mission.id,
            "revision": plan.mission.revision,
            "phase": plan.mission.phase,
            "rewards_committed": True,
        }

    def complete(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._handler(c, viewer)
            mission = self._mission(c, identity)
            rules.handler(mission, viewer.user_id, self._current_handler(c))
            rules.revision(mission, expected)
            if self._pending(c, identity):
                raise WorkflowError(
                    "Required mission work is still pending; it cannot be waived or expired."
                )
            if mission.phase == "ending":
                if mission.success is None:
                    raise WorkflowError("The recorded mission outcome is missing.")
                return self._finish_rewards(c, viewer, key, mission, mission.success)
            updated = rules.complete(
                mission,
                expected,
                resolved_consequences=frozenset(mission.consequence_ids),
                all_other_mandatory_work_resolved=True,
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_completed",
                mission_id=identity,
                revision=updated.revision,
            )
            self._save(c, updated, event)
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_completed",
            {"id": identity, "expected": expected},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def rebuild(self) -> int:
        with self.store.transaction() as c:
            history = t.m3["m3_mission_history"]
            table = t.m3["m3_missions"]
            rows = c.scalars(
                sa.select(history.c.body_json)
                .where(history.c.campaign_id == self.store.campaign_id)
                .order_by(history.c.revision)
            )
            latest = {m.id: m for m in (rules.Mission.model_validate_json(body) for body in rows)}
            for mission in latest.values():
                values = {
                    "handler_id": str(mission.handler),
                    "revision": mission.revision,
                    "phase": mission.phase,
                    "body_json": mission.model_dump_json(),
                }
                where = sa.and_(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == mission.id
                )
                if c.scalar(sa.select(table.c.revision).where(where)) is None:
                    c.execute(
                        table.insert().values(
                            campaign_id=self.store.campaign_id, id=mission.id, **values
                        )
                    )
                else:
                    c.execute(table.update().where(where).values(**values))
            self.store._audit(
                c,
                "system:local_operator",
                str(uuid4()),
                "m3.mission_projections_rebuilt",
                {"missions": len(latest)},
            )
            return len(latest)

    def roster(self, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            self._handler(c, viewer)
            setup = HandlerService(self.store)
            state = load_state(c, self.store.campaign_id)
            return tuple(
                (uid, sheet.callsign)
                for uid, sheet in state.sheets.items()
                if setup._member(c, int(uid))
            )

    def owned_work(self, viewer: GuildViewer) -> builtins.list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, write=False)
            table = t.m3["m3_required_work"]
            rows = c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    sa.or_(
                        table.c.owner_id == str(viewer.user_id),
                        table.c.subject_id == str(viewer.user_id),
                    ),
                )
                .order_by(table.c.revision)
            ).mappings()
            latest = {row["id"]: dict(row) for row in rows}
            return [
                {
                    k: v
                    for k, v in row.items()
                    if k
                    in ("id", "revision", "mission_id", "owner_id", "subject_id", "kind", "state")
                }
                for row in latest.values()
                if row["state"] != "resolved"
            ]
