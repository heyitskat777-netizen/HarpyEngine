"""Owned free replacement proposals, Handler packages and atomic application."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_replacement as rules
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m3_frame_state import Package, Preferences
from girlframe.engine.playbooks import FRAME_TYPES
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ROOT = "doctor_frame_replacement"
DEFEAT_ROOT = "defeat_frame_replacement_active"
ROOTS = (ROOT, DEFEAT_ROOT)
PACKAGE = "frame_replacement_package"
COURT = "frame_replacement_court"


class ReplacementService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    @staticmethod
    def _package_available(supplied: Package) -> None:
        from girlframe.engine.m3_personal_firearm import RULE

        if RULE in supplied.additional_rules:
            raise WorkflowError(
                "UNSUPPORTED_RULE: a free Personal Firearm package needs its actual owned "
                "pistol and Girl Asset-cap issuance procedure"
            )

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
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
        if row is None or row["kind"] not in (*ROOTS, PACKAGE, COURT):
            raise WorkflowError("This replacement task is unavailable.")
        return dict(row)

    def _body(self, row: dict[str, Any]) -> dict[str, Any]:
        return dict(json.loads(row["body_json"]))

    def _handler_id(self, c: Connection) -> int | None:
        return HandlerService(self.store).current(c)[1].handler_id

    def _view(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self.game.authorize(c, viewer, game=False)
        if viewer.user_id != self._handler_id(c) and str(viewer.user_id) not in (
            row["owner_id"],
            row["subject_id"],
        ):
            raise WorkflowError("This replacement belongs to other participants.")

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        event: str,
        body: dict[str, Any],
        *,
        state: str = "pending",
    ) -> None:
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
                state=state,
            )
        )

    def _root(self, c: Connection, row: dict[str, Any]) -> dict[str, Any]:
        return row if row["kind"] in ROOTS else self._row(c, self._body(row)["root_id"])

    def _check(
        self, c: Connection, row: dict[str, Any], revision: int, game_revision: int
    ) -> dict[str, Any]:
        if row["state"] == "resolved" or row["revision"] != revision:
            raise WorkflowError("STALE_WORK: reopen the current replacement task.")
        state = load_state(c, self.store.campaign_id)
        if state.revision != game_revision:
            raise WorkflowError("STALE_STATE: review the changed state and resubmit the proposal.")
        root = self._root(c, row)
        if root["state"] == "resolved" or not state.sheets[root["subject_id"]].frame_scrapped:
            raise WorkflowError("The compulsory replacement is no longer pending.")
        origin = self._body(root)
        sheet = state.sheets[root["subject_id"]]
        character_id = self.game.character_binding(
            c, state, int(root["subject_id"]), require_current_profile=False
        )
        if root["kind"] == DEFEAT_ROOT:
            from girlframe.services.m3_defeat_replacement import check_active

            check_active(c, self.store, root)
        if not {
            "origin_frame",
            "origin_frame_id",
            "origin_fingerprint",
            "origin_character_id",
        } <= set(origin):
            raise WorkflowError(
                "UNSUPPORTED_RULE: legacy replacement origin needs explicit migration review."
            )
        if (
            origin["origin_frame"] != sheet.frame
            or origin["origin_fingerprint"] != sheet.source_fingerprint
            or origin["origin_character_id"] != character_id
            or origin["origin_frame_id"]
            != (sheet.frame_runtime.id if sheet.frame_runtime else None)
        ):
            raise WorkflowError(
                "STALE_FRAME: this obligation belongs to a different Frame or character."
            )
        if row["kind"] not in ROOTS:
            body, parent = self._body(row), self._body(root)
            if body["proposal_id"] != parent.get("proposal_id"):
                raise WorkflowError("STALE_PROPOSAL: this task belongs to an older proposal.")
            if parent["game_revision"] != game_revision:
                raise WorkflowError("STALE_STATE: the owner must submit a fresh proposal.")
        actions = t.m2["m2_actions"]
        if c.scalar(
            sa.select(actions.c.id)
            .where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
            )
            .limit(1)
        ):
            raise WorkflowError("Finish pending scene Plays before replacing a Frame.")
        return root

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
            row = self._row(c, identity)
            self._view(c, viewer, row)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("Only the assigned owner may submit this replacement task.")
            if row["kind"] == PACKAGE:
                self.missions._handler(c, viewer)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=authorize
            )
        except ValidationError:
            raise WorkflowError("Invalid replacement input; reopen the current task.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            self._view(c, viewer, row)
            root = self._root(c, row)
            body, parent = self._body(row), self._body(root)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets[root["subject_id"]]
            result = {
                k: row[k] for k in ("id", "revision", "kind", "state", "owner_id", "subject_id")
            }
            result.update(
                game_revision=state.revision, callsign=sheet.callsign, current_frame=sheet.frame
            )
            if row["kind"] == COURT:
                result.update(role=body["role"], proposed_frame="THE RED QUEEN")
                return result
            result["preferences"] = parent.get("preferences")
            result["stale"] = parent.get("game_revision", state.revision) != state.revision
            result["frames"] = tuple(
                (name, label)
                for name, label in FRAME_TYPES.items()
                if name != "JANUS"
                and name != ("JANUS-B" if sheet.frame == "JANUS" else sheet.frame)
            )
            people = [
                (int(uid), other.callsign)
                for uid, other in state.sheets.items()
                if int(uid) != sheet.owner and HandlerService(self.store)._member(c, int(uid))
            ]
            handler = self._handler_id(c)
            if handler is not None and HandlerService(self.store)._member(c, handler):
                people.append((handler, "Handler"))
            result["people"] = people
            result["bond_targets"] = [
                (uid, label)
                for uid, label in people
                if state.bonds.get(":".join(str(x) for x in sorted((sheet.owner, uid))))
            ]
            result["package"] = None
            result["package_id"] = parent.get("package_id")
            result["court_accepted"] = False
            if parent.get("package_id"):
                quote = self._row(c, parent["package_id"])
                result["package"] = self._body(quote).get("package")
                result["package_revision"] = quote["revision"]
            if parent.get("court_id"):
                consent = self._row(c, parent["court_id"])
                result["court_accepted"] = (
                    consent["state"] == "resolved" and self._body(consent).get("accepted") is True
                )
            result["ready"] = bool(
                result["package"] is not None
                and not result["stale"]
                and (not parent.get("court_id") or result["court_accepted"])
            )
            return result

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        selected: Preferences,
    ) -> dict[str, Any]:
        selected = Preferences.model_validate_json(selected.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            root = self._row(c, identity)
            self._check(c, root, revision, game_revision)
            if root["kind"] not in ROOTS or root["subject_id"] != str(viewer.user_id):
                raise WorkflowError("The affected player must propose its new Frame.")
            state = load_state(c, self.store.campaign_id)
            handler = self.missions._current_handler(c)
            people = frozenset(
                int(uid) for uid in state.sheets if HandlerService(self.store)._member(c, int(uid))
            ) | frozenset({handler})
            chosen = rules.preferences(
                state.sheets[root["subject_id"]].frame, selected, viewer.user_id, people
            )
            event = self.game.event(
                c, viewer.user_id, key, "m3.frame_replacement_proposed", work_id=identity
            )
            old = self._body(root)
            for field in ("package_id", "court_id"):
                if old.get(field):
                    child = self._row(c, old[field])
                    if child["state"] != "resolved":
                        self._save(
                            c,
                            child,
                            event,
                            self._body(child) | {"superseded": True},
                            state="resolved",
                        )
            proposal_id, package_id = str(uuid4()), str(uuid4())
            body = {
                k: v
                for k, v in old.items()
                if k
                not in ("court_id", "package_id", "preferences", "proposal_id", "game_revision")
            }
            body.update(
                preferences=chosen.model_dump(mode="json"),
                proposal_id=proposal_id,
                package_id=package_id,
                game_revision=state.revision,
            )
            related(
                c,
                self.store,
                root,
                package_id,
                handler,
                viewer.user_id,
                PACKAGE,
                {"root_id": identity, "proposal_id": proposal_id},
                event,
            )
            if chosen.court_target:
                court_id = str(uuid4())
                body["court_id"] = court_id
                related(
                    c,
                    self.store,
                    root,
                    court_id,
                    chosen.court_target,
                    viewer.user_id,
                    COURT,
                    {"root_id": identity, "proposal_id": proposal_id, "role": chosen.court_role},
                    event,
                )
            self._save(c, root, event, body)
            return {"id": identity, "state": "proposed", "package_id": package_id}

        return self._write(
            viewer,
            key,
            identity,
            "m3.frame_replacement_proposed",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "preferences": selected.model_dump(mode="json"),
            },
            operation,
        )

    def quote(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        supplied: Package,
    ) -> dict[str, Any]:
        supplied = Package.model_validate_json(supplied.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            root = self._check(c, row, revision, game_revision)
            if row["kind"] != PACKAGE:
                raise WorkflowError("The Handler must submit the assigned package task.")
            registry = self.missions.access.registry
            if registry is None:
                raise WorkflowError("A reviewed source registry is required.")
            self._package_available(supplied)
            parent = self._body(root)
            rules.package(
                load_state(c, self.store.campaign_id),
                int(root["subject_id"]),
                Preferences.model_validate_json(json.dumps(parent["preferences"])),
                supplied,
                registry,
            )
            event = self.game.event(
                c, viewer.user_id, key, "m3.frame_package_quoted", work_id=root["id"]
            )
            self._save(
                c,
                row,
                event,
                self._body(row)
                | {"package": supplied.model_dump(mode="json"), "handler": viewer.user_id},
                state="quoted",
            )
            self._save(c, root, event, parent)
            return {"id": root["id"], "state": "quoted"}

        return self._write(
            viewer,
            key,
            identity,
            "m3.frame_package_quoted",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "package": supplied.model_dump(mode="json"),
            },
            operation,
        )

    def answer_court(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        accepted: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            if row["kind"] != COURT or type(accepted) is not bool:
                raise WorkflowError("Answer only your assigned Court request.")
            if accepted:
                root = self._check(c, row, revision, game_revision)
            else:
                if row["state"] == "resolved" or row["revision"] != revision:
                    raise WorkflowError("STALE_WORK: this Court request is already answered.")
                root = self._root(c, row)
                if root["state"] == "resolved" or self._body(row)["proposal_id"] != self._body(
                    root
                ).get("proposal_id"):
                    raise WorkflowError("STALE_PROPOSAL: reopen the current Court request.")
            event = self.game.event(
                c, viewer.user_id, key, "m3.replacement_court_answered", work_id=identity
            )
            self._save(c, row, event, self._body(row) | {"accepted": accepted}, state="resolved")
            self._save(c, root, event, self._body(root))
            return {"id": identity, "state": "resolved", "accepted": accepted}

        return self._write(
            viewer,
            key,
            identity,
            "m3.replacement_court_answered",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "accepted": accepted,
            },
            operation,
        )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        package_revision: int,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            root = self._row(c, identity)
            self._check(c, root, revision, game_revision)
            if root["kind"] not in ROOTS or root["subject_id"] != str(viewer.user_id):
                raise WorkflowError(
                    "Only the affected player confirms its exact replacement package."
                )
            parent = self._body(root)
            if parent.get("game_revision") != game_revision or not parent.get("package_id"):
                raise WorkflowError("STALE_PROPOSAL: submit a fresh proposal and package review.")
            quote = self._row(c, parent["package_id"])
            body = self._body(quote)
            if (
                quote["state"] != "quoted"
                or quote["revision"] != package_revision
                or body["handler"] != self._handler_id(c)
            ):
                raise WorkflowError("STALE_PACKAGE: review the current Handler's exact package.")
            consent = False
            if parent.get("court_id"):
                answer = self._row(c, parent["court_id"])
                consent = (
                    answer["state"] == "resolved" and self._body(answer).get("accepted") is True
                )
            registry = self.missions.access.registry
            if registry is None:
                raise WorkflowError("A reviewed registry is required.")
            selected = Preferences.model_validate_json(json.dumps(parent["preferences"]))
            if selected.court_target and not HandlerService(self.store)._member(
                c, selected.court_target
            ):
                raise WorkflowError("The Court recipient is unavailable; choose a new proposal.")
            frame_id = str(uuid4())
            supplied = Package.model_validate_json(json.dumps(body["package"]))
            self._package_available(supplied)
            updated = rules.replace(
                load_state(c, self.store.campaign_id),
                viewer.user_id,
                selected,
                supplied,
                registry,
                work_id=identity,
                frame_id=frame_id,
                court_accepted=consent,
            )
            sheet = updated.sheets[str(viewer.user_id)]
            profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .one()
            )
            if profile["revision"] != sheet.source_profile_revision:
                raise WorkflowError("STALE_PROFILE: resolve the profile before replacement.")
            public = json.loads(profile["public_json"]) | {"frame_playbook": sheet.frame}
            draft = DraftInput.model_validate(public)
            sheet.source_profile_revision = profile["revision"] + 1
            c.execute(
                t.characters.update()
                .where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
                .values(revision=sheet.source_profile_revision, public_json=json.dumps(public))
            )
            self.store._enqueue_sync(c, viewer.user_id, sheet.source_profile_revision, draft)
            from girlframe.engine.m3_actor_state import ActorRef
            from girlframe.engine.m3_enforcer_requisitions import replacement_grants

            replacement_event = str(uuid4())
            updated = replacement_grants(
                updated,
                ActorRef(kind="pilot", entity=str(viewer.user_id), incarnation=sheet.character_id),
                identity,
                replacement_event,
                registry,
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.compulsory_frame_replaced",
                updated,
                event_id=replacement_event,
                work_id=identity,
                owner=viewer.user_id,
                frame=sheet.frame,
            )
            c.execute(
                t.snapshots.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(viewer.user_id),
                    revision=sheet.source_profile_revision,
                    character_id=profile["id"],
                    event_id=event,
                    public_json=json.dumps(public),
                    private_json=profile["private_json"],
                )
            )
            self._save(
                c,
                root,
                event,
                parent | {"applied_event": event, "frame_id": frame_id},
                state="resolved",
            )
            self._save(c, quote, event, body | {"applied_event": event}, state="resolved")
            frames = [x for x in sheet.assets if x.family == "frame"]
            if frames and all(x.void for x in frames):
                related(
                    c,
                    self.store,
                    root,
                    str(uuid4()),
                    self.missions._current_handler(c),
                    viewer.user_id,
                    "replacement_void_context",
                    {"source_pdf": 19, "immediate": True, "source_work": identity},
                    event,
                )
            return {"id": identity, "state": "resolved", "frame": sheet.frame}

        return self._write(
            viewer,
            key,
            identity,
            "m3.compulsory_frame_replaced",
            {
                "id": identity,
                "revision": revision,
                "game_revision": game_revision,
                "package_revision": package_revision,
            },
            operation,
        )
