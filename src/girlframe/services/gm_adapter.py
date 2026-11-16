"""Offline GM-provider boundary over native evidence, private reasoning and scoped views."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.gm_protocol import (
    Evidence,
    GMPacket,
    GMProposal,
    GMProvider,
    OfflineReviewProvider,
    TaskFrame,
    validate_proposal,
)
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_native import native_snapshot
from girlframe.services.director_observation import _digest
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class GMAdapterService:
    def __init__(self, context: DirectorContextService, provider: GMProvider | None = None):
        self.context = context
        self.observer = context.observations
        self.store = context.store
        self.provider = provider if provider is not None else OfflineReviewProvider()

    def _gm(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        self.observer._scope()
        self.store.administrator(viewer)
        self.context._build(c, viewer, scene, actor=None)

    def _saved(self, c: Connection, identity: str, kind: str, scene: str) -> dict[str, Any]:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        value = json.loads(raw) if raw else None
        if not value or value.get("record_type") != kind:
            raise WorkflowError("GM_RECORD_UNAVAILABLE: no accessible record in this scene.")
        return dict(value)

    def _save(self, c: Connection, value: dict[str, Any]) -> None:
        c.execute(
            t.director_context["shadow"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=value["scene_id"],
                id=value["id"],
                body_json=json.dumps(value, sort_keys=True),
            )
        )

    def _packet(
        self, c: Connection, viewer: GuildViewer | None, binding: dict[str, Any], frame: TaskFrame
    ) -> tuple[GMPacket, dict[str, Any]]:
        if viewer is not None:
            self._gm(c, viewer, binding["scene_id"])
        native = native_snapshot(
            c,
            self.observer,
            binding["scene_id"],
            binding["source_id"],
            binding["source_revision"],
            binding["action_id"],
        )
        data = native["action"]["data"]
        source = native["source"]
        facts = [
            Evidence(id="goal", value=source.text, audience="scene"),
            Evidence(
                id="receipt", value=json.loads(native["receipt"]["body_json"]), audience="scene"
            ),
            Evidence(
                id="traits",
                value={key: data["result"].get(key, []) for key in ("positive", "negative")},
                audience="actor",
            ),
        ]
        canon = native["canonical"].model_dump(mode="json")
        for index, fact in enumerate(canon.get("facts", [])):
            if isinstance(fact, dict) and fact.get("kind") == "scene_condition":
                facts.append(
                    Evidence(
                        id=f"condition:{index}:" + _digest(fact)[:16], value=fact, audience="gm"
                    )
                )
        for reference in self.context._current(c, binding["scene_id"]):
            facts.append(
                Evidence(
                    id="reference:" + reference.id,
                    value=reference.model_dump(mode="json"),
                    audience="gm",
                )
            )
        ids = {fact.id for fact in facts}
        if len({d.id for d in frame.demands}) != len(frame.demands):
            raise WorkflowError("INVALID_FRAME: demands must have distinct IDs.")
        if len({p.evidence_id for p in frame.prerequisites}) != len(frame.prerequisites) or any(
            p.evidence_id not in ids or not p.evidence_id.startswith("condition:")
            for p in frame.prerequisites
        ):
            raise WorkflowError(
                "INVALID_FRAME: prerequisite interpretations need real scene evidence."
            )
        records: dict[str, Any] = {}
        for name in ("m3_missions", "m3_off_duty", "m3_required_work"):
            table = t.m3[name]
            records[name] = [
                dict(row)
                for row in c.execute(
                    sa.select(table).where(table.c.campaign_id == self.store.campaign_id)
                ).mappings()
            ]
        actions = t.m2["m2_actions"]
        records["scene_actions"] = [
            dict(row)
            for row in c.execute(
                sa.select(actions).where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.scene_id == binding["scene_id"],
                )
            ).mappings()
        ]
        for name in ("m2_receipts", "m2_choices"):
            table = t.m2[name]
            records[name] = [
                dict(row)
                for row in c.execute(
                    sa.select(table)
                    .join(
                        actions,
                        sa.and_(
                            actions.c.campaign_id == table.c.campaign_id,
                            actions.c.id == table.c.action_id,
                        ),
                    )
                    .where(
                        actions.c.campaign_id == self.store.campaign_id,
                        actions.c.scene_id == binding["scene_id"],
                    )
                ).mappings()
            ]
        history_query = self.observer._pending(binding["scene_id"], 0, include_handled=True)
        total = c.scalar(sa.select(sa.func.count()).select_from(history_query.subquery())) or 0
        history = [
            Observation.model_validate_json(row["body_json"]).model_dump(mode="json")
            for row in c.execute(
                history_query.order_by(t.director["inputs"].c.sequence.desc()).limit(100)
            ).mappings()
        ]
        packet = GMPacket(
            request_id="pending",
            play=data["play"],
            source_id=source.source_id,
            source_revision=source.source_revision,
            action_id=native["action"]["id"],
            action_revision=native["action"]["revision"],
            receipt_id=native["receipt"]["id"],
            goal=source.text or "",
            frame=frame,
            evidence=tuple(facts),
            positive=tuple(data["result"].get("positive", [])),
            negative=tuple(data["result"].get("negative", [])),
            stage=native["stage"],
            native_result=data["result"],
            pending_choices=tuple(
                {key: x[key] for key in ("id", "actor_id", "kind", "revision", "state")}
                for x in native["pending"]
            ),
            followups=tuple(native["followups"]),
            gm_private_context={
                "canonical": canon,
                "records": records,
                "history": list(reversed(history)),
                "history_omitted": max(0, total - len(history)),
                "lineage": native["lineage"],
                "guard": self.observer._guard(
                    c, native["scene"], self.observer._state(c, binding["scene_id"])
                ),
            },
        )
        packet = packet.model_copy(update={"request_id": _digest(packet.model_dump(mode="json"))})
        return packet, native

    def evidence(
        self,
        viewer: GuildViewer,
        scene_id: str,
        source_id: str,
        source_revision: int,
        action_id: str,
    ) -> GMPacket:
        """GM-only draft packet for constructing an explicit interpretation, not a ruling."""
        with self.store.engine.connect() as c:
            packet, _ = self._packet(
                c,
                viewer,
                {
                    "scene_id": scene_id,
                    "source_id": source_id,
                    "source_revision": source_revision,
                    "action_id": action_id,
                },
                TaskFrame(stakes="Not yet framed", intent="needs_clarification"),
            )
            return packet

    def frame(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        source_revision: int,
        action_id: str,
        task: TaskFrame,
    ) -> dict[str, Any]:
        if type(source_revision) is not int or source_revision < 1:
            raise WorkflowError("STALE_SOURCE: require a positive original source revision.")
        task = TaskFrame.model_validate_json(task.model_dump_json())
        binding = {
            "scene_id": scene_id,
            "source_id": source_id,
            "source_revision": source_revision,
            "action_id": action_id,
        }

        def authorize(c: Connection) -> None:
            self._gm(c, viewer, scene_id)

        def operation(c: Connection) -> dict[str, Any]:
            packet, _ = self._packet(c, viewer, binding, task)
            identity = "gm-frame:" + str(uuid4())
            self._save(
                c,
                {
                    "id": identity,
                    "record_type": "gm_task_frame",
                    **binding,
                    "owner_id": str(viewer.user_id),
                    "task": task.model_dump(mode="json"),
                    "request_id": packet.request_id,
                    "keep_choice": next(
                        (x for x in packet.pending_choices if x["kind"] == "handler_keep"), None
                    ),
                },
            )
            return {"id": identity, "request_id": packet.request_id}

        return self.store._write(
            viewer,
            key,
            "gm.frame",
            {**binding, "task": task.model_dump(mode="json")},
            operation,
            authorize=authorize,
        )

    def _framed_packet(
        self, c: Connection, viewer: GuildViewer, scene: str, frame_id: str
    ) -> tuple[GMPacket, dict[str, Any], dict[str, Any]]:
        record = self._saved(c, frame_id, "gm_task_frame", scene)
        packet, native = self._packet(
            c, viewer, record, TaskFrame.model_validate_json(json.dumps(record["task"]))
        )
        if packet.request_id != record["request_id"]:
            raise WorkflowError(
                "STALE_GM_FRAME: source, choices, consent or context changed; reframe."
            )
        return packet, native, record

    def evaluate(self, viewer: GuildViewer, key: str, scene: str, frame_id: str) -> dict[str, Any]:
        semantic = {"scene_id": scene, "frame_id": frame_id}
        with self.store.transaction() as c:
            self._gm(c, viewer, scene)
            old = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == self.store.campaign_id,
                        t.commands.c.interaction_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["request_hash"] != _digest(
                    {"actor": viewer.user_id, "kind": "gm.evaluate", "payload": semantic}
                ):
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: this GM request changed.")
                return self.private(viewer, scene, json.loads(old["outcome_json"])["id"])
            packet, _, _ = self._framed_packet(c, viewer, scene, frame_id)
        try:
            proposal = GMProposal.model_validate_json(
                self.provider.propose(packet).model_dump_json()
            )
            validate_proposal(packet, proposal)
        except Exception:
            raise WorkflowError(
                "INVALID_GM_PROPOSAL: bindings, evidence, coverage or authority failed."
            ) from None

        def authorize(c: Connection) -> None:
            self._gm(c, viewer, scene)

        def operation(c: Connection) -> dict[str, str]:
            current, _, _ = self._framed_packet(c, viewer, scene, frame_id)
            if current != packet:
                raise WorkflowError("STALE_GM_PROPOSAL: generation changed no campaign state.")
            identity = "gm-proposal:" + str(uuid4())
            self._save(
                c,
                {
                    "id": identity,
                    "record_type": "gm_provider_proposal",
                    "scene_id": scene,
                    "frame_id": frame_id,
                    "owner_id": str(viewer.user_id),
                    "proposal": proposal.model_dump(mode="json"),
                    "external_tokens": 0,
                    "external_cost": 0,
                },
            )
            return {"id": identity}

        result = self.store._write(
            viewer, key, "gm.evaluate", semantic, operation, authorize=authorize
        )
        return self.private(viewer, scene, result["id"])

    def private(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gm(c, viewer, scene)
            return self._saved(c, identity, "gm_provider_proposal", scene)

    def view(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        """Never returns private reasoning, task annotations or the GM envelope."""
        with self.store.engine.connect() as c:
            self.observer._scope()
            self.observer._scene(c, scene, viewer)
            record = self._saved(c, identity, "gm_provider_proposal", scene)
            framed = self._saved(c, record["frame_id"], "gm_task_frame", scene)
            native = native_snapshot(
                c,
                self.observer,
                scene,
                framed["source_id"],
                framed["source_revision"],
                framed["action_id"],
            )
            proposal = GMProposal.model_validate_json(json.dumps(record["proposal"]))
            # The existing native projection enforces party/target privacy independently.
            native_view = self.observer.game.inspect(viewer, framed["action_id"])
            confirmed = False
            original = framed.get("keep_choice")
            if original:
                raw = c.scalar(
                    sa.select(t.m2["m2_responses"].c.answer_json).where(
                        t.m2["m2_responses"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_responses"].c.choice_id == original["id"],
                    )
                )
                if raw:
                    answer = json.loads(raw)
                    confirmed = answer.get("text") == self._confirmation_text(
                        identity, proposal
                    ) and answer.get("flag") == (proposal.verdict == "enough")
            try:
                current, _ = self._packet_internal(c, framed)
                current_request = current.request_id == proposal.request_id
            except WorkflowError:
                current_request = False
            text = "GM proposal: " + proposal.verdict.replace("_", " ") + ". "
            if native["stage"] == "complete":
                text += (
                    "The native Play is complete; separately required follow-ups remain explicit."
                )
            elif proposal.verdict in ("enough", "not_enough"):
                text += (
                    "This is Keep's goal assessment, pending its original controller confirmation."
                )
            else:
                text += (
                    "Preserve the actual outstanding owner choices or obtain goal clarification."
                )
            return {
                "id": identity,
                "verdict": proposal.verdict,
                "text": text,
                "play": native["action"]["data"]["play"],
                "native": native_view,
                "pending_choices": [
                    {"kind": x["kind"], "your_choice": True}
                    if x["actor_id"] == str(viewer.user_id)
                    else {"your_choice": False}
                    for x in native["pending"]
                ],
                "followups": [
                    {"kind": x["kind"], "your_work": True}
                    if x["owner"] == str(viewer.user_id)
                    else {"your_work": False}
                    for x in native["followups"]
                ],
                "immediate_complete": native["stage"] == "complete",
                "fully_resolved": native["stage"] == "complete" and not native["followups"],
                "confirmed": confirmed,
                "proposal_current": current_request,
                "can_confirm": current_request
                and native["stage"] == "awaiting_keep_ruling"
                and any(
                    x["kind"] == "handler_keep" and x["actor_id"] == str(viewer.user_id)
                    for x in native["pending"]
                )
                and proposal.verdict in ("enough", "not_enough"),
            }

    def confirm_keep(
        self, viewer: GuildViewer, key: str, scene: str, identity: str
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.observer._scene(c, scene, viewer)
            record = self._saved(c, identity, "gm_provider_proposal", scene)
            framed = self._saved(c, record["frame_id"], "gm_task_frame", scene)
            proposal = GMProposal.model_validate_json(json.dumps(record["proposal"]))
            if proposal.verdict not in ("enough", "not_enough"):
                raise WorkflowError(
                    "NO_GM_CONFIRMATION: this proposal supplies no native Keep ruling."
                )
            # No GM role is impersonated. Stored packet is reconstructed using its
            # original configured facilitator only via a pure internal packet path below.
            choices = t.m2["m2_choices"]
            original = framed.get("keep_choice")
            if not original:
                raise WorkflowError("NO_GM_CONFIRMATION: no original native ruling choice.")
            choice = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.id == original["id"],
                        choices.c.action_id == framed["action_id"],
                        choices.c.kind == "handler_keep",
                    )
                )
                .mappings()
                .first()
            )
            if not choice or choice["actor_id"] != str(viewer.user_id):
                raise WorkflowError(
                    "CHOICE_NOT_OWNED: only the original Handler controller can confirm."
                )
            choice_id, choice_revision = choice["id"], original["revision"]
        native_key = "gm-confirm:" + identity + ":" + key

        def guard(c: Connection) -> None:
            self.observer._scene(c, scene, viewer)
            self.observer.game.unpaused(c)
            native = native_snapshot(
                c,
                self.observer,
                scene,
                framed["source_id"],
                framed["source_revision"],
                framed["action_id"],
            )
            if c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == native_key,
                )
            ):
                return  # Native inbox still verifies the original exact answer hash.
            # Reconstruct full current evidence under internal server authority, never
            # by creating a GuildViewer for a different account.
            current, _ = self._packet_internal(c, framed)
            if (
                current.request_id != proposal.request_id
                or native["stage"] != "awaiting_keep_ruling"
            ):
                raise WorkflowError("STALE_GM_CONFIRMATION: obtain a fresh source-bound proposal.")
            validate_proposal(current, proposal)

        return self.observer.game.respond(
            viewer,
            native_key,
            choice_id,
            choice_revision,
            ChoiceAnswer(
                flag=proposal.verdict == "enough",
                text=self._confirmation_text(identity, proposal),
            ),
            source_authorize=guard,
        )

    @staticmethod
    def _confirmation_text(identity: str, proposal: GMProposal) -> str:
        return "Confirmed GM proposal " + identity + ": " + proposal.verdict

    def _packet_internal(
        self, c: Connection, framed: dict[str, Any]
    ) -> tuple[GMPacket, dict[str, Any]]:
        # This is used only after native choice ownership has been proved, and has
        # no wire/API authority flag. _packet's common path handles the same proof.
        return self._packet(
            c, None, framed, TaskFrame.model_validate_json(json.dumps(framed["task"]))
        )
