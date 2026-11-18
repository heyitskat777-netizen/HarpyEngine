"""Synthetic-only Activity observation; short transactions, no model or delivery.

Internal worker methods are not browser endpoints. The default service is Off;
only a trusted local synthetic harness may explicitly enable this development slice.
"""

import hashlib
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.observation import (
    AppendSceneInput,
    InputResult,
    Observation,
    ObservationPolicy,
    ObservationStatus,
    ReviewBatch,
    ReviewCompletion,
    SceneObservationState,
    review_eligibility,
)
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class DirectorObservationService:
    def __init__(self, store: OnboardingStore, *, synthetic: bool = False):
        self.store = store
        self.game = GameService(store)
        self.synthetic = synthetic

    def _scope(self) -> None:
        if not self.synthetic:
            raise WorkflowError("SYNTHETIC_ONLY: real conversation observation is not implemented.")

    def _scene(
        self,
        c: Connection,
        scene_id: str,
        viewer: GuildViewer | None = None,
        *,
        allow_closed: bool = False,
    ) -> dict[str, Any]:
        if not self.store._binding_matches(c):
            raise WorkflowError("SCENE_UNAVAILABLE: campaign binding is unavailable.")
        if viewer is not None:
            self.game.authorize(c, viewer, game=False)
        table = t.m2["m2_scenes"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == scene_id,
                    sa.true() if allow_closed else table.c.open.is_(True),
                )
            )
            .mappings()
            .first()
        )
        context = (
            c.execute(
                sa.select(t.m3["m3_scene_contexts"]).where(
                    t.m3["m3_scene_contexts"].c.campaign_id == self.store.campaign_id,
                    t.m3["m3_scene_contexts"].c.id == scene_id,
                )
            )
            .mappings()
            .first()
        )
        if not row or not context or row["channel_id"] != context["channel_id"]:
            raise WorkflowError("SCENE_UNAVAILABLE: use the actual open bound scene.")
        scene = dict(row) | {
            "participants": json.loads(row["participants_json"]),
            "binding_event": context["binding_event"],
        }
        if viewer is not None and viewer.user_id not in scene["participants"]:
            raise WorkflowError("SCENE_UNAVAILABLE: join this scene before accessing observations.")
        return scene

    def _state(self, c: Connection, scene_id: str) -> SceneObservationState:
        table = t.director["state"]
        body = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene_id,
            )
        )
        return SceneObservationState.model_validate_json(body) if body else SceneObservationState()

    def _save(self, c: Connection, scene_id: str, state: SceneObservationState) -> None:
        table = t.director["state"]
        where = (table.c.campaign_id == self.store.campaign_id, table.c.scene_id == scene_id)
        if c.execute(sa.select(table.c.scene_id).where(*where)).first():
            c.execute(table.update().where(*where).values(body_json=state.model_dump_json()))
        else:
            c.execute(
                table.insert().values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    body_json=state.model_dump_json(),
                )
            )

    def _consented(
        self, c: Connection, scene: dict[str, Any], state: SceneObservationState
    ) -> bool:
        people = {str(x) for x in scene["participants"]}
        active = set(
            c.scalars(
                sa.select(t.members.c.user_id).where(
                    t.members.c.campaign_id == self.store.campaign_id,
                    t.members.c.active.is_(True),
                    t.members.c.user_id.in_(people),
                )
            )
        )
        return (
            bool(people)
            and people == active
            and all(state.consents.get(uid) == state.policy_revision for uid in people)
            and state.policy_revision > 0
        )

    def _authorize_input(
        self, c: Connection, viewer: GuildViewer, scene_id: str, speaker: str
    ) -> tuple[dict[str, Any], SceneObservationState, ActorRef]:
        self._scope()
        scene = self._scene(c, scene_id, viewer)
        state = self._state(c, scene_id)
        if state.policy.mode != "shadow" or not self._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: current participant consent is required.")
        canon = load_state(c, self.store.campaign_id)
        if speaker == "handler":
            HandlerService(self.store).authorize(c, viewer)
            from girlframe.engine.m3_handler_consequences import active_handler

            ref = active_handler(canon)
            if ref is None or ref.entity != str(viewer.user_id):
                raise WorkflowError("ACTOR_UNAVAILABLE: recover the actual Handler binding.")
        else:
            ref = ActorRef(
                kind="pilot",
                entity=str(viewer.user_id),
                incarnation=self.game.character_binding(
                    c, canon, viewer.user_id, require_current_profile=False
                ),
            )
        try:
            actor = resolve(
                canon, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            cast = next((x for x in canon.scene_casts if x.id == scene_id and x.open), None)
            if cast is not None:
                from girlframe.engine.m3_cast import validate_role

                validate_role(cast, actor)
            if actor.controller != viewer.user_id or not actor.alive:
                raise ValueError("Actor unavailable")
        except ValueError:
            raise WorkflowError("ACTOR_UNAVAILABLE: use your actual current scene role.") from None
        return scene, state, ref

    def configure_scene(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        expected_policy_revision: int,
        policy: ObservationPolicy,
    ) -> dict[str, Any]:
        """Local synthetic configuration only; never grants another person's consent."""
        self._scope()
        policy = ObservationPolicy.model_validate_json(policy.model_dump_json())

        def authorize(c: Connection) -> None:
            self.store.administrator(viewer)
            self._scene(c, scene_id, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, scene_id)
            if state.policy_revision != expected_policy_revision:
                raise WorkflowError("STALE_POLICY: refresh observation settings.")
            state = state.model_copy(
                update={
                    "policy": policy,
                    "policy_revision": state.policy_revision + 1,
                    "consents": {},
                    "consent_generation": state.consent_generation + 1,
                    "generation": state.generation + 1,
                }
            )
            self._save(c, scene_id, state)
            return {
                "scene_id": scene_id,
                "policy_revision": state.policy_revision,
                "mode": policy.mode,
            }

        return self.store._write(
            viewer,
            key,
            "director.policy",
            {"scene_id": scene_id, "policy": policy.model_dump(mode="json")},
            operation,
            authorize=authorize,
        )

    def set_consent(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        expected_policy_revision: int,
        *,
        consent: bool,
    ) -> dict[str, Any]:
        self._scope()

        def authorize(c: Connection) -> None:
            # A former participant can always withdraw use of a closed scene's
            # carried references. Granting new consent still requires an open scene.
            try:
                self._scene(c, scene_id, viewer, allow_closed=consent is False)
            except WorkflowError as error:
                if consent is not False or not str(error).startswith("SCENE_UNAVAILABLE:"):
                    raise
                from girlframe.services.director_closeout import report_participant

                self.game.authorize(c, viewer, game=False)
                if not self.store._binding_matches(c) or not report_participant(
                    self.store, c, scene_id, viewer.user_id
                ):
                    raise

        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, scene_id)
            if state.policy_revision != expected_policy_revision or not state.policy_revision:
                raise WorkflowError("STALE_POLICY: review the current observation notice.")
            if type(consent) is not bool:
                raise WorkflowError("INVALID_CONSENT: choose an explicit boolean decision.")
            state = state.model_copy(
                update={
                    "consents": state.consents
                    | {str(viewer.user_id): state.policy_revision if consent else 0},
                    "consent_generation": state.consent_generation + 1,
                    "generation": state.generation + 1,
                }
            )
            self._save(c, scene_id, state)
            return {
                "scene_id": scene_id,
                "consent": consent,
                "policy_revision": state.policy_revision,
            }

        return self.store._write(
            viewer,
            key,
            "director.consent",
            {"scene_id": scene_id, "policy_revision": expected_policy_revision, "consent": consent},
            operation,
            authorize=authorize,
        )

    def _latest_source(self, c: Connection, source_id: str) -> Observation | None:
        table = t.director["inputs"]
        body = c.scalar(
            sa.select(table.c.body_json)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.source_id == source_id,
            )
            .order_by(table.c.source_revision.desc())
            .limit(1)
        )
        return Observation.model_validate_json(body) if body else None

    def _append(
        self, c: Connection, scene_id: str, state: SceneObservationState, observation: Observation
    ) -> InputResult:
        c.execute(
            t.director["inputs"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=scene_id,
                sequence=observation.sequence,
                source_id=observation.source_id,
                source_revision=observation.source_revision,
                owner_id=observation.author_id,
                kind=observation.kind,
                accepted_at=observation.accepted_at,
                body_json=observation.model_dump_json(),
            )
        )
        state = state.model_copy(
            update={
                "sequence": observation.sequence,
                "generation": state.generation + 1,
                "last_input_at": observation.accepted_at
                if observation.kind == "message"
                else state.last_input_at,
            }
        )
        self._save(c, scene_id, state)
        return InputResult(
            scene_id=scene_id,
            source_id=observation.source_id,
            source_revision=observation.source_revision,
            sequence=observation.sequence,
            generation=state.generation,
        )

    def append_scene_input(
        self, viewer: GuildViewer, scene_id: str, command: AppendSceneInput
    ) -> InputResult:
        command = AppendSceneInput.model_validate_json(command.model_dump_json())

        def authorize(c: Connection) -> None:
            self._authorize_input(c, viewer, scene_id, command.speaker)
            if command.source_id:
                source = self._latest_source(c, command.source_id)
                if (
                    source is None
                    or source.author_id != str(viewer.user_id)
                    or source.kind != "message"
                ):
                    raise WorkflowError("SOURCE_UNAVAILABLE: edit only your own scene input.")
                table = t.director["inputs"]
                if not c.scalar(
                    sa.select(table.c.source_id)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene_id,
                        table.c.source_id == command.source_id,
                    )
                    .limit(1)
                ):
                    raise WorkflowError("SOURCE_UNAVAILABLE: use this input's original scene.")

        def operation(c: Connection) -> dict[str, Any]:
            scene, state, actor = self._authorize_input(c, viewer, scene_id, command.speaker)
            self.game.unpaused(c)
            if scene["revision"] != command.expected_scene_revision:
                raise WorkflowError("STALE_SCENE: refresh the actual scene binding.")
            if command.classification == "ooc":
                return InputResult(
                    scene_id=scene_id, generation=state.generation, status="ignored_ooc"
                ).model_dump(mode="json")
            lock = self.game.lock(c, scene["channel_id"])
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: finish the pending Play before adding IC input.")
            old = self._latest_source(c, command.source_id) if command.source_id else None
            if old and (
                old.source_revision != command.expected_source_revision or old.actor != actor
            ):
                raise WorkflowError("STALE_SOURCE: refresh the original input and role.")
            audience = tuple(sorted(str(x) for x in scene["participants"]))
            if old and old.audience_ids != audience:
                raise WorkflowError(
                    "SOURCE_SCOPE_CHANGED: sharing with new participants needs review."
                )
            if old and old.fictional_channel != command.fictional_channel:
                raise WorkflowError("SOURCE_CHANNEL_CHANGED: report through a new message.")
            observation = Observation(
                sequence=state.sequence + 1,
                generation=state.generation + 1,
                source_id=old.source_id if old else str(uuid4()),
                source_revision=old.source_revision + 1 if old else 1,
                kind="message",
                author_id=str(viewer.user_id),
                actor=actor,
                audience_ids=audience,
                accepted_at=float(self.store.clock()),
                text=command.text,
                fictional_channel=command.fictional_channel,
            )
            return self._append(c, scene_id, state, observation).model_dump(mode="json")

        semantic = command.model_dump(
            mode="json",
            exclude={"command_key", "expected_scene_revision", "expected_source_revision"},
        )
        result = self.store._write(
            viewer,
            command.command_key,
            "director.input",
            {"scene_id": scene_id, **semantic},
            operation,
            authorize=authorize,
        )
        return InputResult.model_validate(result)

    def _prove_committed_play(
        self, c: Connection, scene_id: str, action_id: str
    ) -> tuple[
        dict[str, Any],
        SceneObservationState,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        ActorRef,
    ]:
        """Shared native source proof; callers retain their current transaction."""
        self._scope()
        scene = self._scene(c, scene_id)
        state = self._state(c, scene_id)
        if state.policy.mode != "shadow" or not self._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: current participant consent is required.")
        self.game.unpaused(c)
        action = self.game.action(c, action_id)
        data = action["data"]
        if {str(x) for x in data.get("participants", ())} != {
            str(x) for x in scene["participants"]
        }:
            raise WorkflowError("SOURCE_SCOPE_CHANGED: retain the original Play audience.")
        if (
            action["scene_id"] != scene_id
            or action["parent_id"] is not None
            or data.get("play") != "keep_your_head"
            or any(
                data.get(key)
                for key in (
                    "m3",
                    "actor_basic",
                    "gorgon_play",
                    "void_keep",
                    "handler_play_m3",
                    "kicked_puppy",
                    "nightmare_core",
                    "dampener",
                    "princess_child",
                    "ankou_feedback_child",
                    "bonded_child",
                    "red_queen_child",
                    "changeling_child",
                )
            )
            or data.get("private_audience")
        ):
            raise WorkflowError(
                "UNSUPPORTED_PLAY_SOURCE: only ordinary native Keep Your Head is supported."
            )
        if action["state"] != "complete" or self.game.pending(c, action_id):
            raise WorkflowError("PLAY_PENDING: preserve the actual outstanding player choices.")
        actions = t.m2["m2_actions"]
        if c.execute(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.parent_id == action_id,
            )
        ).first():
            raise WorkflowError(
                "UNSUPPORTED_PLAY_SOURCE: child workflows need their source adapter."
            )
        work = t.m3["m3_required_work"]
        latest = {
            row["id"]: row
            for row in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.scene_id == scene_id,
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        canon = load_state(c, self.store.campaign_id)
        self.game.action_characters(c, action, canon)
        if any(row["state"] != "resolved" for row in latest.values()) or any(
            x.action == action_id and x.state == "pending" for x in canon.obligations
        ):
            raise WorkflowError("PLAY_PENDING: complete the actual required source work.")
        receipt = (
            c.execute(
                sa.select(t.m2["m2_receipts"]).where(
                    t.m2["m2_receipts"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == action_id,
                )
            )
            .mappings()
            .first()
        )
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == data.get("response_event"),
                    t.events.c.kind == "m2.choice_resolved",
                )
            )
            .mappings()
            .first()
        )
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.event_id).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == data.get("response_event"),
            )
        )
        if (
            not receipt
            or not event
            or not history
            or json.loads(event["payload_json"]).get("action_id") != action_id
            or json.loads(receipt["body_json"]) != data.get("receipt")
        ):
            raise WorkflowError(
                "UNPROVEN_PLAY: the original committed outcome and receipt are required."
            )
        actor = ActorRef(
            kind="pilot",
            entity=str(action["actor_id"]),
            incarnation=self.game.character_binding(
                c, canon, int(action["actor_id"]), require_current_profile=False
            ),
        )
        return scene, state, action, dict(receipt), dict(event), actor

    def observe_committed_play(self, scene_id: str, action_id: str) -> InputResult:
        """Trusted source adapter for native Keep Your Head only; no browser success flags."""
        with self.store.transaction() as c:
            scene, state, action, receipt, event, actor = self._prove_committed_play(
                c, scene_id, action_id
            )
            source_id = "play:" + action_id
            old = self._latest_source(c, source_id)
            if old:
                return InputResult(
                    scene_id=scene_id,
                    source_id=old.source_id,
                    source_revision=old.source_revision,
                    sequence=old.sequence,
                    generation=old.generation,
                )
            # Only references enter the batch; private Handler answers/results do not.
            observation = Observation(
                sequence=state.sequence + 1,
                generation=state.generation + 1,
                source_id=source_id,
                source_revision=1,
                kind="completed_play",
                author_id=str(action["actor_id"]),
                actor=actor,
                audience_ids=tuple(sorted(str(x) for x in scene["participants"])),
                accepted_at=float(self.store.clock()),
                action_id=action_id,
                receipt_id=receipt["id"],
                event_id=event["id"],
            )
            result = self._append(c, scene_id, state, observation)
            self.store._audit(
                c,
                action["actor_id"],
                "director:play:" + action_id,
                "director.play_observed",
                result.model_dump(mode="json"),
                ruleset_version="p2-observation-synthetic-v1",
            )
            return result

    def _pending(
        self, scene_id: str, frontier: int, *, include_handled: bool = False
    ) -> sa.Select[Any]:
        table = t.director["inputs"]
        newer = table.alias("newer")
        query = sa.select(table).where(
            table.c.campaign_id == self.store.campaign_id,
            table.c.scene_id == scene_id,
            table.c.sequence > frontier,
            ~sa.exists(
                sa.select(newer.c.source_id).where(
                    newer.c.campaign_id == table.c.campaign_id,
                    newer.c.source_id == table.c.source_id,
                    newer.c.source_revision > table.c.source_revision,
                )
            ),
        )
        if not include_handled:
            outcomes = t.director_context["shadow"]
            query = query.where(
                ~sa.exists(
                    sa.select(outcomes.c.id).where(
                        outcomes.c.campaign_id == table.c.campaign_id,
                        outcomes.c.scene_id == table.c.scene_id,
                        sa.func.json_extract(outcomes.c.body_json, "$.record_type").in_(
                            ("conversation_exchange", "gm_play_review")
                        ),
                        sa.func.json_extract(outcomes.c.body_json, "$.route") == "gm",
                        sa.func.json_extract(outcomes.c.body_json, "$.source_id")
                        == table.c.source_id,
                        sa.func.json_extract(outcomes.c.body_json, "$.source_revision")
                        == table.c.source_revision,
                    )
                )
            )
        return query

    def _stats(
        self, c: Connection, scene_id: str, state: SceneObservationState
    ) -> tuple[int, int, float | None]:
        pending = self._pending(scene_id, state.reviewed_sequence).subquery()
        messages, triggers, oldest = c.execute(
            sa.select(
                sa.func.count().filter(pending.c.kind == "message"),
                sa.func.count().filter(pending.c.kind == "completed_play"),
                sa.func.min(pending.c.accepted_at).filter(pending.c.kind == "message"),
            )
        ).one()
        return messages, triggers, oldest

    def _guard(self, c: Connection, scene: dict[str, Any], state: SceneObservationState) -> str:
        members = list(
            c.execute(
                sa.select(t.members.c.user_id, t.members.c.active, t.members.c.role)
                .where(t.members.c.campaign_id == self.store.campaign_id)
                .order_by(t.members.c.user_id)
            ).tuples()
        )
        canonical = c.scalar(
            sa.select(t.m2["m2_state"].c.revision).where(
                t.m2["m2_state"].c.campaign_id == self.store.campaign_id
            )
        )
        safety = c.scalar(
            sa.select(sa.func.max(t.events.c.seq)).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == "safety.changed",
            )
        )
        actions = t.m2["m2_actions"]
        action_versions = list(
            c.execute(
                sa.select(actions.c.id, actions.c.revision, actions.c.state)
                .where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.scene_id == scene["id"],
                )
                .order_by(actions.c.id)
            ).tuples()
        )
        choices = t.m2["m2_choices"]
        choice_versions = list(
            c.execute(
                sa.select(choices.c.id, choices.c.revision, choices.c.state)
                .join(
                    actions,
                    sa.and_(
                        actions.c.campaign_id == choices.c.campaign_id,
                        actions.c.id == choices.c.action_id,
                    ),
                )
                .where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.scene_id == scene["id"],
                )
                .order_by(choices.c.id)
            ).tuples()
        )
        work = t.m3["m3_required_work"]
        work_versions = list(
            c.execute(
                sa.select(work.c.id, work.c.revision, work.c.state)
                .where(work.c.campaign_id == self.store.campaign_id, work.c.scene_id == scene["id"])
                .order_by(work.c.id, work.c.revision)
            ).tuples()
        )
        lock = self.game.lock(c, scene["channel_id"])
        # Policy sets have no order. Their JSON array order can change with the
        # process hash seed; that must not make unchanged saved proposals stale.
        runtime_policy = self.store.policy.model_dump(mode="json")
        runtime_policy["status_user_ids"] = sorted(runtime_policy["status_user_ids"])
        approval = runtime_policy.get("m3_approval")
        if approval is not None:
            for name in ("subsystems", "activity_specialist_rules", "native_risk_plays"):
                if name in approval:
                    approval[name] = sorted(approval[name])
        return _digest(
            {
                "generation": state.generation,
                "scene_revision": scene["revision"],
                "binding": scene["binding_event"],
                "people": scene["participants"],
                "members": [tuple(row) for row in members],
                "canonical": canonical,
                "safety": safety,
                "runtime_policy": runtime_policy,
                "actions": [tuple(row) for row in action_versions],
                "choices": [tuple(row) for row in choice_versions],
                "required_work": [tuple(row) for row in work_versions],
                "lock": (lock["action_id"], lock["state"]) if lock else None,
            }
        )

    def claim_review(self, scene_id: str) -> ReviewBatch | None:
        if not self.synthetic:
            return None
        with self.store.transaction() as c:
            scene = self._scene(c, scene_id)
            state = self._state(c, scene_id)
            if state.policy.mode == "off" or not self._consented(c, scene, state):
                return None
            self.game.unpaused(c)
            now = float(self.store.clock())
            guard = self._guard(c, scene, state)
            runs = t.director["runs"]
            active = (
                c.execute(
                    sa.select(runs).where(
                        runs.c.campaign_id == self.store.campaign_id,
                        runs.c.scene_id == scene_id,
                        runs.c.status == "running",
                    )
                )
                .mappings()
                .first()
            )
            if active:
                batch = ReviewBatch.model_validate_json(active["body_json"])
                if active["lease_until"] > now and batch.guard_digest == guard:
                    return None
                c.execute(
                    runs.update()
                    .where(
                        runs.c.run_id == active["run_id"],
                        runs.c.campaign_id == self.store.campaign_id,
                    )
                    .values(status="stale")
                )
            messages, triggers, oldest = self._stats(c, scene_id, state)
            reason, _ = review_eligibility(
                state.policy,
                now=now,
                messages=messages,
                triggers=triggers,
                oldest_at=oldest,
                latest_at=state.last_input_at,
                last_review_at=state.last_review_at,
            )
            if reason is None:
                return None
            rows = (
                c.execute(
                    self._pending(scene_id, state.reviewed_sequence)
                    .order_by(t.director["inputs"].c.sequence)
                    .limit(20)
                )
                .mappings()
                .all()
            )
            inputs = tuple(Observation.model_validate_json(row["body_json"]) for row in rows)
            people = tuple(sorted(str(x) for x in scene["participants"]))
            if any(x.audience_ids != people for x in inputs):
                raise WorkflowError("SOURCE_SCOPE_CHANGED: retained input needs privacy review.")
            # A bounded tail is reference material, not another unreviewed episode.
            tail_rows = (
                c.execute(
                    self._pending(scene_id, 0)
                    .where(
                        t.director["inputs"].c.sequence <= state.reviewed_sequence,
                        t.director["inputs"].c.kind == "message",
                    )
                    .order_by(t.director["inputs"].c.sequence.desc())
                    .limit(3)
                )
                .mappings()
                .all()
            )
            tail = tuple(
                Observation.model_validate_json(row["body_json"]) for row in reversed(tail_rows)
            )
            if any(x.audience_ids != people for x in tail):
                tail = ()
            batch = ReviewBatch(
                campaign_id=self.store.campaign_id,
                scene_id=scene_id,
                run_id=str(uuid4()),
                lease_token=str(uuid4()),
                lease_until=now + 120,
                generation=state.generation,
                frontier=inputs[-1].sequence,
                scene_revision=scene["revision"],
                policy_revision=state.policy_revision,
                consent_generation=state.consent_generation,
                canonical_revision=load_state(c, self.store.campaign_id).revision,
                binding_event=scene["binding_event"],
                guard_digest=guard,
                reason=reason,
                inputs=inputs,
                recent_tail=tail,
            )
            c.execute(
                runs.insert().values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    run_id=batch.run_id,
                    lease_token=batch.lease_token,
                    lease_until=batch.lease_until,
                    status="running",
                    body_json=batch.model_dump_json(),
                )
            )
            return batch

    def acknowledge_review(
        self, run_id: str, lease_token: str, *, success: bool
    ) -> ReviewCompletion:
        self._scope()
        if type(success) is not bool:
            raise WorkflowError("INVALID_COMPLETION: supply an explicit synthetic review outcome.")
        with self.store.transaction() as c:
            return self.complete_in_transaction(c, run_id, lease_token, success=success)

    def complete_in_transaction(
        self, c: Connection, run_id: str, lease_token: str, *, success: bool
    ) -> ReviewCompletion:
        """Internal atomic seam for the shadow outcome consumer."""
        self._scope()
        table = t.director["runs"]
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.run_id == run_id,
                    table.c.lease_token == lease_token,
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("STALE_CLAIM: use the actual worker claim.")
        batch = ReviewBatch.model_validate_json(row["body_json"])
        scene = self._scene(c, batch.scene_id)
        state = self._state(c, batch.scene_id)
        if row["status"] in ("reviewed", "failed"):
            if success != (row["status"] == "reviewed"):
                raise WorkflowError("IDEMPOTENCY_CONFLICT: review completion changed.")
            return ReviewCompletion(run_id=run_id, status=row["status"], frontier=batch.frontier)
        self.game.unpaused(c)
        if (
            row["status"] != "running"
            or row["lease_until"] <= self.store.clock()
            or state.policy.mode != "shadow"
            or not self._consented(c, scene, state)
            or batch.guard_digest != self._guard(c, scene, state)
        ):
            raise WorkflowError("STALE_CLAIM: source, authority or worker claim changed.")
        if success:
            self._save(
                c,
                batch.scene_id,
                state.model_copy(
                    update={
                        "reviewed_sequence": batch.frontier,
                        "last_review_at": float(self.store.clock()),
                    }
                ),
            )
        result = ReviewCompletion(
            run_id=run_id, status="reviewed" if success else "failed", frontier=batch.frontier
        )
        c.execute(
            table.update()
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.run_id == run_id,
                table.c.lease_token == lease_token,
            )
            .values(status=result.status)
        )
        return result

    def status(self, viewer: GuildViewer, scene_id: str) -> ObservationStatus:
        with self.store.transaction() as c:
            scene = self._scene(c, scene_id, viewer)
            state = self._state(c, scene_id)
            messages, triggers, oldest = self._stats(c, scene_id, state)
            consented = self._consented(c, scene, state)
            mode = state.policy.mode if self.synthetic else "off"
            phase: Any = "off"
            next_at = None
            if mode != "off":
                if not consented:
                    phase = "awaiting_consent"
                elif c.execute(
                    sa.select(t.pauses).where(t.pauses.c.campaign_id == self.store.campaign_id)
                ).first():
                    phase = "paused"
                else:
                    reason, next_at = review_eligibility(
                        state.policy,
                        now=float(self.store.clock()),
                        messages=messages,
                        triggers=triggers,
                        oldest_at=oldest,
                        latest_at=state.last_input_at,
                        last_review_at=state.last_review_at,
                    )
                    phase = "ready" if reason else "waiting" if messages or triggers else "idle"
                    runs = t.director["runs"]
                    active = c.scalar(
                        sa.select(runs.c.body_json).where(
                            runs.c.campaign_id == self.store.campaign_id,
                            runs.c.scene_id == scene_id,
                            runs.c.status == "running",
                            runs.c.lease_until > self.store.clock(),
                        )
                    )
                    if active and ReviewBatch.model_validate_json(
                        active
                    ).guard_digest == self._guard(c, scene, state):
                        phase = "running"
            return ObservationStatus(
                scene_id=scene_id,
                scene_revision=scene["revision"],
                policy_revision=state.policy_revision,
                mode=mode,
                consented=consented,
                phase=phase,
                pending_messages=messages,
                pending_triggers=triggers,
                generation=state.generation,
                reviewed_sequence=state.reviewed_sequence,
                next_review_at=next_at,
            )
