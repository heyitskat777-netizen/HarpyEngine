"""Private controller-authored response handoffs; never inferred reactions or mechanics."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.gm_outcomes import OutcomePacket
from girlframe.ai.gm_protocol import Evidence, TaskFrame
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_observation import _digest
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.gm_outcomes import GMOutcomeService, SourceKind


class DirectorResponseService:
    def __init__(self, outcomes: "GMOutcomeService"):
        self.outcomes = outcomes
        self.store, self.observer = outcomes.store, outcomes.observer

    def _binding(
        self,
        c: Connection,
        scene: str,
        kind: str,
        source: str,
        owner: str,
        frame: TaskFrame,
        native: dict[str, Any],
    ) -> str:
        # Ordinary transcript additions need not revoke an unanswered question.
        # Real native choices, actors, consent, policy and safety still bind it.
        row = self.observer._scene(c, scene)
        state = self.observer._state(c, scene).model_copy(update={"generation": 0})
        return _digest(
            {
                "scene": scene,
                "source_kind": kind,
                "source_id": source,
                "owner": owner,
                "frame": frame.model_dump(mode="json", exclude={"response_request"}),
                "native": {key: value for key, value in native.items() if key != "state_revision"},
                "guard": self.observer._guard(c, row, state),
                "consent_generation": state.consent_generation,
            }
        )

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        outcome_request: str,
        question: str,
        *,
        clarify_intent: bool = False,
    ) -> dict[str, Any]:
        """GM explicitly selects the question to disclose; no private frame is forwarded."""
        if not question.strip() or len(question) > 1200:
            raise WorkflowError("RESPONSE_QUESTION_INVALID: supply a short explicit question.")

        def operation(c: Connection) -> dict[str, Any]:
            packet = OutcomePacket.model_validate_json(
                json.dumps(
                    self.outcomes._record(c, scene, outcome_request, "gm_outcome_request")["packet"]
                )
            )
            self.outcomes._current(c, packet)
            if packet.operation != "keep" or packet.frame is None:
                raise WorkflowError("RESPONSE_NOT_REQUIRED: select a pending Keep ruling.")
            if clarify_intent:
                if packet.frame.intent != "needs_clarification" or packet.frame.intent_request:
                    raise WorkflowError("INTENT_NOT_REQUIRED: select a ruling held for intent.")
                actor, controller = self._acting_pilot(c, scene, packet.native)
            elif (
                packet.frame.response_scope != "other"
                or packet.frame.response_request is not None
                or packet.native.get("response_authorized")
            ):
                raise WorkflowError(
                    "RESPONSE_NOT_REQUIRED: use an unresolved actual target response."
                )
            else:
                response_actor = packet.native.get("response_actor")
                response_controller = packet.native.get("response_controller")
                if not isinstance(response_actor, dict) or not isinstance(response_controller, str):
                    raise WorkflowError("RESPONSE_NOT_REQUIRED: recover the actual target.")
                actor, controller = response_actor, response_controller
            binding = self._binding(
                c,
                scene,
                packet.source_kind,
                packet.source_id,
                packet.owner_id,
                packet.frame,
                packet.native,
            )
            value = {
                "id": "director-response:" + str(uuid4()),
                "record_type": "director_response_request",
                "scene_id": scene,
                "request": outcome_request,
                "source_id": packet.source_id,
                "source_kind": packet.source_kind,
                "actor": actor,
                "controller": controller,
                **({"purpose": "intent"} if clarify_intent else {}),
                "question": question,
                "binding": binding,
            }
            self.outcomes._save(c, value)
            return {"id": value["id"], "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.response_request",
            {
                "scene": scene,
                "request": outcome_request,
                "question": question,
                **({"clarify_intent": True} if clarify_intent else {}),
            },
            operation,
            authorize=lambda c: self._authorize(c, viewer, scene, gm=True),
        )

    def _acting_pilot(
        self, c: Connection, scene: str, native: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        from girlframe.services.director_knowledge import DirectorKnowledgeService

        action = native["action"]
        data = action["data"]
        controller = str(action["actor_id"])
        if data.get("actor_basic"):
            actor = ActorRef.model_validate(data["actor_basic"]["ref"])
        else:
            actor = ActorRef(
                kind="pilot",
                entity=controller,
                incarnation=data.get("character_ids", {}).get(controller),
            )
        current = DirectorKnowledgeService(self.outcomes.context)._actors(
            c, self.observer._scene(c, scene)
        )
        if actor.kind != "pilot" or actor.entity != controller or actor not in current:
            raise WorkflowError("INTENT_ACTOR_UNAVAILABLE: recover the original acting Pilot.")
        return actor.model_dump(mode="json"), controller

    def _authorize(
        self, c: Connection, viewer: GuildViewer, scene: str, *, gm: bool = False
    ) -> None:
        self.outcomes._scope(c, viewer, scene, gm=gm)

    def _load(self, c: Connection, scene: str, identity: str) -> dict[str, Any]:
        return self.outcomes._record(c, scene, identity, "director_response_request")

    def _fresh(self, c: Connection, scene: str, record: dict[str, Any]) -> OutcomePacket:
        original = OutcomePacket.model_validate_json(
            json.dumps(
                self.outcomes._record(c, scene, record["request"], "gm_outcome_request")["packet"]
            )
        )
        assert original.frame is not None
        packet = self.outcomes._snapshot(
            c, scene, original.source_kind, original.source_id, original.frame
        )
        assert packet.frame is not None
        binding = self._binding(
            c,
            scene,
            packet.source_kind,
            packet.source_id,
            packet.owner_id,
            packet.frame,
            packet.native,
        )
        if binding != record["binding"]:
            raise WorkflowError("STALE_TARGET_RESPONSE: reopen the native source and target.")
        if record.get("purpose") == "intent" and self._acting_pilot(c, scene, packet.native) != (
            record["actor"],
            record["controller"],
        ):
            raise WorkflowError("INTENT_ACTOR_UNAVAILABLE: recover the original acting Pilot.")
        return packet

    def _answer(self, c: Connection, scene: str, identity: str) -> dict[str, Any] | None:
        try:
            return self.outcomes._record(c, scene, identity + ":answer", "director_response_answer")
        except WorkflowError:
            return None

    def get(
        self, viewer: GuildViewer, scene: str, identity: str, *, gm: bool = False
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene, gm=gm)
            record = self._load(c, scene, identity)
            if not gm and record["controller"] != str(viewer.user_id):
                raise WorkflowError(
                    "RESPONSE_NOT_OWNED: only the actual target controller may read."
                )
            answer = self._answer(c, scene, identity)
            status = "answered" if answer else "awaiting_response"
            try:
                self._fresh(c, scene, record)
            except (WorkflowError, ValueError):
                status = "stale_reopen_source"
            # Frozen owner authorization prevents a replacement controller from
            # inheriting private correspondence; stale text is only historical.
            return {
                "id": identity,
                "question": record["question"],
                "actor": record["actor"],
                "status": status,
                "purpose": record.get("purpose", "target_response"),
                "answer": {k: answer[k] for k in ("decision", "text")} if answer else None,
                "effects_applied": False,
                "publication": "private_adjudication_only",
            }

    def pending(self, viewer: GuildViewer, scene: str, *, gm: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene, gm=gm)
            table = t.director_context["shadow"]
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.func.json_extract(table.c.body_json, "$.record_type")
                        == "director_response_request",
                    )
                )
            ]
            result = []
            for record in records:
                answer = self._answer(c, scene, record["id"])
                if not gm and (record["controller"] != str(viewer.user_id) or answer):
                    continue
                try:
                    self._fresh(c, scene, record)
                except (WorkflowError, ValueError):
                    continue
                result.append(
                    {
                        "id": record["id"],
                        "actor": record["actor"],
                        "purpose": record.get("purpose", "target_response"),
                        "status": "answered_resume_required" if answer else "awaiting_response",
                    }
                )
            return result

    def answer(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        decision: Literal["accept", "decline", "clarify"],
        text: str,
    ) -> dict[str, Any]:
        if decision not in ("accept", "decline", "clarify") or not text.strip() or len(text) > 1200:
            raise WorkflowError("RESPONSE_INVALID: provide your own bounded response.")

        def operation(c: Connection) -> dict[str, Any]:
            record = self._load(c, scene, identity)
            if record["controller"] != str(viewer.user_id):
                raise WorkflowError(
                    "RESPONSE_NOT_OWNED: only the actual target controller may answer."
                )
            self._fresh(c, scene, record)
            if record.get("purpose") == "intent" and (decision != "clarify" or len(text) > 1000):
                raise WorkflowError(
                    "INTENT_ANSWER: describe your own intent in up to 1000 characters."
                )
            if self._answer(c, scene, identity):
                raise WorkflowError("RESPONSE_FINAL: this request already has an answer.")
            self.outcomes._save(
                c,
                {
                    "id": identity + ":answer",
                    "record_type": "director_response_answer",
                    "scene_id": scene,
                    "request": identity,
                    "actor": record["actor"],
                    "controller": str(viewer.user_id),
                    "decision": decision,
                    "text": text,
                },
            )
            return {"id": identity, "status": "answered", "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.response_answer",
            {"scene": scene, "request": identity, "decision": decision, "text": text},
            operation,
            authorize=lambda c: self._authorize(c, viewer, scene),
        )

    def bind(
        self,
        c: Connection,
        scene: str,
        kind: "SourceKind",
        source: str,
        owner: str,
        frame: TaskFrame,
        native: dict[str, Any],
        evidence: list[Evidence],
    ) -> None:
        assert frame.response_request is not None
        record = self._load(c, scene, frame.response_request)
        if record.get("purpose") == "intent":
            raise WorkflowError(
                "RESPONSE_SOURCE: an intent answer cannot replace a target decision."
            )
        if self._binding(c, scene, kind, source, owner, frame, native) != record["binding"]:
            raise WorkflowError(
                "STALE_TARGET_RESPONSE: retain the exact original attempt and target."
            )
        answer = self._answer(c, scene, record["id"])
        if answer is None:
            raise WorkflowError("TARGET_RESPONSE_REQUIRED: await the actual controller's answer.")
        native["response_authorized"] = answer["decision"] != "clarify"
        native["response_decision"] = answer["decision"]
        evidence.append(
            Evidence(
                id="target_response",
                audience="gm",
                value={
                    "id": record["id"],
                    "actor": record["actor"],
                    "controller": record["controller"],
                    "question": record["question"],
                    "decision": answer["decision"],
                    "text": answer["text"],
                },
            )
        )

    def _clarified_frame(
        self, c: Connection, scene: str, record: dict[str, Any], original: TaskFrame
    ) -> TaskFrame:
        answer = self._answer(c, scene, record["id"])
        if answer is None:
            raise WorkflowError("INTENT_ANSWER_REQUIRED: await the original Pilot's clarification.")
        return original.model_copy(
            update={
                "intent": "established",
                "stakes": answer["text"],
                "intent_request": record["id"],
            }
        )

    def bind_intent(
        self,
        c: Connection,
        scene: str,
        kind: "SourceKind",
        source: str,
        frame: TaskFrame,
        evidence: list[Evidence],
    ) -> None:
        assert frame.intent_request is not None
        record = self._load(c, scene, frame.intent_request)
        if record.get("purpose") != "intent" or (kind, source) != (
            record["source_kind"],
            record["source_id"],
        ):
            raise WorkflowError("INTENT_SOURCE: retain the original pending ruling.")
        original = self._fresh(c, scene, record)
        assert original.frame is not None
        expected = self._clarified_frame(c, scene, record, original.frame)
        # A subsequent other-character answer remains a separate owned handoff.
        if frame.model_copy(update={"response_request": expected.response_request}) != expected:
            raise WorkflowError("INTENT_SOURCE: retain the actual Pilot's clarified intent.")
        evidence.append(
            Evidence(
                id="actor_intent",
                audience="gm",
                value={
                    "id": record["id"],
                    "actor": record["actor"],
                    "text": expected.stakes,
                },
            )
        )

    def resume(self, viewer: GuildViewer, key: str, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.outcomes._scope(c, viewer, scene, gm=True)
            record = self._load(c, scene, identity)
            packet = self._fresh(c, scene, record)
            assert packet.frame is not None
            frame = (
                self._clarified_frame(c, scene, record, packet.frame)
                if record.get("purpose") == "intent"
                else packet.frame.model_copy(update={"response_request": identity})
            )
        return self.outcomes.open(viewer, key, scene, packet.source_kind, packet.source_id, frame)
