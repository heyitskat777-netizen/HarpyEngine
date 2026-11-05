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
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_careers import archive_for
from girlframe.engine.m3_identity_slots import bind as bind_identity_slots
from girlframe.engine.m3_off_duty import Period, Progress, clone, doctor_credit
from girlframe.engine.m3_policy import RULESET
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def current_original_characters(
    c: Connection,
    game: GameService,
    state: GameState,
    period: Period,
) -> dict[str, str]:
    """Only surviving original period actors have that period's unconsumed authority."""
    if set(period.character_ids) != {str(uid) for uid in period.pilots}:
        raise WorkflowError("SOURCE_OFF_DUTY_MISSING: recover original period characters.")
    result = {}
    for uid, character in period.character_ids.items():
        if uid in period.ended_characters:
            archive = archive_for(state, ActorRef(kind="pilot", entity=uid, incarnation=character))
            progress = period.progress.get(uid)
            body = (
                c.scalar(
                    sa.select(t.m2["m2_state_history"].c.body_json).where(
                        t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_state_history"].c.event_id == archive.source_event,
                    )
                )
                if archive
                else None
            )
            proof = GameState.model_validate_json(body) if body else None
            if (
                archive is None
                or proof is None
                or archive not in proof.career_archives
                or progress is None
                or progress.career_ended != archive.id
            ):
                raise WorkflowError("SOURCE_CAREER_MISSING: recover the actual ended period actor.")
            continue
        if game.character_binding(c, state, int(uid), require_current_profile=False) != character:
            raise WorkflowError("STALE_OFF_DUTY: this period belongs to its original Girl.")
        result[uid] = character
    return result


