"""Private durable Off-Duty preparation; unsupported Strain work cannot be waived.

This foundation deliberately exposes no generic work resolver or activation API.
The Strain subsystem must resolve its typed start consequences before ordinary
roll/recovery reducers can be connected to a player command.
"""

import json
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_off_duty import Period, doctor_credit
from girlframe.engine.m3_policy import RULESET
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class OffDutyService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    def _get(self, c: Connection, identity: str) -> Period:
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("Unknown Off-Duty period.") from None
        table = t.m3["m3_off_duty"]
        body = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id, table.c.id == identity
            )
        )
        if body is None:
            raise WorkflowError("Unknown Off-Duty period.")
        return Period.model_validate_json(body)

    def _view(self, c: Connection, viewer: GuildViewer, period: Period) -> None:
        self.game.authorize(c, viewer, game=False)
        current_handler = HandlerService(self.store).current(c)[1].handler_id
        if viewer.user_id not in period.pilots and viewer.user_id != current_handler:
            raise WorkflowError("This period is private to its Pilots and current Handler.")

    def _save(self, c: Connection, period: Period, event: str) -> None:
        table = t.m3["m3_off_duty"]
        where = sa.and_(table.c.campaign_id == self.store.campaign_id, table.c.id == period.id)
        values = {
            "handler_id": str(period.handler),
            "revision": period.revision,
            "phase": period.phase,
            "body_json": period.model_dump_json(),
        }
        if c.scalar(sa.select(table.c.revision).where(where)) is None:
            c.execute(
                table.insert().values(campaign_id=self.store.campaign_id, id=period.id, **values)
            )
        else:
            c.execute(table.update().where(where).values(**values))
        c.execute(
            t.m3["m3_off_duty_history"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=period.id,
                revision=period.revision,
                body_json=period.model_dump_json(),
                event_id=event,
            )
        )

    def _work(
        self,
        c: Connection,
        period: Period,
        owner: int,
        kind: str,
        event: str,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=period.id + ":" + kind + ":" + str(owner),
                revision=1,
                mission_id=None,
                off_duty_id=period.id,
                owner_id=str(owner),
                subject_id=str(owner),
                kind=kind,
                state="pending",
                body_json=json.dumps(
                    {
                        "source_pdf": 71
                        if kind == "doctor_credit"
                        else 142
                        if kind == "off_duty_strain_start"
                        else 118
                    }
                ),
                event_id=event,
            )
        )

    def _pending(self, c: Connection, identity: str) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        rows = c.execute(
            sa.select(table)
            .where(table.c.campaign_id == self.store.campaign_id, table.c.off_duty_id == identity)
            .order_by(table.c.revision)
        ).mappings()
        latest = {row["id"]: dict(row) for row in rows}
        return [row for row in latest.values() if row["state"] != "resolved"]

    def begin(self, viewer: GuildViewer, key: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.missions._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if self.game.pending_actions(c):
                raise WorkflowError("Finish the pending scene Play before starting Off-Duty.")
            existing = t.m3["m3_off_duty"]
            missions = t.m3["m3_missions"]
            if c.scalar(
                sa.select(existing.c.id).where(
                    existing.c.campaign_id == self.store.campaign_id, existing.c.phase != "complete"
                )
            ):
                raise WorkflowError("Resume the existing Off-Duty period.")
            if c.scalar(
                sa.select(missions.c.id).where(
                    missions.c.campaign_id == self.store.campaign_id,
                    missions.c.phase.not_in(("complete", "cancelled")),
                )
            ):
                raise WorkflowError("Finish all mission work before starting Off-Duty.")
            setup = HandlerService(self.store)
            if not state.order or any(
                not setup._member(c, uid)
                or str(uid) not in state.sheets
                or state.sheets[str(uid)].frame_scrapped
                or self.game.immediate_work(c, uid)
                or state.sheets[str(uid)].sedation_locked
                for uid in state.order
            ):
                raise WorkflowError(
                    "Resolve the current Pilot roster, immediate work and old locks."
                )
            period = Period(id=str(uuid4()), handler=viewer.user_id, pilots=state.order)
            event = self.game.event(
                c, viewer.user_id, key, "m3.off_duty_preparing", period_id=period.id
            )
            self._save(c, period, event)
            # This is an actual dependency, not an operator acknowledgement checkbox.
            self._work(c, period, viewer.user_id, "off_duty_strain_start", event)
            self._work(c, period, viewer.user_id, "off_duty_handler_scene", event)
            self._work(c, period, viewer.user_id, "off_duty_status_review", event)
            for uid in state.order:
                if state.sheets[str(uid)].frame == "DOCTORDOCTOR MK. II":
                    self._work(c, period, uid, "doctor_credit", event)
            return {"id": period.id, "revision": 1, "phase": "preparing"}

        return self.missions._write(
            viewer,
            key,
            "m3.off_duty_preparing",
            {},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            period = self._get(c, identity)
            self._view(c, viewer, period)
            work = self._pending(c, identity)
            # Other Pilots cannot see an owner's private factual account or sheet choices.
            return {
                "id": period.id,
                "revision": period.revision,
                "phase": period.phase,
                "pending_count": len(work),
                "work": [
                    {k: row[k] for k in ("id", "kind", "revision", "state")}
                    for row in work
                    if row["owner_id"] == str(viewer.user_id)
                ],
            }

    def credit(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        recipient: int | None,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "playbooks")
            self._view(c, viewer, self._get(c, identity))

        def operation(c: Connection) -> dict[str, Any]:
            period = self._get(c, identity)
            state = load_state(c, self.store.campaign_id)
            if state.revision != game_revision or self.game.pending_actions(c):
                raise WorkflowError("STALE_STATE: finish pending Plays and review current state.")
            if recipient is not None and not HandlerService(self.store)._member(c, recipient):
                raise WorkflowError("Credit requires another current canonical Pilot.")
            rows = [
                x
                for x in self._pending(c, identity)
                if x["kind"] == "doctor_credit" and x["owner_id"] == str(viewer.user_id)
            ]
            if len(rows) != 1:
                raise WorkflowError("Resume your own pending DoctorDoctor credit record.")
            updated_period, updated_state = doctor_credit(
                period, expected, viewer.user_id, state, recipient, account
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.off_duty_credit_recorded",
                updated_state,
                period_id=identity,
                recipient_id=recipient,
            )
            self._save(c, updated_period, event)
            row = rows[0]
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                    body_json=json.dumps(
                        {"recipient": recipient, "account": account.strip(), "source_pdf": 71},
                        sort_keys=True,
                    ),
                )
            )
            return {"id": identity, "revision": updated_period.revision, "state": "resolved"}

        return self.missions._write(
            viewer,
            key,
            "m3.off_duty_credit_recorded",
            {
                "id": identity,
                "expected": expected,
                "game_revision": game_revision,
                "recipient": recipient,
                "account": account,
            },
            operation,
            authorize,
        )

    def rebuild(self) -> int:
        with self.store.transaction() as c:
            history = t.m3["m3_off_duty_history"]
            latest = {
                period.id: period
                for period in (
                    Period.model_validate_json(body)
                    for body in c.scalars(
                        sa.select(history.c.body_json)
                        .where(history.c.campaign_id == self.store.campaign_id)
                        .order_by(history.c.revision)
                    )
                )
            }
            table = t.m3["m3_off_duty"]
            for period in latest.values():
                where = sa.and_(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == period.id
                )
                values = {
                    "handler_id": str(period.handler),
                    "revision": period.revision,
                    "phase": period.phase,
                    "body_json": period.model_dump_json(),
                }
                if c.scalar(sa.select(table.c.revision).where(where)) is None:
                    c.execute(
                        table.insert().values(
                            campaign_id=self.store.campaign_id, id=period.id, **values
                        )
                    )
                else:
                    c.execute(table.update().where(where).values(**values))
            self.store._audit(
                c,
                "system:local_operator",
                str(uuid4()),
                "m3.off_duty_projections_rebuilt",
                {"periods": len(latest)},
                ruleset_version=RULESET,
            )
            return len(latest)
