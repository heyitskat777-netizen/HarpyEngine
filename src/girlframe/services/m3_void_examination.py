"""Low Void 6.2 records an examination for every original Girl."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_janus_storage import effective_for_owner
from girlframe.engine.m3_observation import order
from girlframe.engine.m3_off_duty import Period, clone
from girlframe.services.m2_state import load_state
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

TASK = "strain_void_exam"


def prove_discovery(c: Connection, campaign: str, punishment: dict[str, Any]) -> None:
    table = t.m3["m3_required_work"]
    exam = json.loads(punishment["body_json"])["examination"]
    source = c.execute(
        sa.select(table.c.body_json, table.c.event_id)
        .join(
            t.events,
            (table.c.campaign_id == t.events.c.campaign_id) & (table.c.event_id == t.events.c.id),
        )
        .where(
            table.c.campaign_id == campaign,
            table.c.id == exam,
            table.c.off_duty_id == punishment["off_duty_id"],
            table.c.kind == TASK,
            table.c.state == "resolved",
            t.events.c.kind == "m3.strain_void_exam_completed",
        )
    ).first()
    if (
        punishment["id"] != exam + ":punishment"
        or source is None
        or json.loads(source.body_json).get("hidden") is not True
        or not json.loads(source.body_json).get("found")
    ):
        raise WorkflowError("Recover the original concealed Void discovery before Punishment")


def schedule(
    c: Connection, periods: OffDutyService, parent: dict[str, Any], state: GameState, event: str
) -> None:
    period = periods._get(c, parent["off_duty_id"])
    for uid in period.pilots:
        character = period.character_ids.get(str(uid))
        sheet = state.sheets.get(str(uid))
        if sheet is None or not character or sheet.character_id != character:
            raise WorkflowError("Recover the actual original examination roster")
        related(
            c,
            periods.store,
            parent,
            f"{parent['id']}:exam:{uid}",
            uid,
            uid,
            TASK,
            dict(character=character, source_work=parent["id"], source_event=event),
            event,
        )


class ExaminationService:
    def __init__(self, periods: OffDutyService):
        self.periods, self.store, self.game = periods, periods.store, periods.game

    def _owned(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], Period, GameState]:
        self.game.authorize(c, viewer, game=False)
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != TASK or row["owner_id"] != str(viewer.user_id):
            raise WorkflowError("Only the original patient may open this examination")
        state = load_state(c, self.store.campaign_id)
        period = self.periods._get(c, row["off_duty_id"])
        sheet = state.sheets.get(str(viewer.user_id))
        body = json.loads(row["body_json"])
        if sheet is None or sheet.character_id != body["character"]:
            raise WorkflowError("Recover the actual original examination patient")
        return dict(row), period, state

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, _, state = self._owned(c, viewer, identity)
            return {
                "revision": row["revision"],
                "state": row["state"],
                "game_revision": state.revision,
                "assets": [
                    (asset.id, asset.name)
                    for asset in effective_for_owner(state, viewer.user_id)
                    if asset.void and row["state"] == "pending"
                ],
            }

    def finish(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        found: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.periods.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            self._owned(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row, period, state = self._owned(c, viewer, identity)
            uid = viewer.user_id
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or state.revision != game_revision
                or period.phase != "preparing"
                or period.handler != state.handler
            ):
                raise WorkflowError("STALE_EXAMINATION: reopen the original examination")
            if not 0 < len(account.strip()) <= 1200:
                raise WorkflowError("Record what the actual examination found")
            void = {asset.id: asset for asset in effective_for_owner(state, uid) if asset.void}
            if len(set(found)) != len(found) or not set(found) <= void.keys():
                raise WorkflowError("Choose only actual original Void Assets found in the exam")
            hidden = any(void[asset].concealed for asset in found)
            event_id = str(uuid4())
            updated = period
            if found:
                progress = period.progress.get(str(uid))
                if progress and progress.observation:
                    # Keep the already established Observation and its original cause.
                    if hidden:
                        updated = clone(period)
                        observation = updated.progress[str(uid)].observation
                        assert observation is not None
                        observation.suspects_hiding = True
                        observation.hiding_review_event = event_id
                        updated.revision += 1
                else:
                    updated, state = order(
                        period,
                        period.revision,
                        period.handler,
                        uid,
                        state,
                        hidden,
                        account,
                        event_id,
                    )
            body = json.loads(row["body_json"])
            punishment = identity + ":punishment"
            discipline: dict[str, Any] | None = None
            subject = uid
            if hidden:
                from girlframe.engine.m3_actor_bonds import current_ref
                from girlframe.engine.m3_intracadre_marriage import allocation_fields
                from girlframe.services.m3_intracadre_marriage import allocate_punishment

                original = current_ref(state, uid)
                allocation = allocate_punishment(
                    self.game,
                    c,
                    state,
                    original,
                    source_event=event_id,
                    source_id=punishment,
                    work_id=punishment,
                )
                recipient = allocation.subject if allocation else original
                subject = int(recipient.entity)
                discipline = dict(
                    reason="void_examination_discovery",
                    source_pdf=144,
                    character=recipient.incarnation,
                    due_stage="active",
                    examination=identity,
                    **allocation_fields(state, punishment),
                )
            event = self.game.event(
                c,
                uid,
                key,
                "m3.strain_void_exam_completed",
                state if found else None,
                event_id=event_id,
                work_id=identity,
                period_id=period.id,
            )
            if updated != period:
                self.periods._save(c, updated, event)
            if discipline is not None:
                related(
                    c,
                    self.store,
                    row,
                    punishment,
                    period.handler,
                    subject,
                    "punishment",
                    discipline,
                    event,
                )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        name: value
                        for name, value in row.items()
                        if name not in {"revision", "event_id", "state", "body_json"}
                    },
                    revision=revision + 1,
                    event_id=event,
                    state="resolved",
                    body_json=json.dumps(body | dict(found=found, account=account, hidden=hidden)),
                )
            )
            return dict(id=identity, revision=revision + 1, state="resolved")

        return self.periods.missions._write(
            viewer,
            key,
            "m3.strain_void_exam_completed",
            dict(
                id=identity,
                revision=revision,
                game_revision=game_revision,
                found=found,
                account=account,
            ),
            operation,
            authorize,
        )