def end_off_duty_original(c: Connection, game: GameService, archive: CareerArchive) -> None:
    """Ending a real career closes its participation, without pretending recovery occurred."""
    periods = OffDutyService(MissionService(game.store))
    table = t.m3["m3_off_duty"]
    state = load_state(c, game.store.campaign_id)
    same_source = [x for x in state.career_archives if x.source_event == archive.source_event]
    for body in list(
        c.scalars(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.phase != "complete",
            )
        )
    ):
        old = Period.model_validate_json(body)
        endings = [
            x
            for x in same_source
            if old.character_ids.get(x.actor.entity) == x.actor.incarnation
            and x.actor.entity not in old.ended_characters
        ]
        if not endings:
            continue
        updated = clone(old)
        updated.status_review = None
        updated.status_review_game_revision = None
        # One actual source may end multiple originals. Save one period revision for
        # that event, preserving the history table's one-source/one-snapshot contract.
        for ending in endings:
            uid = ending.actor.entity
            progress = updated.progress.setdefault(uid, Progress())
            progress.career_ended = ending.id
            updated.ended_characters[uid] = str(ending.actor.incarnation)
            # Do not manufacture the departed original's unfinished attendance.
            for owner, other in updated.progress.items():
                if (
                    owner != uid
                    and other.scene is not None
                    and int(uid) in other.scene.participants
                    and (
                        not other.scene.character_ids
                        or other.scene.character_ids.get(uid) == ending.actor.incarnation
                    )
                    and set(other.scene.participants) != set(other.scene.acknowledgements)
                ):
                    other.scene = None
            handler_scene = updated.handler_scene
            if (
                handler_scene is not None
                and int(uid) in handler_scene.participants
                and set(handler_scene.participants) != set(handler_scene.acknowledgements)
            ):
                updated.handler_scene = None
                updated.handler_recipient = updated.handler_work = updated.handler_context = None
        updated.revision += 1
        periods._save(c, updated, archive.source_event)
        if not state.order and set(updated.ended_characters) == set(updated.character_ids):
            # There is no Girl for a new Handler scene; no scene or attendance is invented.
            work = t.m3["m3_required_work"]
            latest = {
                row["id"]: dict(row)
                for row in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == game.store.campaign_id,
                        work.c.off_duty_id == old.id,
                        work.c.kind == "off_duty_handler_scene",
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }
            for row in latest.values():
                if row["state"] == "resolved":
                    continue
                c.execute(
                    work.insert().values(
                        **{
                            k: v
                            for k, v in row.items()
                            if k not in ("revision", "state", "body_json", "event_id")
                        },
                        revision=row["revision"] + 1,
                        state="resolved",
                        event_id=archive.source_event,
                        body_json=json.dumps(
                            json.loads(row["body_json"])
                            | dict(
                                resolution="no_remaining_girl_after_career_end",
                                career_archive=archive.id,
                            )
                        ),
                    )
                )


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
        invited = period.handler_scene and viewer.user_id in period.handler_scene.participants
        invited = invited or any(
            progress.scene and viewer.user_id in progress.scene.participants
            for progress in period.progress.values()
        )
        if (
            viewer.user_id not in period.pilots
            and viewer.user_id != current_handler
            and not invited
        ):
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
        from girlframe.services.m3_privileges import resume_restored_benefits
        from girlframe.services.m3_scene_requisitions import (
            synchronize as synchronize_scene_purchases,
        )

        resume_restored_benefits(c, self.store, period, event)
        synchronize_scene_purchases(c, self.store, period, event)
        from girlframe.services.m3_personal_firearm import synchronize as firearms

        firearms(c, self.store, period, event)
        from girlframe.services.m3_defeat_replacement import synchronize as replacements

        replacements(c, self.store, period, event)
        from girlframe.services.m3_handler_plays import synchronize_off_duty

        synchronize_off_duty(c, self.game, period, event)
        from girlframe.services.m3_janus_pandora import synchronize as janus_pandora

        janus_pandora(c, self.store, period, event)
        from girlframe.services.m3_janus_pet import synchronize as janus_pet

        janus_pet(c, self.store, period, event)

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

    def _frameless_off_duty(self, c: Connection, state: GameState, owner: int) -> bool:
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.engine.m3_careers import can_pilot
        from girlframe.services.m3_defeat_replacement import pending

        actor = ActorRef(
            kind="pilot",
            entity=str(owner),
            incarnation=self.game.character_binding(c, state, owner, require_current_profile=False),
        )
        return not can_pilot(state, actor) or pending(c, self.store, state, owner)

    def begin(self, viewer: GuildViewer, key: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.missions._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_gorgon_dormant import (
                require_clear as require_gorgon_costs_clear,
            )
            from girlframe.services.m3_quadrant_loss import require_aftermath_clear

            require_aftermath_clear(state)
            require_gorgon_costs_clear(self.game, c)
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
                or (
                    state.sheets[str(uid)].frame_scrapped
                    and not self._frameless_off_duty(c, state, uid)
                )
                or self.game.immediate_work(c, uid)
                or state.sheets[str(uid)].sedation_locked
                for uid in state.order
            ):
                raise WorkflowError(
                    "Resolve the current Pilot roster, immediate work and old locks."
                )
            characters = {
                str(uid): self.game.character_binding(c, state, uid, require_current_profile=False)
                for uid in state.order
            }
            period = Period(
                id=str(uuid4()),
                handler=viewer.user_id,
                pilots=state.order,
                character_ids=characters,
            )
            from girlframe.engine.m3_repairs import begin_period

            bound = begin_period(state, period.id)
            changed = bound != state
            state = bound
            for uid in state.order:
                original = state.sheets[str(uid)]
                normalized = bind_identity_slots(original)
                changed |= normalized != original
                state.sheets[str(uid)] = normalized
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.off_duty_preparing",
                state if changed else None,
                period_id=period.id,
            )
            self._save(c, period, event)
            from girlframe.services.m3_debts import synchronize

            synchronize(c, self.store, state, event)
            # This is an actual dependency, not an operator acknowledgement checkbox.
            self._work(c, period, viewer.user_id, "off_duty_strain_start", event)
            self._work(c, period, viewer.user_id, "off_duty_handler_scene", event)
            self._work(c, period, viewer.user_id, "off_duty_status_review", event)
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

    def current(self, viewer: GuildViewer) -> dict[str, Any] | None:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            table = t.m3["m3_off_duty"]
            identity = c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.phase != "complete"
                )
            )
        return self.get(viewer, identity) if identity else None

    def credit_review(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            work = t.m3["m3_required_work"]
            row = (
                c.execute(
                    sa.select(work)
                    .where(work.c.campaign_id == self.store.campaign_id, work.c.id == identity)
                    .order_by(work.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["kind"] != "doctor_credit"
                or row["owner_id"] != str(viewer.user_id)
            ):
                raise WorkflowError("Resume your own DoctorDoctor credit record.")
            period = self._get(c, row["off_duty_id"])
            self._view(c, viewer, period)
            state = load_state(c, self.store.campaign_id)
            setup = HandlerService(self.store)
            return {
                "period_id": period.id,
                "period_revision": period.revision,
                "game_revision": state.revision,
                "state": row["state"],
                "recipients": tuple(
                    (str(uid), state.sheets[str(uid)].callsign)
                    for uid in state.order
                    if uid != viewer.user_id and setup._member(c, uid)
                ),
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
