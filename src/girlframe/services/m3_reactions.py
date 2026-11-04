"""Transactional playbook reactions that precede mission rewards."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_reactions as rules
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ReactionService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity,
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] not in (
            "doctor_obsolescence",
            "princess_mission_end",
            "doctor_frame_replacement",
        ):
            raise WorkflowError("This playbook reaction is unavailable.")
        return dict(row)

    def _view(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self.game.authorize(c, viewer, game=False)
        if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
            raise WorkflowError("This reaction belongs to other participants.")

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            self._view(c, viewer, row)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(row["subject_id"])
            if sheet is None:
                raise WorkflowError("Resolve the current canonical Pilot first.")
            result = {
                k: row[k] for k in ("id", "kind", "revision", "state", "owner_id", "subject_id")
            }
            result.update(
                game_revision=state.revision,
                callsign=sheet.callsign,
                obsolescence_marked=sheet.obsolescence_marked,
                frame_scrapped=sheet.frame_scrapped,
            )
            if row["kind"] == "princess_mission_end":
                standards = []
                own = sheet.review.creation.girl_details
                if own and own.own_standard:
                    standards.append(
                        {"role": "own", "label": own.own_standard.label, "is_order": False}
                    )
                standards.extend(
                    {
                        "role": x.role,
                        "label": x.standard.label,
                        "is_order": x.role == "princess_handler",
                    }
                    for x in sheet.review.coordination
                    if x.standard and x.role in ("princess_peer", "princess_handler")
                )
                result["standards"] = standards
                result["ruling_ready"] = (
                    self.store.policy.owner_m3_rulings is not None
                    and self.store.policy.owner_m3_rulings.princess_ace_check is not None
                )
            return result

    def _check(
        self,
        c: Connection,
        viewer: GuildViewer,
        row: dict[str, Any],
        revision: int,
        game_revision: int,
    ) -> None:
        if row["state"] != "pending" or row["revision"] != revision:
            raise WorkflowError("STALE_WORK: reopen this reaction.")
        if load_state(c, self.store.campaign_id).revision != game_revision:
            raise WorkflowError("STALE_STATE: review the changed state first.")
        mission = self.missions._mission(c, row["mission_id"])
        if mission.phase != "ending":
            raise WorkflowError("Resolve mission-end reactions before the final reward snapshot.")
        if mission.handler != viewer.user_id:
            raise WorkflowError("Resolve the mission Handler assignment first.")
        actions = t.m2["m2_actions"]
        if c.scalar(
            sa.select(actions.c.id)
            .where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
            )
            .limit(1)
        ):
            raise WorkflowError("Finish the pending scene Play before mission-end reactions.")

    def _save(self, c: Connection, row: dict[str, Any], event: str, body: dict[str, Any]) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "body_json", "event_id", "state")
                },
                revision=row["revision"] + 1,
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
                state="resolved",
            )
        )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "playbooks")
            self.game.unpaused(c)
            self.missions._handler(c, viewer)
            row = self._row(c, identity)
            self._view(c, viewer, row)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("The designated current Handler must review this reaction.")

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=authorize
            )
        except ValidationError:
            raise WorkflowError("Invalid playbook reaction; reopen the saved task.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def doctor(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, game_revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, viewer, row, revision, game_revision)
            mission = self.missions._mission(c, row["mission_id"])
            if row["kind"] != "doctor_obsolescence" or mission.success is not False:
                raise WorkflowError("This task does not record a failed-Cadre-mission trigger.")
            state = load_state(c, self.store.campaign_id)
            result = rules.mark_obsolescence(state.sheets[row["subject_id"]], "mission_failure")
            state.sheets[row["subject_id"]] = result.sheet
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.doctor_obsolescence_marked",
                state,
                work_id=identity,
                source_trigger="mission_failure",
            )
            self._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | {"marked": result.sheet.obsolescence_marked},
            )
            if result.replacement_required:
                self.missions._work(
                    c,
                    mission,
                    str(uuid4()),
                    result.sheet.owner,
                    result.sheet.owner,
                    "doctor_frame_replacement",
                    {
                        "source_pdf": 71,
                        "immediate": True,
                        "source_work": identity,
                        "origin_frame": result.sheet.frame,
                        "origin_frame_id": result.sheet.frame_runtime.id
                        if result.sheet.frame_runtime
                        else None,
                        "origin_fingerprint": result.sheet.source_fingerprint,
                        "origin_character_id": c.scalar(
                            sa.select(t.characters.c.id).where(
                                t.characters.c.campaign_id == self.store.campaign_id,
                                t.characters.c.user_id == str(result.sheet.owner),
                            )
                        ),
                    },
                    event,
                )
            return {
                "id": identity,
                "state": "resolved",
                "replacement_required": result.replacement_required,
            }

        return self._write(
            viewer,
            key,
            identity,
            "m3.doctor_obsolescence_marked",
            {"id": identity, "revision": revision, "game_revision": game_revision},
            operation,
        )

    def princess(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        *,
        upheld: bool,
        rationale: str,
    ) -> dict[str, Any]:
        if not rationale.strip() or len(rationale) > 1200:
            raise WorkflowError("Record a short factual standards review in 1–1200 characters.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, viewer, row, revision, game_revision)
            if row["kind"] != "princess_mission_end":
                raise WorkflowError("This is not a Princess standards review.")
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets[row["subject_id"]]
            if (
                sheet.review.creation.girl_playbook != "PRINCESS"
                or sheet.review.creation.girl_details is None
                or sheet.review.creation.girl_details.own_standard is None
                or {x.role for x in sheet.review.coordination if x.standard}
                != {"princess_peer", "princess_handler"}
            ):
                raise WorkflowError("Resolve all three current Princess standards before review.")
            rulings = self.store.policy.owner_m3_rulings
            updated = rules.princess_mission_end(
                state,
                sheet.owner,
                upheld=upheld,
                ace_check=rulings.princess_ace_check if rulings else None,
            )
            event = self.game.event(
                c, viewer.user_id, key, "m3.princess_standards_reviewed", updated, work_id=identity
            )
            self._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | {"upheld": upheld, "rationale": rationale.strip()},
            )
            return {"id": identity, "state": "resolved", "upheld": upheld}

        return self._write(
            viewer,
            key,
            identity,
            "m3.princess_standards_reviewed",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "upheld": upheld,
                "rationale": rationale,
            },
            operation,
        )
