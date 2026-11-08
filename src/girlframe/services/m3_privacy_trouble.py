"""Actual inquiry or discipline after a protected-room death; no transcript disclosure."""

import json
from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS = ("privacy_trouble", "privacy_inquiry_response")


class PrivacyTroubleService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
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
        if row is None or row["kind"] not in KINDS:
            raise WorkflowError("This original Privacy consequence is unavailable.")
        return dict(row)

    def _source(
        self, c: Connection, row: dict[str, Any], *, writing: bool = False
    ) -> tuple[GameState, dict[str, Any]]:
        state, body = load_state(c, self.store.campaign_id), json.loads(row["body_json"])
        archive = next(
            (x for x in state.career_archives if x.id == body.get("source_career")), None
        )
        if (
            archive is None
            or archive.ending not in ("death", "execution")
            or archive.actor.model_dump(mode="json") != body.get("ended_actor")
        ):
            raise WorkflowError("SOURCE_PRIVACY_DEATH_MISSING: recover the original actual ending.")
        actor = body.get("source_actor")
        if writing and actor is not None:
            ref = ActorRef.model_validate_json(json.dumps(actor))
            if (
                self.game.character_binding(
                    c, state, int(ref.entity), require_current_profile=False
                )
                != ref.incarnation
            ):
                raise WorkflowError(
                    "STALE_PRIVACY_SURVIVOR: no replacement inherits this response."
                )
        if writing and (
            state.handler != body["handler"]
            or HandlerService(self.store).current(c)[1].handler_id != body["handler"]
        ):
            raise WorkflowError("Recover the actual investigation's changed Handler appointment.")
        return state, body

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._get(c, viewer, identity)

    def _get(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        row = self._row(c, identity)
        _, body = self._source(c, row)
        if str(viewer.user_id) not in (
            row["owner_id"],
            row["subject_id"],
            str(body["handler"]),
        ):
            raise WorkflowError("This inquiry belongs to its actual participants.")
        stale = False
        try:
            self._source(c, row, writing=True)
        except WorkflowError:
            stale = True
        return dict(
            id=identity,
            revision=row["revision"],
            kind=row["kind"],
            state=row["state"],
            own=row["owner_id"] == str(viewer.user_id),
            source_actor=body.get("source_actor"),
            question=body.get("question", ""),
            method=body.get("method", ""),
            route=body.get("route"),
            report=body.get("report", ""),
            evidence=body.get("evidence", "unknown"),
            response=body.get("response", ""),
            disclosed=body.get("disclosed"),
            child=body.get("child"),
            stale=stale,
        )

    def _trouble_tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        work = t.m3["m3_required_work"]
        latest = {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.kind.in_(KINDS),
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        result = []
        for row in latest.values():
            body = json.loads(row["body_json"])
            if str(viewer.user_id) in (row["owner_id"], row["subject_id"], str(body["handler"])):
                result.append(self._get(c, viewer, row["id"]))
        return result

    def _save(
        self, c: Connection, row: dict[str, Any], source: str, body: dict[str, Any], *, done: bool
    ) -> None:
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
                state="resolved" if done else "pending",
                event_id=source,
                body_json=json.dumps(body, sort_keys=True),
            )
        )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        operation: str,
        payload: dict[str, Any],
        apply: Callable[[Connection, dict[str, Any], GameState, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy")
            row = self._row(c, identity)
            self._source(c, row, writing=True)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("Only the actual inquiry decision owner can submit it.")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row = self._row(c, identity)
            if row["revision"] != revision or row["state"] == "resolved":
                raise WorkflowError("STALE_PRIVACY_TROUBLE: reopen the original consequence.")
            state, body = self._source(c, row, writing=True)
            return apply(c, row, state, body)

        return self.store._write(
            viewer,
            key,
            "m3.privacy_" + operation,
            dict(id=identity, revision=revision, **payload),
            change,
            authorize=access,
            auto_audit=False,
        )

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        route: Literal["inquiry", "punishment"],
        *,
        question: str = "",
        method: str = "",
        report: str = "",
        evidence: Literal["known", "unknown"] = "unknown",
    ) -> dict[str, Any]:
        def apply(
            c: Connection, row: dict[str, Any], state: GameState, body: dict[str, Any]
        ) -> dict[str, Any]:
            HandlerService(self.store).authorize(c, viewer)
            if row["kind"] != "privacy_trouble" or body.get("route"):
                raise WorkflowError(
                    "Resume the original actual consequence instead of replacing it."
                )
            source, child = str(uuid4()), str(uuid4())
            if route == "punishment":
                if body.get("source_actor") is None or question or method or report:
                    raise WorkflowError(
                        "Only a living original Girl can receive this chosen discipline."
                    )
                event = self.game.event(
                    c, viewer.user_id, key, "m3.privacy_discipline_required", work_id=identity
                )
                related(
                    c,
                    self.store,
                    row,
                    child,
                    viewer.user_id,
                    int(row["subject_id"]),
                    "punishment",
                    dict(
                        reason="privacy_death",
                        immediate=True,
                        source_pdf=16,
                        source_work=identity,
                        source_actor=body["source_actor"],
                        source_career=body["source_career"],
                        ended_actor=body["ended_actor"],
                    ),
                    event,
                )
                self._save(c, row, event, body | dict(route=route, child=child), done=True)
                return dict(id=identity, child=child, state="actual_punishment_pending")
            if (
                route != "inquiry"
                or not question.strip()
                or not method.strip()
                or any(len(x) > 1200 for x in (question, method, report))
            ):
                raise WorkflowError(
                    "Describe the actual inquiry question and method in bounded text."
                )
            has_survivor = body.get("source_actor") is not None
            if has_survivor and report:
                raise WorkflowError(
                    "The original surviving Girl supplies her own answer or refusal."
                )
            if not has_survivor and (not report.strip() or evidence not in ("known", "unknown")):
                raise WorkflowError(
                    "Record a concrete actual report and explicit known/unknown evidence."
                )
            state.facts.append(
                dict(
                    kind="privacy_inquiry",
                    work=identity,
                    handler=str(viewer.user_id),
                    question=question.strip(),
                    method=method.strip(),
                    report=report.strip(),
                    evidence=evidence,
                    source_event=source,
                )
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.privacy_inquiry_opened",
                state,
                event_id=source,
                work_id=identity,
            )
            if has_survivor:
                related(
                    c,
                    self.store,
                    row,
                    child,
                    int(row["subject_id"]),
                    int(row["subject_id"]),
                    "privacy_inquiry_response",
                    body
                    | dict(source_work=identity, question=question.strip(), method=method.strip()),
                    event,
                )
            self._save(
                c,
                row,
                event,
                body
                | dict(
                    route=route,
                    child=child if has_survivor else None,
                    question=question.strip(),
                    method=method.strip(),
                    report=report.strip(),
                    evidence=evidence,
                ),
                done=not has_survivor,
            )
            return dict(
                id=identity,
                child=child if has_survivor else None,
                state="owned_survivor_response_pending"
                if has_survivor
                else "actual_report_recorded",
            )

        return self._write(
            viewer,
            key,
            identity,
            revision,
            "trouble_choice",
            dict(
                route=route,
                question=question,
                method=method,
                report=report,
                evidence=evidence,
            ),
            apply,
        )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        disclose: bool,
        account: str,
    ) -> dict[str, Any]:
        def apply(
            c: Connection, row: dict[str, Any], state: GameState, body: dict[str, Any]
        ) -> dict[str, Any]:
            if (
                row["kind"] != "privacy_inquiry_response"
                or type(disclose) is not bool
                or len(account) > 1200
            ):
                raise WorkflowError("Supply only your actual owned answer or refusal.")
            if disclose and not account.strip():
                raise WorkflowError(
                    "Write the actual response you choose to share with the Handler."
                )
            root = self._row(c, body["source_work"])
            source = str(uuid4())
            state.facts.append(
                dict(
                    kind="privacy_inquiry_response",
                    work=identity,
                    actor=ActorRef.model_validate_json(
                        json.dumps(body["source_actor"])
                    ).model_dump_json(),
                    disclosed=str(disclose),
                    statement=account.strip(),
                    source_event=source,
                )
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.privacy_inquiry_answered",
                state,
                event_id=source,
                work_id=identity,
            )
            self._save(
                c, row, event, body | dict(response=account.strip(), disclosed=disclose), done=True
            )
            self._save(
                c,
                root,
                event,
                json.loads(root["body_json"]) | dict(response=account.strip(), disclosed=disclose),
                done=True,
            )
            return dict(id=identity, state="actual_owned_response_recorded", disclosed=disclose)

        return self._write(
            viewer,
            key,
            identity,
            revision,
            "inquiry_response",
            dict(
                disclose=disclose,
                account=account,
            ),
            apply,
        )
