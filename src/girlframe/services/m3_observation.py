"""Actual Observation orders, separate human selections and typed saved consequences."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_observation as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_observation_state import Details, Kind
from girlframe.engine.m3_off_duty import Period, clone
from girlframe.services.m2_state import load_state
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def work_id(period: str, subject: int, actor: int) -> str:
    return period + ":observation-choices:" + str(subject) + ":" + str(actor)


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    table = t.m3["m3_required_work"]
    for uid, progress in period.progress.items():
        if (
            progress.observation is None
            or progress.roll is None
            or progress.roll.stage != "choices"
        ):
            continue
        for actor in (int(uid), period.handler):
            try:
                _, count = rules.choices(period, int(uid), actor)
            except ValueError:
                continue
            identity = work_id(period.id, int(uid), actor)
            if count == 0 or c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == store.campaign_id, table.c.id == identity
                )
            ):
                continue
            related(
                c,
                store,
                {"campaign_id": store.campaign_id, "off_duty_id": period.id},
                identity,
                actor,
                int(uid),
                "observation_choice",
                {
                    "source_pdf": 28,
                    "count": count,
                    "due_stage": "active",
                    "observation_source": progress.observation.source_event,
                },
                event,
            )


def settle(period: Period, state: GameState) -> None:
    for uid, progress in period.progress.items():
        if progress.observation is None or not rules.complete(period, int(uid)):
            continue
        for debt in state.obligations:
            if (
                debt.id in progress.observation.obligations
                and debt.owner == int(uid)
                and debt.kind == "void_observation"
            ):
                debt.state = "fulfilled"


def discipline_applied(
    period: Period, state: GameState, subject: int, identity: str, event: str
) -> Period:
    selected = rules.outcome(period, subject, identity)
    if selected.kind != "moderate_punishment":
        raise WorkflowError("This discipline does not match its actual Observation consequence.")
    updated = clone(period)
    saved = rules.outcome(updated, subject, identity)
    saved.resolved, saved.source_event = True, event
    updated.revision += 1
    settle(updated, state)
    return updated


Result = tuple[Period, GameState, list[dict[str, Any]], list[dict[str, Any]]]


class ObservationService:
    def __init__(self, periods: OffDutyService):
        self.periods, self.missions, self.game, self.store = (
            periods,
            periods.missions,
            periods.game,
            periods.store,
        )
        self.cycle = CycleService(periods)

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
        if row is None or row["kind"] not in ("observation_choice", "observation_effect"):
            raise WorkflowError("Resume an actual saved Observation task.")
        return dict(row)

    def _change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        kind: str,
        payload: dict[str, Any],
        change: Callable[[Connection, Period, GameState, str], Result],
        *,
        role_work: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            period, state = self.cycle._current(
                c, viewer, identity, game_revision, invited_observation=role_work
            )
            if period.revision != expected or period.phase == "complete":
                raise WorkflowError("STALE_OBSERVATION: reopen the current period.")
            event = str(uuid4())
            updated, canon, resolved, additions = change(c, period, state, event)
            settle(updated, canon)
            self.game.event(c, viewer.user_id, key, kind, canon, event_id=event, period_id=identity)
            self.periods._save(c, updated, event)
            self.cycle._resolve(c, resolved, event, {"source_pdf": 28, "applied_event": event})
            for item in additions:
                if "update_row" in item:
                    self._save_work(
                        c, item["update_row"], event, body=item["body"], **item["values"]
                    )
                    continue
                related(
                    c,
                    self.store,
                    {"campaign_id": self.store.campaign_id, "off_duty_id": identity},
                    item["id"],
                    item["owner"],
                    item["subject"],
                    item["kind"],
                    item["body"],
                    event,
                )
            synchronize(c, self.store, updated, event)
            awaiting_human = False
            if payload.get("work"):
                saved = self._row(c, payload["work"])
                awaiting_human = (
                    saved["state"] == "pending"
                    and json.loads(saved["body_json"]).get("mode") == "npc_response"
                )
            return {
                "id": identity,
                "revision": updated.revision,
                "phase": updated.phase,
                "awaiting_human": awaiting_human,
            }

        return self.missions._write(
            viewer,
            key,
            kind,
            {"id": identity, "expected": expected, "game_revision": game_revision, **payload},
            operation,
            lambda c: self.missions.access.authorize(c, viewer, "plays"),
        )

    def order(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        subject: int,
        suspects_hiding: bool,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection, period: Period, state: GameState, event: str) -> Result:
            self.missions._handler(c, viewer)
            updated, canon = rules.order(
                period, expected, viewer.user_id, subject, state, suspects_hiding, account, event
            )
            # The private account stays in period work/history, not public event metadata.
            observation = rules.context(updated, subject)[1]
            for debt in canon.obligations:
                if debt.id in observation.obligations:
                    debt.details.setdefault("account", account.strip())
            return updated, canon, [], []

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.observation_ordered",
            {"subject": subject, "suspects_hiding": suspects_hiding, "account": account},
            change,
        )

    def suspicion(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        subject: int,
        suspected: bool,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection, period: Period, state: GameState, event: str) -> Result:
            self.missions._handler(c, viewer)
            if not account.strip() or len(account) > 1200:
                raise WorkflowError("Record your actual hiding-suspicion review.")
            updated = rules.review_hiding(
                period, expected, viewer.user_id, subject, suspected, event
            )
            for debt in state.obligations:
                if debt.id in rules.context(updated, subject)[1].obligations:
                    debt.details["hiding_review"] = account.strip()
            return updated, state, [], []

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.observation_hiding_reviewed",
            {"subject": subject, "suspected": suspected, "account": account},
            change,
        )

    def select(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        subject: int,
        values: tuple[Kind, ...],
    ) -> dict[str, Any]:
        def change(c: Connection, period: Period, state: GameState, event: str) -> Result:
            row = self._row(c, work_id(identity, subject, viewer.user_id))
            if (
                row["kind"] != "observation_choice"
                or row["state"] != "pending"
                or row["owner_id"] != str(viewer.user_id)
            ):
                raise WorkflowError("Only the saved choice owner answers this Observation request.")
            updated = rules.choose(period, expected, viewer.user_id, subject, values, event)
            for value in values:
                if value in ("remove_girl_void_asset", "remove_frame_void_asset"):
                    family = "girl" if value == "remove_girl_void_asset" else "frame"
                    if not any(
                        x.void and x.family == family for x in state.sheets[str(subject)].assets
                    ):
                        raise WorkflowError(
                            "Choose a consequence with an actual current Void Asset."
                        )
            _, observation = rules.context(updated, subject)
            old = {x.id for x in rules.context(period, subject)[1].outcomes}
            additions = []
            for outcome in observation.outcomes:
                if outcome.id in old:
                    continue
                owner = (
                    subject
                    if outcome.kind == "reprogram"
                    else period.handler
                    if outcome.kind
                    in (
                        "public_display_tag",
                        "assigned_observer",
                        "medical_probing",
                        "hospital_stay",
                        "director_or_rival_arrives",
                        "moderate_punishment",
                    )
                    else outcome.chooser
                )
                additions.append(
                    {
                        "id": outcome.id,
                        "owner": owner,
                        "subject": subject,
                        "kind": "punishment"
                        if outcome.kind == "moderate_punishment"
                        else "observation_effect",
                        "body": {
                            "reason": "void_observation",
                            "source_pdf": 28,
                            "required_severity": "moderate",
                            "origin_outcome": outcome.id,
                            "consequence": outcome.kind,
                            "due_stage": "active",
                        },
                    }
                )
            return updated, state, [row], additions

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.observation_choices_saved",
            {"subject": subject, "values": values},
            change,
        )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        period_revision: int,
        game_revision: int,
        details: Details,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._row(c, identity)
            period_id = row["off_duty_id"]

        def change(c: Connection, period: Period, state: GameState, event: str) -> Result:
            row = self._row(c, identity)
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or row["kind"] != "observation_effect"
                or row["owner_id"] != str(viewer.user_id)
            ):
                raise WorkflowError(
                    "STALE_OBSERVATION: only the actual detail owner may apply this outcome."
                )
            subject = int(row["subject_id"])
            selected = rules.outcome(period, subject, identity)
            body = json.loads(row["body_json"])
            if body.get("mode") == "npc_response":
                raise WorkflowError(
                    "Answer the saved NPC role question; do not replace the Handler's proposal."
                )
            if selected.kind in ("assigned_observer", "director_or_rival_arrives"):
                self.missions.access.authorize(c, viewer, "world")
                npc = (
                    next((x for x in state.world.npcs if x.id == details.npc), None)
                    if state.world
                    else None
                )
                if (
                    npc is None
                    or not npc.alive
                    or npc.captive_of is not None
                    or ("director" in npc.jobs and npc.controller == period.handler)
                ):
                    raise WorkflowError(
                        "Select an actual available NPC with the correct human controller."
                    )
                jobs = (
                    {"handler", "guard"}
                    if selected.kind == "assigned_observer"
                    else {"handler", "director"}
                )
                if not set(npc.jobs) & jobs or not (
                    npc.revealed or npc.controller == viewer.user_id or "director" in npc.jobs
                ):
                    raise WorkflowError("Select a known actual NPC of the required role.")
                if npc.controller != viewer.user_id:
                    from girlframe.services.handler_setup import HandlerService

                    if not HandlerService(self.store)._member(c, npc.controller):
                        raise WorkflowError(
                            "The NPC's actual human controller must still be a member."
                        )
                    updated = clone(period)
                    updated.revision += 1
                    proposed = body | {
                        "mode": "npc_response",
                        "proposal": details.model_dump(mode="json"),
                        "proposing_handler": period.handler,
                    }
                    return (
                        updated,
                        state,
                        [],
                        [
                            {
                                "update_row": row,
                                "body": proposed,
                                "values": {"owner_id": str(npc.controller)},
                            }
                        ],
                    )
            policy = self.store.policy.owner_m3_rulings
            updated, canon = rules.apply(
                period,
                period_revision,
                state,
                viewer.user_id,
                subject,
                identity,
                details,
                event,
                allow_duplicate_labels=bool(
                    policy and policy.identity_duplicate_labels == "distinct_ids"
                ),
            )
            return updated, canon, [row], []

        return self._change(
            viewer,
            key,
            period_id,
            period_revision,
            game_revision,
            "m3.observation_consequence_reviewed",
            {"work": identity, "revision": revision, "details": details.model_dump(mode="json")},
            change,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                raise WorkflowError("This Observation request belongs to other participants.")
            period = self.periods._get(c, row["off_duty_id"])
            state = load_state(c, self.store.campaign_id)
            subject = int(row["subject_id"])
            result = {
                k: row[k] for k in ("id", "owner_id", "subject_id", "kind", "state", "revision")
            }
            result.update(
                period_id=period.id, period_revision=period.revision, game_revision=state.revision
            )
            if row["state"] != "pending" or row["owner_id"] != str(viewer.user_id):
                return result
            if row["kind"] == "observation_choice":
                options, count = rules.choices(period, subject, viewer.user_id)
                sheet = state.sheets[str(subject)]
                options = tuple(
                    x
                    for x in options
                    if x not in ("remove_girl_void_asset", "remove_frame_void_asset")
                    or any(
                        a.void
                        and a.family == ("girl" if x == "remove_girl_void_asset" else "frame")
                        for a in sheet.assets
                    )
                )
                result.update(options=options, count=count)
            else:
                selected = rules.outcome(period, subject, identity)
                sheet = state.sheets[str(subject)]
                result["consequence"] = selected.kind
                body = json.loads(row["body_json"])
                if body.get("mode") == "npc_response":
                    npc = (
                        next((x for x in state.world.npcs if x.id == body["proposal"]["npc"]), None)
                        if state.world
                        else None
                    )
                    result.update(
                        response_required=True,
                        npc_name=npc.name if npc else "Unavailable NPC",
                        proposal_account=body["proposal"]["account"],
                    )
                    return result
                if selected.kind in ("remove_girl_void_asset", "remove_frame_void_asset"):
                    family = "girl" if selected.kind == "remove_girl_void_asset" else "frame"
                    result["assets"] = tuple(
                        (x.id, x.name) for x in sheet.assets if x.void and x.family == family
                    )
                if selected.kind == "reprogram":
                    result["identities"] = tuple(
                        x.model_dump(mode="json") for x in sheet.identities
                    )
                    from girlframe.engine.creation_catalog import CATALOG

                    result["starting_identities"] = CATALOG[sheet.girl]["identities"]
                if selected.kind in ("assigned_observer", "director_or_rival_arrives"):
                    jobs = (
                        {"handler", "guard"}
                        if selected.kind == "assigned_observer"
                        else {"handler", "director"}
                    )
                    result["npcs"] = (
                        tuple(
                            (x.id, x.name)
                            for x in state.world.npcs
                            if x.alive
                            and x.captive_of is None
                            and (
                                x.revealed or x.controller == viewer.user_id or "director" in x.jobs
                            )
                            and set(x.jobs) & jobs
                            and ("director" not in x.jobs or x.controller != period.handler)
                        )
                        if state.world
                        else ()
                    )
            return result

    def _save_work(
        self, c: Connection, row: dict[str, Any], event: str, *, body: dict[str, Any], **values: Any
    ) -> None:
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

    def answer_npc(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        period_revision: int,
        game_revision: int,
        accepted: bool,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            period_id = self._row(c, identity)["off_duty_id"]

        def change(c: Connection, period: Period, state: GameState, event: str) -> Result:
            self.missions.access.authorize(c, viewer, "world")
            row = self._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                type(accepted) is not bool
                or row["state"] != "pending"
                or row["revision"] != revision
                or row["owner_id"] != str(viewer.user_id)
                or body.get("mode") != "npc_response"
                or body.get("proposing_handler") != period.handler
            ):
                raise WorkflowError(
                    "Only the actual saved NPC-response owner may answer this current proposal."
                )
            details = Details.model_validate_json(json.dumps(body["proposal"]))
            npc = (
                next((x for x in state.world.npcs if x.id == details.npc), None)
                if state.world
                else None
            )
            if npc is None or npc.controller != viewer.user_id:
                raise WorkflowError("Recover the changed NPC controller before this old response.")
            if not accepted:
                updated = clone(period)
                updated.revision += 1
                for field in ("mode", "proposal", "proposing_handler"):
                    body.pop(field, None)
                body["declined_role_event"] = event
                return (
                    updated,
                    state,
                    [],
                    [
                        {
                            "update_row": row,
                            "body": body,
                            "values": {"owner_id": str(period.handler)},
                        }
                    ],
                )
            policy = self.store.policy.owner_m3_rulings
            updated, canon = rules.apply(
                period,
                period_revision,
                state,
                period.handler,
                int(row["subject_id"]),
                identity,
                details,
                event,
                allow_duplicate_labels=bool(
                    policy and policy.identity_duplicate_labels == "distinct_ids"
                ),
                npc_confirmed_by=viewer.user_id,
            )
            additions = []
            if "director" in npc.jobs:
                additions.append(
                    {
                        "id": identity + ":director-presence",
                        "owner": period.handler,
                        "subject": period.handler,
                        "kind": "director_presence",
                        "body": {
                            "source_pdf": 192,
                            "npc": npc.id,
                            "controller": npc.controller,
                            "origin_outcome": identity,
                            "immediate": True,
                            "due_stage": "active",
                        },
                    }
                )
            return updated, canon, [row], additions

        return self._change(
            viewer,
            key,
            period_id,
            period_revision,
            game_revision,
            "m3.observation_npc_answered",
            {"work": identity, "revision": revision, "accepted": accepted},
            change,
            role_work=identity,
        )
