"""Owned discipline work, fixed-proposal Handler consultation and atomic effects."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_punishments as rules
from girlframe.engine.rules_registry import Registry
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class PunishmentService:
    def __init__(self, store: OnboardingStore, registry: Registry | None = None):
        self.store = store
        self.missions = MissionService(store, registry)
        self.game = self.missions.game

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
            "punishment",
            "punishment_consult",
            "punishment_paired_identity_heat",
        ):
            raise WorkflowError("This discipline task is unavailable.")
        return dict(row)

    def _body(self, row: dict[str, Any]) -> dict[str, Any]:
        return dict(json.loads(row["body_json"]))

    def _view(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self.game.authorize(c, viewer, game=False)
        permitted = {row["owner_id"], row["subject_id"]}
        if row["kind"] == "punishment_consult":
            permitted.add(str(self._body(row)["inflictor"]))
        if str(viewer.user_id) not in permitted:
            raise WorkflowError("This discipline task belongs to other participants.")

    def _actor(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self._view(c, viewer, row)
        if row["owner_id"] != str(viewer.user_id):
            raise WorkflowError("Only the designated decision owner may submit this task.")
        state = load_state(c, self.store.campaign_id)
        if viewer.user_id == state.handler:
            HandlerService(self.store).authorize(c, viewer)
        elif str(viewer.user_id) not in state.sheets:
            raise WorkflowError("A current canonical Pilot or Handler is required.")

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
            self.missions.access.authorize(c, viewer, "discipline")
            self.game.unpaused(c)
            self._actor(c, viewer, self._row(c, identity))

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=authorize
            )
        except ValidationError:
            raise WorkflowError("Invalid discipline choices; reopen the current task.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _check(self, c: Connection, row: dict[str, Any], revision: int, game_revision: int) -> None:
        if row["state"] == "resolved" or row["revision"] != revision:
            raise WorkflowError("STALE_WORK: reopen the current discipline task.")
        if load_state(c, self.store.campaign_id).revision != game_revision:
            raise WorkflowError("STALE_STATE: sheets or Status changed; review the task again.")
        actions = t.m2["m2_actions"]
        if c.scalar(
            sa.select(actions.c.id)
            .where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
            )
            .limit(1)
        ):
            raise WorkflowError("Finish the pending scene Play before applying mission discipline.")

    def _save(self, c: Connection, row: dict[str, Any], event: str, **values: Any) -> None:
        body = values.pop("body", self._body(row))
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{k: v for k, v in row.items() if k not in ("revision", "body_json", "event_id")},
                revision=row["revision"] + 1,
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
            )
            .values(**values)
        )

    def _bundle(self, c: Connection, row: dict[str, Any]) -> list[dict[str, Any]]:
        result = [
            x
            for x in self.missions._pending(c, row["mission_id"])
            if x["kind"] == "punishment" and x["subject_id"] == row["subject_id"]
        ]
        if not result or any(x["owner_id"] != row["owner_id"] for x in result):
            raise WorkflowError("Resolve conflicting discipline ownership before applying effects.")
        if any(
            self._body(x).get("reason") not in ("mission_failure", "dog_mission_end")
            for x in result
        ):
            raise WorkflowError("This cause requires its own source-specific discipline resolver.")
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            self._view(c, viewer, row)
            state = load_state(c, self.store.campaign_id)
            subject = int(row["subject_id"])
            sheet = state.sheets.get(str(subject))
            body = self._body(row)
            result: dict[str, Any] = {
                k: row[k]
                for k in (
                    "id",
                    "revision",
                    "kind",
                    "state",
                    "owner_id",
                    "subject_id",
                )
            }
            result.update(
                game_revision=state.revision, callsign=sheet.callsign if sheet else "Pilot"
            )
            if row["kind"] == "punishment_consult":
                result["proposal"] = body["proposal"]
                result["inflictor"] = body["inflictor"]
                result["stale"] = body["game_revision"] != state.revision
                proposal = body["proposal"]
                labels = {x.id: x.name for x in sheet.identities + sheet.assets} if sheet else {}
                if sheet:
                    labels.update({x.id: x.label for x in sheet.tags})
                result["summary"] = [rules.KINDS[proposal["kind"]][0]] + [
                    key.replace("_", " ")
                    + ": "
                    + str(
                        [labels.get(x, x) for x in value]
                        if isinstance(value, list)
                        else labels.get(str(value), value)
                    )
                    for key, value in proposal.items()
                    if key != "kind" and value
                ]
            if row["kind"] == "punishment" and row["state"] != "resolved":
                bundle = self._bundle(c, row)
                result["causes"] = [self._body(x)["reason"] for x in bundle]
                result["consultation"] = None
                if body.get("consult_id"):
                    consultation = self._row(c, body["consult_id"])
                    result["consultation"] = {
                        "id": consultation["id"],
                        "state": consultation["state"],
                        "approved": self._body(consultation).get("approved", False),
                    }
                # Inflictor receives only fields necessary for the assigned choices.
                # No descriptions, notes, review snapshots, private NPCs or raw state.
                if row["owner_id"] == str(viewer.user_id) and sheet:
                    result["choices"] = {
                        "identities": [{"id": x.id, "name": x.name} for x in sheet.identities],
                        "removable_identities": [
                            {"id": x.id, "name": x.name}
                            for x in sheet.identities
                            if not x.protected or (x.paired and subject == viewer.user_id)
                        ],
                        "assets": [
                            {"id": x.id, "name": x.name, "family": x.family, "damaged": x.damaged}
                            for x in sheet.assets
                        ],
                        "tags": [{"id": x.id, "name": x.label} for x in sheet.tags],
                        "bonds": [
                            (uid, other.callsign)
                            for uid, other in state.sheets.items()
                            if int(uid) != subject
                            and state.bonds.get(
                                ":".join(str(x) for x in sorted((subject, int(uid)))), 0
                            )
                        ],
                        "pilots": [
                            (uid, other.callsign)
                            for uid, other in state.sheets.items()
                            if HandlerService(self.store)._member(c, int(uid))
                        ],
                        "handler": state.handler,
                        "identity_cap_reached": sum(
                            not x.protected or x.paired for x in sheet.identities
                        )
                        >= 4,
                    }
                    if state.handler is not None and state.bonds.get(
                        ":".join(str(x) for x in sorted((subject, state.handler))), 0
                    ):
                        result["choices"]["bonds"].append((str(state.handler), "Handler"))
            return result

    def _approved(
        self,
        c: Connection,
        row: dict[str, Any],
        bundle: list[dict[str, Any]],
        details: rules.Details,
    ) -> bool:
        identity = self._body(row).get("consult_id")
        if not identity:
            return False
        consultation = self._row(c, identity)
        body = self._body(consultation)
        state = load_state(c, self.store.campaign_id)
        return bool(
            consultation["state"] == "resolved"
            and body.get("approved") is True
            and int(consultation["owner_id"]) == state.handler
            and body["game_revision"] == state.revision
            and body["proposal"] == details.model_dump(mode="json")
            and body["work_versions"] == {x["id"]: x["revision"] for x in bundle}
        )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        details: rules.Details,
    ) -> dict[str, Any]:
        details = rules.Details.model_validate_json(details.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            if row["kind"] != "punishment":
                raise WorkflowError("Choose the typed resolver for this required task.")
            severity = rules.validate(details)
            bundle = self._bundle(c, row)
            state = load_state(c, self.store.campaign_id)
            if details.kind == "passing_responsibility":
                target = details.delegate
                if (
                    target is None
                    or str(target) not in state.sheets
                    or not HandlerService(self.store)._member(c, target)
                ):
                    raise WorkflowError("Delegate to a current active Pilot.")
                if target == viewer.user_id:
                    raise WorkflowError("You already own this task; choose its Punishment instead.")
                event = self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.punishment_delegated",
                    work_id=identity,
                    cause_count=len(bundle),
                )
                for item in bundle:
                    body = self._body(item)
                    consultation_id = body.pop("consult_id", None)
                    if consultation_id:
                        consultation = self._row(c, consultation_id)
                        if consultation["state"] != "resolved":
                            self._save(
                                c,
                                consultation,
                                event,
                                state="resolved",
                                body=self._body(consultation)
                                | {"approved": False, "superseded": True},
                            )
                    self._save(c, item, event, owner_id=str(target), body=body)
                return {"id": identity, "state": "delegated", "cause_count": len(bundle)}
            consulted = self._approved(c, row, bundle, details)
            if severity == "moderate" and viewer.user_id != state.handler and not consulted:
                raise WorkflowError(
                    "HANDLER_CONSULT_REQUIRED: submit this exact proposal for Handler "
                    "consultation first."
                )
            result = rules.apply(
                state,
                int(row["subject_id"]),
                viewer.user_id,
                details,
                entity_id=str(uuid4()),
                off_duty=False,
                handler_consulted=consulted,
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.punishment_applied",
                result.state,
                work_id=identity,
                punishment=details.kind,
                cause_count=len(bundle),
            )
            for item in bundle:
                body = self._body(item) | {
                    "punishment": details.model_dump(mode="json"),
                    "applied_event": event,
                }
                self._save(c, item, event, state="resolved", body=body)
                consultation_id = body.get("consult_id")
                if consultation_id:
                    consultation = self._row(c, consultation_id)
                    if consultation["state"] != "resolved":
                        self._save(
                            c,
                            consultation,
                            event,
                            state="resolved",
                            body=self._body(consultation) | {"approved": False, "superseded": True},
                        )
            mission = self.missions._mission(c, row["mission_id"])
            for followup in result.followups:
                self.missions._work(
                    c,
                    mission,
                    str(uuid4()),
                    followup.owner,
                    followup.owner,
                    "punishment_" + followup.kind,
                    followup.model_dump(mode="json") | {"immediate": True, "source_work": identity},
                    event,
                )
            return {
                "id": identity,
                "state": "resolved",
                "cause_count": len(bundle),
                "followups": len(result.followups),
            }

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_apply",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "details": details.model_dump(mode="json"),
            },
            operation,
        )

    def split_paired_heat(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        share: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            if (
                row["kind"] != "punishment_paired_identity_heat"
                or type(share) is not int
                or not 0 <= share <= 5
            ):
                raise WorkflowError(
                    "Only the Paired Identity's owner chooses a zero-to-five Heat share."
                )
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if sheet is None or row["subject_id"] != str(viewer.user_id):
                raise WorkflowError("The Paired Identity belongs to another Pilot.")
            pair = state.sheets.get(str(sheet.pair))
            if share and (pair is None or pair.owner == viewer.user_id):
                raise WorkflowError("Resolve the current Pair before sharing Heat.")
            sheet.heat += 5 - share
            sheet.revision += 1
            if share and pair is not None:
                pair.heat += share
                pair.revision += 1
            event = self.game.event(
                c, viewer.user_id, key, "m3.paired_identity_heat_split", state, work_id=identity
            )
            self._save(c, row, event, state="resolved", body=self._body(row) | {"share": share})
            return {"id": identity, "state": "resolved"}

        return self._write(
            viewer,
            key,
            identity,
            "m3.paired_identity_heat_split",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "share": share,
            },
            operation,
        )

    def consult(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        details: rules.Details,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self._check(c, row, revision, game_revision)
            state = load_state(c, self.store.campaign_id)
            if (
                row["kind"] != "punishment"
                or rules.validate(details) != "moderate"
                or viewer.user_id == state.handler
            ):
                raise WorkflowError(
                    "Only a designated Pilot inflictor needs Moderate consultation."
                )
            if state.handler is None:
                raise WorkflowError("Appoint a Handler first.")
            # Validate mechanical legality before asking the Handler to review it.
            rules.apply(
                state,
                int(row["subject_id"]),
                viewer.user_id,
                details,
                entity_id="consultation-preview",
                off_duty=False,
                handler_consulted=True,
            )
            bundle = self._bundle(c, row)
            previous = self._body(row).get("consult_id")
            if previous and self._row(c, previous)["state"] != "resolved":
                raise WorkflowError("A Handler consultation is already pending; reopen it.")
            consultation_id = str(uuid4())
            event = self.game.event(
                c, viewer.user_id, key, "m3.punishment_consult_requested", work_id=identity
            )
            body = {
                "proposal": details.model_dump(mode="json"),
                "inflictor": viewer.user_id,
                "game_revision": state.revision,
                "work_versions": {x["id"]: x["revision"] + 1 for x in bundle},
            }
            self.missions._work(
                c,
                self.missions._mission(c, row["mission_id"]),
                consultation_id,
                state.handler,
                int(row["subject_id"]),
                "punishment_consult",
                body,
                event,
            )
            for item in bundle:
                self._save(c, item, event, body=self._body(item) | {"consult_id": consultation_id})
            return {"id": consultation_id, "state": "pending"}

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_consult",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "details": details.model_dump(mode="json"),
            },
            operation,
        )

    def answer_consultation(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, approve: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            HandlerService(self.store).authorize(c, viewer)
            if (
                row["kind"] != "punishment_consult"
                or row["state"] == "resolved"
                or row["revision"] != revision
                or type(approve) is not bool
            ):
                raise WorkflowError("STALE_WORK: reopen the current consultation.")
            body = self._body(row)
            if approve and load_state(c, self.store.campaign_id).revision != body["game_revision"]:
                raise WorkflowError(
                    "STALE_STATE: decline this stale proposal and request a fresh review."
                )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.punishment_consult_answered",
                work_id=identity,
                approved=approve,
            )
            self._save(c, row, event, state="resolved", body=body | {"approved": approve})
            return {"id": identity, "state": "resolved", "approved": approve}

        return self._write(
            viewer,
            key,
            identity,
            "m3.punishment_consult_answer",
            {"id": identity, "revision": revision, "approve": approve},
            operation,
        )
