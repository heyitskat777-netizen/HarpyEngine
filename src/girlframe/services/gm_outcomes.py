"""Private GM proposals, original-owner confirmations and atomic native consumers."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.ai.gm_outcomes import (
    BattleFacts,
    HandlerOutcome,
    KeepOutcome,
    OutcomeNarration,
    OutcomePacket,
    OutcomeProposal,
    OutcomeProvider,
    SensorAnswers,
    TableOutcome,
)
from girlframe.ai.gm_protocol import Evidence, TaskFrame
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
from girlframe.engine.m3_battle_state import Context
from girlframe.services.director_context import DirectorContextService, next_contribution_ordinal
from girlframe.services.director_observation import _digest
from girlframe.services.gm_outcome_compile import CHOICES, sensor_answer_contract, validate
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

SourceKind = Literal["choice", "battle", "handler_grant", "table", "completed"]


class GMOutcomeService:
    def __init__(
        self,
        context: DirectorContextService,
        provider: OutcomeProvider | None = None,
        *,
        require_response_scope: bool = False,
    ):
        self.context, self.observer = context, context.observations
        self.game, self.store, self.provider = self.observer.game, context.store, provider
        self.require_response_scope = require_response_scope
        from girlframe.services.director_responses import DirectorResponseService

        self.responses = DirectorResponseService(self)

    def _scope(
        self, c: Connection, viewer: GuildViewer, scene: str, *, gm: bool = False
    ) -> dict[str, Any]:
        self.observer._scope()
        row = self.observer._scene(c, scene, viewer)
        policy = self.observer._state(c, scene)
        if policy.policy.mode != "shadow" or not self.observer._consented(c, row, policy):
            raise WorkflowError("OBSERVATION_DISABLED: retain current synthetic scene consent.")
        self.game.unpaused(c)
        if gm:
            self.context._build(c, viewer, scene, actor=None)
        return row

    def _record(self, c: Connection, scene: str, identity: str, kind: str) -> dict[str, Any]:
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
            raise WorkflowError("OUTCOME_UNAVAILABLE: no accessible source-bound record.")
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

    def _snapshot(
        self, c: Connection, scene: str, kind: SourceKind, identity: str, frame: TaskFrame | None
    ) -> OutcomePacket:
        scene_row = self.observer._scene(c, scene)
        canon = load_state(c, self.store.campaign_id)
        data: dict[str, Any]
        action = None
        if kind == "choice":
            table = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == identity,
                        table.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if not row or row["kind"] not in CHOICES:
                raise WorkflowError(
                    "UNSUPPORTED_GM_CHOICE: use a real implemented GM semantic stage."
                )
            action = self.game.action(c, row["action_id"])
            if action["scene_id"] != scene or action["state"] in ("complete", "aborted"):
                raise WorkflowError("STALE_GM_SOURCE: recover the actual source action.")
            from girlframe.services.m3_princess_sex import decision_author

            author = decision_author(self.game, c, canon, action, dict(row))
            owner = str(author if author is not None else row["actor_id"])
            data = {
                "choice": dict(row),
                "choice_body": json.loads(row["body_json"]),
                "action": action,
            }
            operation = CHOICES[row["kind"]]
            if operation == "table":
                from girlframe.services.gm_table_outcomes import table_source

                _, source_owner = table_source(self.game, c, canon, scene, action)
                if source_owner != owner:
                    raise WorkflowError("STALE_TABLE_GM: recover the actual pending GM choice.")
            receipt = action["data"].get("receipt")
            if receipt:
                receipts = t.m2["m2_receipts"]
                raw = c.scalar(
                    sa.select(receipts.c.body_json).where(
                        receipts.c.campaign_id == self.store.campaign_id,
                        receipts.c.action_id == action["id"],
                    )
                )
                if not raw or json.loads(raw) != receipt:
                    raise WorkflowError("UNPROVEN_GM_RECEIPT: retain the original native receipt.")
            if operation == "keep" and (
                action["data"].get("play") != "keep_your_head"
                or not {"positive", "negative"} <= action["data"]["result"].keys()
            ):
                raise WorkflowError("UNPROVEN_KEEP: require actual committed traits.")
        elif kind == "battle":
            context = next(
                (
                    Context.model_validate_json(x["body"])
                    for x in reversed(canon.facts)
                    if x.get("kind") == "battle_context" and x.get("id") == identity
                ),
                None,
            )
            if context is None or context.scene != scene or context.state != "proposed":
                raise WorkflowError("STALE_BATTLE_SOURCE: use an actual proposed declaration.")
            data, owner, operation = (
                {"battle": context.model_dump(mode="json")},
                str(context.adjudicator),
                "battle_facts",
            )
        elif kind == "handler_grant":
            from girlframe.engine.m3_handler_plays import available_plays
            from girlframe.services.m3_handler_plays import _authority, _source

            _, grant = _source(c, self.game, identity)
            _authority(c, self.game, canon, grant)
            # Non-scene grants must be connected through their actual source action.
            action = self.game.action(c, grant.source_action) if grant.source_action else None
            campaign_targets = (
                grant.scope.campaign_context
                and bool(grant.target_controllers)
                and all(
                    str(x) in {str(u) for u in scene_row["participants"]}
                    for x in grant.target_controllers.values()
                )
            )
            if grant.clause.startswith("tracker:"):
                from girlframe.services.m3_tracker_implants import prove_tracker_play

                campaign_targets = campaign_targets and (
                    prove_tracker_play(self.game, c, canon, grant).cast.id == scene
                )
            if grant.state != "pending" or not (
                grant.scope.scene_id == scene
                or campaign_targets
                or action
                and action["scene_id"] == scene
            ):
                raise WorkflowError("STALE_HANDLER_GRANT: use its actual pending scene source.")
            data, owner, operation = (
                {
                    "grant": grant.model_dump(mode="json"),
                    "allowed_plays": list(available_plays(canon, grant)),
                },
                str(grant.chooser_controller),
                "handler_effect",
            )
        elif kind == "completed":
            from girlframe.services.gm_table_outcomes import gm_owner

            action = self.game.action(c, identity)
            if action["scene_id"] != scene or action["state"] != "complete":
                raise WorkflowError("OUTCOME_NOT_COMPLETE: preserve native pending work.")
            data, owner, operation = {"action": action}, str(gm_owner(canon, action)), "narration"
        else:
            from girlframe.services.gm_table_outcomes import table_source

            action = self.game.action(c, identity)
            data, owner = table_source(self.game, c, canon, scene, action)
            operation = "table"
        if owner not in {str(x) for x in scene_row["participants"]}:
            raise WorkflowError("GM_SOURCE_OWNER_UNAVAILABLE: recover the actual scene controller.")
        data["state_revision"] = canon.revision
        if operation == "sensors":
            data["answer_contract"] = sensor_answer_contract(data)
        evidence = [
            Evidence(
                id="source",
                value=json.loads(json.dumps({"kind": kind, "id": identity})),
                audience="gm",
            ),
            Evidence(id="native", value=data, audience="gm"),
        ]
        if operation == "keep":
            assert action is not None
            evidence.append(
                Evidence(
                    id="traits",
                    value={key: action["data"]["result"][key] for key in ("positive", "negative")},
                    audience="actor",
                )
            )
        for i, fact in enumerate(canon.facts):
            if fact.get("kind") == "scene_condition":
                evidence.append(
                    Evidence(
                        id=f"condition:{i}:" + _digest(fact)[:16],
                        value=json.loads(json.dumps(fact)),
                        audience="gm",
                    )
                )
        history_query = self.observer._pending(scene, 0, include_handled=True)
        history_total = (
            c.scalar(sa.select(sa.func.count()).select_from(history_query.subquery())) or 0
        )
        history = [
            Observation.model_validate_json(row["body_json"]).model_dump(mode="json")
            for row in c.execute(
                history_query.order_by(t.director["inputs"].c.sequence.desc()).limit(100)
            ).mappings()
        ]
        references = self.context._current(c, scene)
        evidence.extend(
            Evidence(id="reference:" + r.id, value=r.model_dump(mode="json"), audience="gm")
            for r in references
        )
        if frame is not None:
            known = {e.id for e in evidence if e.id.startswith("condition:")}
            if (
                len({d.id for d in frame.demands}) != len(frame.demands)
                or len({p.evidence_id for p in frame.prerequisites}) != len(frame.prerequisites)
                or any(p.evidence_id not in known for p in frame.prerequisites)
            ):
                raise WorkflowError(
                    "INVALID_GM_FRAME: use distinct demands and actual prerequisite facts."
                )
            if self.require_response_scope:
                data["response_scope_required"] = True
            if frame.response_scope == "other":
                from girlframe.engine.m3_actors import resolve
                from girlframe.engine.m3_cast import validate_role
                from girlframe.services.m3_actors import profiles

                if frame.response_target is None:
                    raise WorkflowError("INVALID_RESPONSE_TARGET: bind the actual affected actor.")
                try:
                    target = resolve(
                        canon,
                        frame.response_target,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    cast = next((x for x in canon.scene_casts if x.id == scene and x.open), None)
                    if not target.alive or target.controller not in scene_row["participants"]:
                        raise ValueError("Unavailable target")
                    if cast is not None:
                        validate_role(cast, target)
                    elif target.ref.kind == "npc":
                        raise ValueError("Explicit NPC casting required")
                except ValueError:
                    raise WorkflowError(
                        "INVALID_RESPONSE_TARGET: recover current target and casting."
                    ) from None
                data["response_actor"] = target.ref.model_dump(mode="json")
                data["response_controller"] = str(target.controller)
                data["response_authorized"] = (
                    target.ref.kind == "npc" and str(target.controller) == owner
                )
            elif frame.response_target is not None or frame.response_request is not None:
                raise WorkflowError(
                    "INVALID_RESPONSE_TARGET: select other scope for an affected actor."
                )
            if frame.response_request is not None:
                self.responses.bind(c, scene, kind, identity, owner, frame, data, evidence)
            if frame.intent_request is not None:
                self.responses.bind_intent(c, scene, kind, identity, frame, evidence)
        records = {}
        for name in ("m3_missions", "m3_off_duty", "m3_required_work"):
            table = t.m3[name]
            records[name] = [
                dict(r)
                for r in c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                    )
                    .order_by(*table.primary_key.columns)
                ).mappings()
            ]
        from girlframe.services.director_time import scene_time

        time = scene_time(c, self.store.campaign_id, scene)
        packet = OutcomePacket(
            request_id="pending",
            scene_id=scene,
            source_kind=kind,
            source_id=identity,
            operation=operation,
            owner_id=owner,
            evidence=tuple(evidence),
            frame=frame,
            native=data,
            gm_private_context={
                "canonical": canon.model_dump(mode="json"),
                "history": list(reversed(history)),
                "history_omitted": max(0, history_total - len(history)),
                "records": json.loads(json.dumps(records)),
                "references": [r.model_dump(mode="json") for r in references],
                "guard": self.observer._guard(c, scene_row, self.observer._state(c, scene)),
                **({"fictional_time": time.model_dump(mode="json")} if time else {}),
            },
        )
        return packet.model_copy(update={"request_id": _digest(packet.model_dump(mode="json"))})

    def open(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        source_kind: SourceKind,
        source_id: str,
        frame: TaskFrame | None = None,
    ) -> dict[str, Any]:
        if source_kind not in ("choice", "battle", "handler_grant", "table", "completed"):
            raise WorkflowError("UNSUPPORTED_GM_SOURCE: choose an implemented native source.")
        frame = TaskFrame.model_validate_json(frame.model_dump_json()) if frame else None

        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene, gm=True)

        def operation(c: Connection) -> dict[str, Any]:
            packet = self._snapshot(c, scene, source_kind, source_id, frame)
            value = {
                "id": "gm-request:" + str(uuid4()),
                "record_type": "gm_outcome_request",
                "scene_id": scene,
                "packet": packet.model_dump(mode="json"),
            }
            self._save(c, value)
            return {"id": value["id"], "request_id": packet.request_id}

        return self.store._write(
            viewer,
            key,
            "gm.outcome_open",
            {
                "scene": scene,
                "kind": source_kind,
                "source": source_id,
                "frame": frame.model_dump(mode="json") if frame else None,
            },
            operation,
            authorize=authorize,
        )

    def packet(self, viewer: GuildViewer, scene: str, request: str) -> OutcomePacket:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            return OutcomePacket.model_validate_json(
                json.dumps(self._record(c, scene, request, "gm_outcome_request")["packet"])
            )

    def _current(self, c: Connection, packet: OutcomePacket) -> None:
        current = self._snapshot(
            c, packet.scene_id, packet.source_kind, packet.source_id, packet.frame
        )
        if current != packet:
            raise WorkflowError("STALE_GM_OUTCOME: source, context or authority changed; reopen.")

    def feedback(
        self, viewer: GuildViewer, scene: str, request: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        """Private dry-run validation; never includes raw input or applies a proposal."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            packet = OutcomePacket.model_validate_json(
                json.dumps(self._record(c, scene, request, "gm_outcome_request")["packet"])
            )
            self._current(c, packet)
        try:
            candidate = OutcomeProposal.model_validate_json(json.dumps(raw))
        except ValidationError as error:
            return {
                "valid": False,
                "errors": [
                    {
                        "code": "SCHEMA_VALIDATION",
                        "field": ".".join(map(str, issue["loc"])),
                        "message": "Use the exported typed field contract.",
                    }
                    for issue in error.errors(include_input=False)
                ],
            }
        try:
            validate(packet, candidate)
        except ValueError as error:
            message = str(error)
            code = "RESPONSE_OWNERSHIP" if "RESPONSE_OWNERSHIP" in message else "INVALID_PROPOSAL"
            field = "frame.response_scope" if code == "RESPONSE_OWNERSHIP" else "decision"
            if not {"source", "native"} <= set(candidate.cited_evidence):
                code, field, message = (
                    "MISSING_CITATION",
                    "cited_evidence",
                    "Include source and native citations.",
                )
            elif isinstance(candidate.decision, SensorAnswers) and packet.operation == "sensors":
                contract = sensor_answer_contract(packet.native)
                code, field = "SENSOR_INPUT_CONTRACT", "decision"
                message = (
                    "Use answer keys "
                    + ", ".join(contract["answers"])
                    + " in native question order. "
                )
                message += (
                    "This branch requires incomplete_information or punishment_later."
                    if contract["consequence_required"]
                    else "This branch requires consequence=null."
                )
            return {"valid": False, "errors": [{"code": code, "field": field, "message": message}]}
        return {"valid": True, "errors": []}

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        request: str,
        proposal: OutcomeProposal | None = None,
    ) -> dict[str, Any]:
        semantic = {
            "scene": scene,
            "request": request,
            "manual": proposal.model_dump(mode="json") if proposal else None,
        }
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
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
                    {"actor": viewer.user_id, "kind": "gm.outcome_propose", "payload": semantic}
                ):
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: this proposal command changed.")
                return self.private(viewer, scene, json.loads(old["outcome_json"])["id"])
            packet = OutcomePacket.model_validate_json(
                json.dumps(self._record(c, scene, request, "gm_outcome_request")["packet"])
            )
            self._current(c, packet)
        try:
            if proposal is None:
                if self.provider is None:
                    raise ValueError("No offline/manual provider supplied")
                proposal = self.provider.propose(packet)
            candidate = OutcomeProposal.model_validate_json(proposal.model_dump_json())
            validate(packet, candidate)
        except Exception:
            raise WorkflowError(
                "INVALID_GM_OUTCOME: obtain a typed, evidence-bound proposal."
            ) from None

        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene, gm=True)

        def operation(c: Connection) -> dict[str, Any]:
            self._current(c, packet)
            value = {
                "id": "gm-outcome:" + str(uuid4()),
                "record_type": "gm_outcome_proposal",
                "scene_id": scene,
                "request": request,
                "proposal": candidate.model_dump(mode="json"),
            }
            self._save(c, value)
            return {"id": value["id"]}

        saved = self.store._write(
            viewer, key, "gm.outcome_propose", semantic, operation, authorize=authorize
        )
        return self.private(viewer, scene, saved["id"])

    def private(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            return self._record(c, scene, identity, "gm_outcome_proposal")

    def _load(
        self, c: Connection, scene: str, identity: str
    ) -> tuple[OutcomePacket, OutcomeProposal]:
        saved = self._record(c, scene, identity, "gm_outcome_proposal")
        request = self._record(c, scene, saved["request"], "gm_outcome_request")
        return (
            OutcomePacket.model_validate_json(json.dumps(request["packet"])),
            OutcomeProposal.model_validate_json(json.dumps(saved["proposal"])),
        )

    def owner_review(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        """Explicit OOC review of intended consumer fields; never a Handler persona prompt."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            packet, proposal = self._load(c, scene, identity)
            if packet.owner_id != str(viewer.user_id):
                raise WorkflowError(
                    "GM_OUTCOME_NOT_OWNED: only the original consumer owner may confirm."
                )
            return {
                "id": identity,
                "operation": packet.operation,
                "decision": proposal.decision.model_dump(
                    mode="json",
                    exclude={"assessments"}
                    if isinstance(proposal.decision, KeepOutcome)
                    else set(),
                ),
                "notice": "Review intended disclosures and effects. "
                "Private GM reasoning is excluded.",
            }

    def confirm(self, viewer: GuildViewer, key: str, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            packet, proposal = self._load(c, scene, identity)
            if packet.owner_id != str(viewer.user_id):
                raise WorkflowError("GM_OUTCOME_NOT_OWNED: retain the actual native source owner.")
        native_key = "gm-outcome:" + identity + ":" + key

        def guard(c: Connection) -> None:
            self._scope(c, viewer, scene)
            if c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == native_key,
                )
            ):
                return
            self._current(c, packet)
            validate(packet, proposal)

        answer = validate(packet, proposal)
        native: Any = packet.native
        with self.store.source_guard(guard):
            if packet.source_kind == "choice":
                if answer is None:
                    raise WorkflowError("GM_CLARIFICATION_REQUIRED: no native ruling supplied.")
                row = native["choice"]
                return self.game.respond(viewer, native_key, row["id"], row["revision"], answer)
            if isinstance(proposal.decision, BattleFacts):
                from girlframe.services.m3_battle import BattleService

                return BattleService(self.store).confirm(
                    viewer,
                    native_key,
                    native["state_revision"],
                    packet.source_id,
                    **proposal.decision.model_dump(exclude={"kind"}, mode="python"),
                )
            if isinstance(proposal.decision, HandlerOutcome):
                from girlframe.services.m3_handler_plays import HandlerPlayService

                return HandlerPlayService(self.store).submit(
                    viewer,
                    native_key,
                    packet.source_id,
                    native["state_revision"],
                    proposal.decision.play,
                    proposal.decision.effect,
                )
            if isinstance(proposal.decision, TableOutcome):
                from girlframe.services.gm_table_outcomes import adjudicate

                return adjudicate(
                    self.context,
                    viewer,
                    native_key,
                    scene,
                    packet.source_id,
                    native["state_revision"],
                    proposal.decision,
                )
            if isinstance(proposal.decision, OutcomeNarration):

                def authorize(c: Connection) -> None:
                    self._scope(c, viewer, scene, gm=True)
                    self.game.inspect(viewer, packet.source_id)

                def operation(c: Connection) -> dict[str, Any]:
                    assert isinstance(proposal.decision, OutcomeNarration)
                    record = {
                        "id": "gm-narration:" + str(uuid4()),
                        "record_type": "gm_outcome_narration",
                        "scene_id": scene,
                        "action_id": packet.source_id,
                        "proposal_id": identity,
                        "audience_ids": sorted(
                            str(x)
                            for x in self._scope(c, viewer, scene)["participants"]
                            if str(x)
                            in {str(u) for u in native["action"]["data"].get("participants", [])}
                        ),
                        "ordinal": next_contribution_ordinal(c, self.store.campaign_id, scene),
                        "text": proposal.decision.text,
                        "effect_refs": list(proposal.decision.effect_refs),
                        "canon_effects": False,
                    }
                    self._save(c, record)
                    return {"id": record["id"], "canon_effects": False}

                return self.store._write(
                    viewer,
                    native_key,
                    "gm.outcome_narrated",
                    {"proposal": identity},
                    operation,
                    authorize=authorize,
                    auto_audit=False,
                )
        raise WorkflowError("UNSUPPORTED_GM_CONSUMER: no permitted native operation.")

    def contribution(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            record = self._record(c, scene, identity, "gm_outcome_narration")
            native = self.game.inspect(viewer, record["action_id"])
            return {
                "id": identity,
                "text": record["text"],
                "ordinal": record.get("ordinal", 0),
                "native": native,
                "canon_effects": False,
                "publication": "synthetic_projection_only",
            }
