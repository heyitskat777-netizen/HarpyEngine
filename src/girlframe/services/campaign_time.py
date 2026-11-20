"""Offline Handler commands and the audience-filtered campaign timeline."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.scenes.campaign_time import SLOTS, Anchor, Cut, Dependency, LateSubmission, ScenePlan
from girlframe.services import campaign_time_history as ledger
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_gorgon_dormant import require_clear as require_gorgon_costs_clear
from girlframe.services.m3_medical import KIND as MEDICAL_WORK
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_quadrant_loss import require_aftermath_clear
from girlframe.services.mission_timing_history import active as active_timing
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@dataclass
class ScheduledScene:
    id: str
    channel: int
    chapter: str
    plan: ScenePlan
    row: dict[str, Any] | None
    scheduled_receipt: str
    sealed_by: str | None = None
    sealed_participants: tuple[int, ...] = ()
    late_closed: bool = False
    entries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def joined(self) -> tuple[int, ...]:
        if self.sealed_by:
            return self.sealed_participants
        return tuple(json.loads(self.row["participants_json"])) if self.row else ()


class CampaignTimeService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.missions = MissionService(store)
        self.game = self.missions.game

    def _handler(self, c: Connection, viewer: GuildViewer) -> None:
        self.missions.access.authorize(c, viewer, "missions")
        self.missions._handler(c, viewer)

    def _current(self, c: Connection) -> tuple[str, Anchor]:
        result = ledger.anchor(c, self.store.campaign_id)
        if result is None:
            raise WorkflowError("Initialize this campaign's fictional calendar first.")
        return result

    def _event(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        kind: str,
        body: dict[str, Any],
        *,
        event_id: str | None = None,
    ) -> str:
        return self.store._audit(
            c, viewer.user_id, key, kind, body, event_id=event_id, ruleset_version="timeline-v1"
        )

    def initialize(self, viewer: GuildViewer, key: str, anchor: Anchor) -> dict[str, Any]:
        anchor = Anchor.model_validate_json(anchor.model_dump_json())
        payload = {"anchor": anchor.model_dump(mode="json")}

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            if ledger.anchor(c, self.store.campaign_id):
                raise WorkflowError("The fictional calendar is already initialized.")
            return payload | {"receipt": self._event(c, viewer, key, ledger.INITIALIZED, payload)}

        return self.store._write(
            viewer,
            key,
            ledger.INITIALIZED,
            payload,
            operation,
            auto_audit=False,
            authorize=lambda c: self._handler(c, viewer),
        )

    def _scene_rows(self, c: Connection) -> dict[str, dict[str, Any]]:
        table = t.m2["m2_scenes"]
        return {
            row["id"]: dict(row)
            for row in c.execute(
                sa.select(table).where(table.c.campaign_id == self.store.campaign_id)
            ).mappings()
        }

    def _scenes(self, c: Connection, rows: dict[str, dict[str, Any]]) -> dict[str, ScheduledScene]:
        scenes: dict[str, ScheduledScene] = {}
        for row, data in ledger.history(
            c,
            self.store.campaign_id,
            ledger.SCHEDULED,
            ledger.CUT,
            ledger.LATE_ENTRY,
            ledger.LATE_CLOSED,
        ):
            if row["kind"] == ledger.CUT:
                for item in data["late_scenes"]:
                    scene = scenes[item["scene"]]
                    scene.sealed_by = row["id"]
                    scene.sealed_participants = tuple(item["participants"])
            elif row["kind"] == ledger.SCHEDULED:
                scene_id = data["scene"]
                scenes[scene_id] = ScheduledScene(
                    scene_id,
                    data["channel"],
                    data["chapter"],
                    ScenePlan.model_validate_json(json.dumps(data["plan"])),
                    rows.get(scene_id),
                    row["id"],
                )
            elif row["kind"] == ledger.LATE_ENTRY:
                scenes[data["scene"]].entries.append(
                    data | {"id": row["id"], "author": int(row["actor_id"])}
                )
            else:
                scenes[data["scene"]].late_closed = True
        return scenes

    def schedule(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        scene_id: str,
        expected_scene_revision: int,
        expected_anchor: str,
        plan: ScenePlan,
    ) -> dict[str, Any]:
        plan = ScenePlan.model_validate_json(plan.model_dump_json())
        payload = {
            "channel": channel,
            "scene": scene_id,
            "expected_scene_revision": expected_scene_revision,
            "expected_anchor": expected_anchor,
            "plan": plan.model_dump(mode="json"),
        }

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            receipt, current = self._current(c)
            row = self.game.scene(c, channel, check_slot=False)
            if receipt != expected_anchor or (row["id"], row["revision"]) != (
                scene_id,
                expected_scene_revision,
            ):
                raise WorkflowError("STALE_SCENE: refresh the calendar and exact scene binding.")
            if plan.start.order < current.position.order:
                raise WorkflowError("Schedule this scene at the current or a future slot.")
            state = load_state(c, self.store.campaign_id)
            active = set(state.order) | {viewer.user_id}
            if any(
                uid not in active or not HandlerService(self.store)._member(c, uid)
                for uid in plan.participants
            ):
                raise WorkflowError("Schedule current campaign Pilots or the appointed Handler.")
            joined_pilots = set(row["participants"]) - {viewer.user_id}
            if not joined_pilots.issubset(plan.participants):
                raise WorkflowError("Include the Pilots already joined to this scene.")
            scenes = self._scenes(c, self._scene_rows(c))
            old = scenes.get(scene_id)
            if plan.narrative_only or (old and old.plan.narrative_only):
                raise WorkflowError("The Session Zero opening owns this roleplay scene.")
            if old and (old.plan.start, old.plan.end) != (plan.start, plan.end):
                clock = active_timing(c, self.store.campaign_id)
                if clock is not None and clock.scene == scene_id:
                    raise WorkflowError("Finish the active timed sequence before moving its scene.")
                actions = t.m2["m2_actions"]
                if c.scalar(
                    sa.select(actions.c.id)
                    .where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.scene_id == scene_id,
                    )
                    .limit(1)
                ):
                    raise WorkflowError("A recorded Play fixes its scene's scheduled span.")
            pilots = set(plan.participants) - {viewer.user_id}
            if any(
                scene.plan.overlaps(plan) and pilots.intersection(scene.plan.participants)
                for scene in scenes.values()
                if scene.id != scene_id
            ):
                raise WorkflowError("A Pilot has an overlapping scheduled commitment.")
            body = {
                "scene": scene_id,
                "channel": channel,
                "chapter": plan.chapter or current.chapter,
                "plan": payload["plan"],
            }
            event = self._event(c, viewer, key, ledger.SCHEDULED, body)
            # The existing scene form revision also fences concurrent rescheduling.
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == scene_id,
                )
                .values(revision=table.c.revision + 1)
            )
            return body | {"receipt": event, "scene_revision": expected_scene_revision + 1}

        return self.store._write(
            viewer,
            key,
            ledger.SCHEDULED,
            payload,
            operation,
            auto_audit=False,
            authorize=lambda c: self._handler(c, viewer),
        )

    def _work(self, c: Connection) -> dict[str, dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return {
            row["id"]: dict(row)
            for row in c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id)
                .order_by(table.c.revision)
            ).mappings()
        }

    def _phase(self, c: Connection) -> list[dict[str, Any]]:
        result = []
        for kind, name, final in (
            ("mission", "m3_missions", ("complete", "cancelled")),
            ("off_duty", "m3_off_duty", ("complete",)),
        ):
            table = t.m3[name]
            for row in c.execute(
                sa.select(table.c.id, table.c.phase, table.c.revision)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.phase.not_in(final))
                .order_by(table.c.id)
            ).mappings():
                result.append({"kind": kind, **dict(row)})
        return result

    def _dependency(
        self, c: Connection, work: dict[str, dict[str, Any]], dependency: Dependency
    ) -> tuple[bool, str]:
        if dependency.kind == "work":
            item = work.get(dependency.id)
            if item is None:
                raise WorkflowError("A required outcome is unavailable in this campaign.")
            return item["state"] == "resolved", item["event_id"]

        actions = t.m2["m2_actions"]
        if dependency.kind == "choice":
            choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
            row = c.execute(
                sa.select(choices.c.state, responses.c.event_id, actions.c.state)
                .select_from(
                    choices.join(
                        actions,
                        sa.and_(
                            actions.c.campaign_id == choices.c.campaign_id,
                            actions.c.id == choices.c.action_id,
                        ),
                    ).outerjoin(
                        responses,
                        sa.and_(
                            responses.c.campaign_id == choices.c.campaign_id,
                            responses.c.choice_id == choices.c.id,
                        ),
                    )
                )
                .where(
                    choices.c.campaign_id == self.store.campaign_id, choices.c.id == dependency.id
                )
            ).first()
            if row is None:
                raise WorkflowError("A required outcome is unavailable in this campaign.")
            choice_state, event, action_state = row
            return choice_state == "answered" and bool(event) and action_state == "complete", (
                event or choice_state
            )

        receipts = t.m2["m2_receipts"]
        status = c.scalar(
            sa.select(actions.c.state)
            .select_from(
                receipts.join(
                    actions,
                    sa.and_(
                        actions.c.campaign_id == receipts.c.campaign_id,
                        actions.c.id == receipts.c.action_id,
                    ),
                )
            )
            .where(
                receipts.c.campaign_id == self.store.campaign_id,
                receipts.c.id == dependency.id,
            )
        )
        if status is None:
            raise WorkflowError("A required outcome is unavailable in this campaign.")
        return status == "complete", dependency.id

    def _preview(
        self, c: Connection, viewer: GuildViewer, cut: Cut
    ) -> tuple[dict[str, Any], list[ScheduledScene]]:
        receipt, current = self._current(c)
        target = cut.target.position.order
        if target <= current.position.order:
            raise WorkflowError("A chapter cut must move the fictional calendar forward.")
        phase, work = self._phase(c), self._work(c)
        rows = self._scene_rows(c)
        scenes = self._scenes(c, rows)
        state = load_state(c, self.store.campaign_id)
        dependencies = [self._dependency(c, work, item) for item in cut.requires]
        blockers = [
            x.model_dump(mode="json")
            for x, result in zip(cut.requires, dependencies, strict=True)
            if not result[0]
        ]
        clock = active_timing(c, self.store.campaign_id)
        if clock is not None:
            blockers.append({"kind": "timed_sequence_active", "id": clock.id})
        listed_work = {x.id for x in cut.requires if x.kind == "work"}
        for item in sorted(work.values(), key=lambda x: x["id"]):
            scene = scenes.get(item["scene_id"])
            if (
                item["id"] not in listed_work
                and item["state"] != "resolved"
                and (
                    scene is None
                    or scene.plan.start.order < target
                    or json.loads(item["body_json"]).get("immediate")
                )
            ):
                blockers.append({"kind": "work", "id": item["id"]})
        if self.game.pending_actions(c):
            blockers.append({"kind": "play_pending"})
        if any(
            x["phase"] in {"offered", "ending", "awaiting_consequences", "preparing"} for x in phase
        ):
            blockers.append({"kind": "phase_transition_required"})
        if any(x.state == "pending" for x in state.obligations):
            blockers.append({"kind": "play_followup_required"})
        self._progression_blockers(c, state, blockers)

        late = []
        observation = DirectorObservationService(self.store, synthetic=True)
        for scene_id, row in sorted(rows.items()):
            if not row["open"]:
                continue
            scene = scenes.get(scene_id)
            if scene is None:
                blockers.append({"kind": "classify_scene", "id": scene_id})
            elif scene.plan.start.order >= target:
                continue
            elif scene.plan.end.order >= target:
                if not scene.plan.narrative_only:
                    blockers.append({"kind": "cut_inside_scene_span", "id": scene_id})
            elif not scene.plan.allow_late_narration:
                blockers.append({"kind": "finish_or_classify_scene", "id": scene_id})
            elif observation._state(c, scene_id).policy.mode == "shadow":
                blockers.append({"kind": "director_closeout_required", "id": scene_id})
            else:
                try:
                    closure = self.game.scene_close_state(
                        c, row | {"participants": list(scene.joined)}, str(uuid4())
                    )
                except WorkflowError:
                    blockers.append({"kind": "scene_followup_required", "id": scene_id})
                    continue
                if closure is not None:
                    blockers.append({"kind": "scene_has_close_effects", "id": scene_id})
                else:
                    late.append(scene)

        args = cut.model_dump(mode="json")
        fingerprint = {
            "campaign": self.store.campaign_id,
            "actor": viewer.user_id,
            "handler_revision": HandlerService(self.store).current(c)[0],
            "source": receipt,
            "request": args,
            "game_revision": state.revision,
            "phase": phase,
            "dependencies": dependencies,
            "blockers": blockers,
            "scenes": [
                (
                    scene_id,
                    row["open"],
                    row["revision"],
                    scenes[scene_id].scheduled_receipt if scene_id in scenes else None,
                )
                for scene_id, row in sorted(rows.items())
            ],
        }
        token = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
        return (
            {
                "anchor_receipt": receipt,
                "target": args["target"],
                "required": args["requires"],
                "dependency_receipts": [
                    item.model_dump(mode="json") | {"receipt": proof}
                    for item, (resolved, proof) in zip(cut.requires, dependencies, strict=True)
                    if resolved
                ],
                "game_revision": state.revision,
                "token": token,
                "blockers": blockers,
                "late_scenes": [x.id for x in late],
            },
            late,
        )

    def _progression_blockers(
        self, c: Connection, state: GameState, blockers: list[dict[str, Any]]
    ) -> None:
        try:
            self.game.unpaused(c)
        except WorkflowError:
            blockers.append({"kind": "safety_paused"})
        try:
            require_aftermath_clear(state)
        except WorkflowError:
            blockers.append({"kind": "quadrant_aftermath_required"})
        try:
            require_gorgon_costs_clear(self.game, c)
        except WorkflowError:
            blockers.append({"kind": "gorgon_followup_required"})

    def preview_cut(self, viewer: GuildViewer, cut: Cut) -> dict[str, Any]:
        cut = Cut.model_validate_json(cut.model_dump_json())
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._handler(c, viewer)
            return self._preview(c, viewer, cut)[0]

    def _record_cut(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        preview: dict[str, Any],
        late: list[ScheduledScene],
    ) -> dict[str, Any]:
        if preview["blockers"]:
            raise WorkflowError("CUT_BLOCKED: resolve the required work in the preview.")
        for index, scene in enumerate(late, start=1):
            self.game.record_scene_close(
                c,
                viewer.user_id,
                key,
                {"id": scene.id, "channel_id": str(scene.channel)},
                str(uuid4()),
                apply_effects=False,
                event_index=index,
            )
        body = {
            "anchor": preview["target"],
            "previous": preview["anchor_receipt"],
            "required": preview["dependency_receipts"],
            "game_revision": preview["game_revision"],
            "late_scenes": [{"scene": x.id, "participants": list(x.joined)} for x in late],
        }
        event = self._event(c, viewer, key, ledger.CUT, body)
        return {
            "anchor": body["anchor"],
            "receipt": event,
            "late_scenes": preview["late_scenes"],
        }

    def commit_cut(self, viewer: GuildViewer, key: str, cut: Cut, token: str) -> dict[str, Any]:
        cut = Cut.model_validate_json(cut.model_dump_json())
        payload = {"cut": cut.model_dump(mode="json"), "token": token}

        def operation(c: Connection) -> dict[str, Any]:
            preview, late = self._preview(c, viewer, cut)
            if token != preview["token"]:
                raise WorkflowError(
                    "STALE_CUT: review a fresh preview of the current dependencies."
                )
            return self._record_cut(c, viewer, key, preview, late)

        return self.store._write(
            viewer,
            key,
            ledger.CUT,
            payload,
            operation,
            auto_audit=False,
            authorize=lambda c: self._handler(c, viewer),
        )

    def _late_scene(self, c: Connection, scene_id: str, expected_cut: str) -> ScheduledScene:
        scene = self._scenes(c, self._scene_rows(c)).get(scene_id)
        if scene is None or not scene.sealed_by or scene.late_closed:
            raise WorkflowError("This late scene is unavailable.")
        if expected_cut != scene.sealed_by:
            raise WorkflowError("STALE_SCENE: refresh the exact late scene.")
        return scene

    def record_late(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        expected_cut: str,
        submission: LateSubmission,
    ) -> dict[str, Any]:
        submission = LateSubmission.model_validate_json(submission.model_dump_json())
        review = submission.kind in ("mechanical", "uncertain")
        payload = {
            "scene": scene_id,
            "expected_cut": expected_cut,
            "submission": submission.model_dump(mode="json"),
        }

        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "missions")
            if not review:
                self.missions._handler(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            scene = self._late_scene(c, scene_id, expected_cut)
            handler = HandlerService(self.store).current(c)[1].handler_id
            if viewer.user_id != handler and viewer.user_id not in scene.joined:
                raise WorkflowError("This late scene is unavailable.")
            if review:
                audience = {viewer.user_id}
                if handler is not None:
                    audience.add(handler)
            elif submission.kind == "knowledge":
                audience = set(submission.recipients)
            else:
                audience = set(scene.joined)
            if submission.kind == "knowledge" and (
                not audience.issubset(scene.joined)
                or any(not HandlerService(self.store)._member(c, uid) for uid in audience)
            ):
                raise WorkflowError("Choose actual participants as recipients.")
            body = {
                "scene": scene_id,
                "kind": submission.kind,
                "account": submission.account,
                "audience": sorted(audience),
                "status": "handler_review" if review else "recorded",
            }
            event = self._event(c, viewer, key, ledger.LATE_ENTRY, body)
            return {"id": event, "scene": scene_id, "status": body["status"]}

        return self.store._write(
            viewer,
            key,
            ledger.LATE_ENTRY,
            payload,
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def close_late(
        self, viewer: GuildViewer, key: str, scene_id: str, expected_cut: str
    ) -> dict[str, Any]:
        payload = {"scene": scene_id, "expected_cut": expected_cut}

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._late_scene(c, scene_id, expected_cut)
            return {
                "scene": scene_id,
                "receipt": self._event(c, viewer, key, ledger.LATE_CLOSED, {"scene": scene_id}),
            }

        return self.store._write(
            viewer,
            key,
            ledger.LATE_CLOSED,
            payload,
            operation,
            auto_audit=False,
            authorize=lambda c: self._handler(c, viewer),
        )

    def projection(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            return self._projection(c, viewer)

    def _projection(self, c: Connection, viewer: GuildViewer) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        current = ledger.anchor(c, self.store.campaign_id)
        if current is None:
            return {"version": 1, "mode": "legacy"}
        receipt, anchor = current
        phase = self._phase(c)
        appointed = HandlerService(self.store).current(c)[1].handler_id
        handler = viewer.user_id == appointed == load_state(c, self.store.campaign_id).handler
        rows = self._scene_rows(c)
        scenes = self._scenes(c, rows)
        visible = [
            {
                "id": scene.id,
                "channel": str(scene.channel),
                "chapter": scene.chapter,
                "start": scene.plan.start.model_dump(),
                "end": scene.plan.end.model_dump(),
                "scheduled_participants": [str(uid) for uid in scene.plan.participants],
                "joined": viewer.user_id in scene.joined,
                "narrative_only": scene.plan.narrative_only,
                "status": (
                    ("closed" if scene.late_closed else "late")
                    if scene.sealed_by
                    else ("scheduled" if scene.plan.start.order > anchor.position.order else "open")
                    if scene.row and scene.row["open"]
                    else "closed"
                ),
                "scene_revision": scene.row["revision"] if scene.row and handler else None,
                "late_cut": scene.sealed_by,
                "entries": [
                    {k: x[k] for k in ("id", "kind", "account", "status")}
                    for x in scene.entries
                    if viewer.user_id == x["author"] or viewer.user_id in x["audience"]
                ],
            }
            for scene in sorted(scenes.values(), key=lambda item: (item.plan.start.order, item.id))
            if handler
            or viewer.user_id in scene.plan.participants
            or viewer.user_id in scene.joined
        ]
        followups = [
            {"route": "play_choice", "id": row["id"], "revision": row["revision"]}
            for row in self.game.pending_choices(c, viewer)
        ]
        followups.extend(
            {"route": "required_work", "id": row["id"], "revision": row["revision"]}
            for row in self._work(c).values()
            if (
                row["owner_id"] == str(viewer.user_id)
                and row["state"] != "resolved"
                and row["kind"] != MEDICAL_WORK
            )
        )
        followups.extend(
            {"route": "medical", "id": item["id"], "revision": item["revision"]}
            for item in MedicalService(self.store)._tasks(c, viewer)
            if item["actionable"]
        )
        result = {
            "version": 1,
            "mode": "asynchronous",
            "anchor": anchor.model_dump(mode="json"),
            "anchor_receipt": receipt,
            "slots": list(SLOTS),
            "cadre_phase": [{"kind": x["kind"], "phase": x["phase"]} for x in phase],
            "scenes": visible,
            "followups": followups,
        }
        from girlframe.services.mission_timing import MissionTimingService

        timing = MissionTimingService(self.store).project(c, viewer)
        if timing is not None:
            result["mission_timing"] = timing
        if handler:
            result["unscheduled_scenes"] = [
                {"id": identity, "channel": row["channel_id"], "revision": row["revision"]}
                for identity, row in rows.items()
                if row["open"] and identity not in scenes
            ]
        return result
