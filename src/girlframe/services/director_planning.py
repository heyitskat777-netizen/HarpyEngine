"""Review connected character opportunities inside the existing Director ledger."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.conversation import RULES_IN_PROSE
from girlframe.ai.director import KnowledgeReference
from girlframe.ai.director_fronts import Front, PortrayalMove
from girlframe.ai.director_planning import (
    DirectorPlanningDecision,
    DirectorPlanningPacket,
    DirectorPlanningProvider,
    PlannedMove,
    PlanningActor,
    PlanningFront,
    PlanningKind,
    PlanningSource,
)
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.campaign_difficulty import opening
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_observation import _digest
from girlframe.services.director_reactions import DirectorReactionService
from girlframe.services.director_time import scene_time
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RECORD = "director_ensemble_plan"
REVIEW = "director_ensemble_review"


class DirectorPlanningService:
    def __init__(
        self, context: DirectorContextService, provider: DirectorPlanningProvider | None = None
    ):
        self.context, self.store, self.observer = context, context.store, context.observations
        self.provider = provider
        self.reactions = DirectorReactionService(context)
        self.dossiers = DirectorDossierService(context)

    def _scene(self, c: Connection, scene: str, *, closed: bool = False) -> dict[str, Any]:
        self.observer._scope()
        if not self.observer.activity_shadow:
            raise WorkflowError("PLANNING_UNAVAILABLE: use synthetic Activity review.")
        row = self.observer._scene(c, scene, allow_closed=closed)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: retain current planning consent.")
        self.observer.game.unpaused(c)
        self.observer.game.scene_unpaused(c, scene)
        return row

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        self.store.administrator(viewer)
        self.observer._scene(c, scene, viewer)
        self._scene(c, scene)

    def _closeout(self, c: Connection, origin: str) -> str | None:
        ledger = t.director_context["shadow"]
        event = t.events
        return c.scalar(
            sa.select(event.c.id)
            .join(
                ledger,
                (event.c.campaign_id == ledger.c.campaign_id)
                & (ledger.c.id == "handler-closeout:" + event.c.id),
            )
            .where(
                ledger.c.campaign_id == self.store.campaign_id,
                ledger.c.scene_id == origin,
                event.c.kind == "m2.scene_closed",
            )
            .order_by(event.c.seq.desc())
            .limit(1)
        )

    def _source_refs(
        self,
        c: Connection,
        scene: str,
        source: PlanningSource,
        refs: tuple[KnowledgeReference, ...],
    ) -> tuple[str, ...]:
        original = self._scene(c, source.scene, closed=True)
        if source.kind == "closeout":
            if (
                original["open"]
                or not source.source
                or self._closeout(c, source.scene) != source.source
            ):
                raise WorkflowError("PLANNING_SOURCE: use an approved native closeout.")
            return tuple(ref.id for ref in refs if ref.origin_scene == source.scene)
        self.context._approved_outcome(c, source.scene, source.source, allow_closed=True)
        return tuple(
            ref.id
            for ref in refs
            if ref.source_id == source.source and (ref.origin_scene or scene) == source.scene
        )

    def _fronts(
        self,
        c: Connection,
        scene: str,
        refs: tuple[KnowledgeReference, ...],
        controllers: dict[ActorRef, int],
    ) -> tuple[PlanningFront, ...]:
        from girlframe.services.director_fronts import evidence_refs, records

        origins = {
            (ref.origin_scene or scene, ref.origin_reference or ref.id): ref.id for ref in refs
        }
        eligible = []
        for front in records(load_state(c, self.store.campaign_id)):
            if front.status not in ("active", "ready"):
                continue
            candidates = tuple(
                actor
                for actor, controller in controllers.items()
                if self._owns_front(front, actor, controller)
            )
            if not candidates:
                continue
            try:
                self._scene(c, front.scene_id, closed=True)
            except WorkflowError:
                continue
            if (
                self.observer._state(c, front.scene_id).consent_generation
                != front.consent_generation
            ):
                continue
            prior = {
                ref.id: (ref.origin_scene or front.scene_id, ref.origin_reference or ref.id)
                for ref in self.context._references(c, front.scene_id)
            }
            known = tuple(
                dict.fromkeys(
                    origins[key]
                    for item in evidence_refs(front)
                    if item.kind == "reference"
                    and (key := prior.get(item.id, (front.scene_id, item.id))) in origins
                )
            )
            if known:
                eligible.append(PlanningFront(front=front, evidence=known, actors=candidates))
        return tuple(eligible[-12:])

    @staticmethod
    def _owns_front(front: Front, actor: ActorRef, controller: int) -> bool:
        if actor.kind == "handler":
            return front.confirmed_by == controller and any(
                move.portrayed_by == actor and move.trigger is None for move in front.possible_moves
            )
        return (
            actor.kind == "npc"
            and front.subject_controllers.get("npc:" + actor.entity) == controller
            and any(
                (item.subject.kind, item.subject.id) == ("npc", actor.entity)
                for item in front.participants
            )
        )

    def _planned_roles(self, c: Connection, scene: str) -> set[ActorRef]:
        roles = set(self.dossiers.activity_pilots(c, scene))
        approved = opening(c, self.store.campaign_id)
        if approved is not None and approved.handler_control == "ai":
            row = self.observer._scene(c, scene)
            roles.update(
                role.ref
                for role in self.dossiers.knowledge._actor_views(c, row)
                if role.ref.kind == "handler" and role.controller == approved.handler
            )
        return roles

    def _snapshot(
        self, c: Connection, scene: str, source: PlanningSource
    ) -> DirectorPlanningPacket:
        from girlframe.services.activity_scene_opening import ActivitySceneOpening

        row = self._scene(c, scene)
        refs = self.context._current(c, scene)
        trigger = self._source_refs(c, scene, source, refs)
        if not trigger:
            raise WorkflowError(
                "PLANNING_SOURCE: approve carry or record the actual outcome first."
            )
        actors = []
        planned_roles = self._planned_roles(c, scene)
        controllers = {}
        for role in self.dossiers.knowledge._actor_views(c, row):
            if role.ref in planned_roles:
                controllers[role.ref] = role.controller
            own = self.dossiers._role_packet(
                c, scene, role.ref, omit_stale_portrayal=True, activity_pilot=role.ref.kind == "npc"
            )
            actors.append(
                PlanningActor(
                    actor=role.ref,
                    label=role.label,
                    profile=own.profile,
                    state=own.state,
                    known_refs=own.source_refs,
                )
            )
        cast = tuple(actors)
        fronts = self._fronts(c, scene, refs, controllers)
        if not fronts:
            raise WorkflowError("PLANNING_SOURCE: no current sourced Front applies in this scene.")
        # Ordinary talk and wall-clock time do not change planning evidence.
        packet = DirectorPlanningPacket(
            scene=scene,
            opening=ActivitySceneOpening(self.context).current(c, row),
            fictional_time=scene_time(c, self.store.campaign_id, scene),
            source=source,
            trigger_refs=trigger,
            references=refs,
            actors=cast,
            fronts=fronts,
            revision="",
        )
        revision = _digest((packet.model_dump(mode="json"), self._binding(c, scene, source.scene)))
        return packet.model_copy(update={"revision": revision})

    def _binding(self, c: Connection, scene: str, origin: str) -> str:
        from girlframe.services.activity_scene_opening import opening_head

        roles = [
            (
                self.observer._state(c, identity).consent_generation,
                self.observer._scene(c, identity, allow_closed=True)["binding_event"],
            )
            for identity in (scene, origin)
        ]
        position = scene_time(c, self.store.campaign_id, scene)
        opening = opening_head(c, self.store.campaign_id, scene)
        return _digest(
            (
                roles,
                opening.id if opening else None,
                position.model_dump(mode="json") if position else None,
            )
        )

    def _candidates(self, c: Connection, scene: str) -> list[PlanningSource]:
        refs = self.context._current(c, scene)
        sources: list[PlanningSource] = []
        seen = set()
        for ref in reversed(refs):
            origin = ref.origin_scene or scene
            if ref.classification == "approved_outcome" and ref.source_id.startswith(
                "gm-narration:"
            ):
                candidate = PlanningSource(
                    kind="outcome",
                    scene=origin,
                    source=ref.source_id,
                    label="Confirmed Play outcome · " + ref.text[:100],
                )
            elif ref.origin_scene and (event := self._closeout(c, origin)):
                candidate = PlanningSource(
                    kind="closeout",
                    scene=origin,
                    source=event,
                    label="Reviewed closeout · " + ref.text[:100],
                )
            else:
                continue
            key = (candidate.kind, candidate.source, candidate.scene)
            if key not in seen:
                seen.add(key)
                sources.append(candidate)
        return sources

    def _validate(self, packet: DirectorPlanningPacket, decision: DirectorPlanningDecision) -> None:
        fronts = {item.front.id: item for item in packet.fronts}
        actors = {item.actor: set(item.known_refs) for item in packet.actors}
        rationales = (decision.reasoning, *(item.why for item in decision.moves))
        connected = []
        for move in decision.moves:
            front = fronts.get(move.front)
            cited = set(move.evidence)
            known = actors.get(move.actor, set())
            if (
                front is None
                or move.actor not in front.actors
                or (move.actor.kind == "handler" and len(cited) > 3)
                or not cited <= known
                or not cited.intersection(packet.trigger_refs)
                or not cited.intersection(front.evidence)
                or RULES_IN_PROSE.search(move.text)
            ):
                raise WorkflowError(
                    "PLANNING_SCOPE: retain the eligible actor, Front and known trigger evidence."
                )
            if any(
                len(note.strip()) >= 12 and note.strip().casefold() in move.text.casefold()
                for note in rationales
            ):
                raise WorkflowError("PLANNING_SCOPE: keep private reasoning out of the move.")
            for ref in packet.references:
                if ref.id in known:
                    continue
                quote = ref.text.partition(": ")
                private_text = (
                    quote[2]
                    if quote[0] in ("Reported claim", "Established world", "Confirmed outcome")
                    else ref.text
                )
                if len(private_text) >= 12 and private_text.casefold() in move.text.casefold():
                    raise WorkflowError("PLANNING_SCOPE: keep unshared evidence out of the move.")
            connected.append((cited, {entry.subject for entry in front.front.participants}))
        if len(connected) > 1:
            known, subjects = connected.pop(0)
            while connected:
                linked = [
                    (refs, roles) for refs, roles in connected if refs & known or roles & subjects
                ]
                if not linked:
                    raise WorkflowError(
                        "PLANNING_SCOPE: cite an actual connection between the Fronts."
                    )
                for refs, roles in linked:
                    known |= refs
                    subjects |= roles
                    connected.remove((refs, roles))

    @staticmethod
    def _source_key(source: PlanningSource) -> tuple[str, str, str]:
        return source.kind, source.scene, source.source

    def _read(self, c: Connection, scene: str, identity: str) -> dict[str, Any] | None:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        return dict(json.loads(raw)) if raw else None

    def _status(self, c: Connection, scene: str, record: dict[str, Any]) -> str:
        review = self._read(c, scene, record["id"] + ":review")
        try:
            if review and review["decision"] == "approve":
                self._approved_refs(c, scene, record)
            else:
                source = PlanningSource.model_validate(record["source"])
                if self._snapshot(c, scene, source).revision != record["revision"]:
                    return "stale"
        except WorkflowError:
            return "stale"
        return (
            ("approved" if review["decision"] == "approve" else "rejected") if review else "pending"
        )

    def _records(self, c: Connection, scene: str) -> list[dict[str, Any]]:
        table = t.director_context["shadow"]
        return [
            dict(json.loads(raw))
            for raw in c.scalars(
                sa.select(table.c.body_json)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type") == RECORD,
                )
                .order_by(table.c.id)
            )
        ]

    def work(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        if not self.observer.activity_shadow:
            return {"enabled": False, "sources": [], "items": []}
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._scope(c, viewer, scene)
            records = [(item, self._status(c, scene, item)) for item in self._records(c, scene)]
            seen = {
                self._source_key(PlanningSource.model_validate(item["source"]))
                for item, status in records
                if status != "stale"
            }
            sources = []
            if self.provider is not None:
                for source in self._candidates(c, scene):
                    if self._source_key(source) in seen:
                        continue
                    try:
                        self._snapshot(c, scene, source)
                    except WorkflowError:
                        continue
                    sources.append(source.model_dump(mode="json"))
                    if len(sources) == 4:
                        break
            return {
                "enabled": self.provider is not None or bool(records),
                "sources": sources,
                "items": [
                    {
                        "id": item["id"],
                        "status": status,
                        **({"label": item["source"]["label"]} if status != "stale" else {}),
                    }
                    for item, status in records[-8:]
                ],
            }

    def generate(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        kind: PlanningKind,
        source_scene: str,
        source: str,
    ) -> dict[str, Any]:
        payload = {"scene": scene, "kind": kind, "source_scene": source_scene, "source": source}
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._scope(c, viewer, scene)
            old = c.execute(
                sa.select(t.commands.c.request_hash, t.commands.c.outcome_json).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == key,
                )
            ).first()
            if old:
                if old.request_hash != _digest(
                    {"actor": viewer.user_id, "kind": RECORD, "payload": payload}
                ):
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: planning request changed.")
                return dict(json.loads(old.outcome_json))
            actual = next(
                (
                    item
                    for item in self._candidates(c, scene)
                    if (item.kind, item.scene, item.source) == (kind, source_scene, source)
                ),
                None,
            )
            if actual is None:
                raise WorkflowError("PLANNING_SOURCE: select a current consequential source.")
            for item in self._records(c, scene):
                if (
                    self._source_key(PlanningSource.model_validate(item["source"]))
                    == self._source_key(actual)
                    and self._status(c, scene, item) != "stale"
                ):
                    return {"id": item["id"], "effects_applied": False}
            packet = self._snapshot(c, scene, actual)
            identity = "director-plan:" + _digest(
                (scene, self._source_key(actual), packet.revision)
            )
        if self.provider is None:
            raise WorkflowError("PLANNING_PROVIDER_REQUIRED: use a trusted synthetic provider.")
        try:
            decision = DirectorPlanningDecision.model_validate_json(
                self.provider.propose(packet).model_dump_json()
            )
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError):
            raise WorkflowError("PLANNING_PROVIDER_UNAVAILABLE: no decision was saved.") from None
        self._validate(packet, decision)

        def save(c: Connection) -> dict[str, Any]:
            if self._snapshot(c, scene, actual).revision != packet.revision:
                raise WorkflowError("STALE_PLANNING: the scoped planning evidence changed.")
            if not self._read(c, scene, identity):
                self.reactions._save(
                    c,
                    scene,
                    identity,
                    RECORD,
                    source=actual.model_dump(mode="json"),
                    revision=packet.revision,
                    decision=decision.model_dump(mode="json"),
                    binding=self._binding(c, scene, actual.scene),
                    evidence={
                        ref.id: ref.model_dump(mode="json")
                        for ref in packet.references
                        if any(ref.id in move.evidence for move in decision.moves)
                    },
                )
            return {"id": identity, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            RECORD,
            payload,
            save,
            authorize=lambda c: self._scope(c, viewer, scene),
            auto_audit=False,
        )

    def private(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        from girlframe.services.director_fronts import records

        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self._scope(c, viewer, scene)
            item = self.reactions._get(c, scene, identity, RECORD)
            status = self._status(c, scene, item)
            view = {"id": identity, "status": status}
            if status == "stale":
                return view
            selected = {move["front"] for move in item["decision"]["moves"]}
            handler_moves = self._handler_move_review(c, scene, item, status)
            return view | {
                "decision": item["decision"],
                "evidence": {key: ref["text"] for key, ref in item["evidence"].items()},
                "fronts": {
                    front.id: front.title
                    for front in records(load_state(c, self.store.campaign_id))
                    if front.id in selected
                },
                **({"handler_moves": handler_moves} if handler_moves else {}),
            }

    @staticmethod
    def _shared_evidence(
        refs: tuple[KnowledgeReference, ...], move: PlannedMove, listener: ActorRef
    ) -> bool:
        known = {ref.id for ref in refs if {move.actor.token, listener.token} <= set(ref.known_by)}
        return set(move.evidence) <= known

    @staticmethod
    def _move_id(plan: str, move: PlannedMove) -> str:
        return _digest((plan, move.front, move.actor.token))

    def _handler_move_review(
        self, c: Connection, scene: str, item: dict[str, Any], status: str
    ) -> dict[str, Any]:
        from girlframe.services.director_fronts import DirectorFrontService

        if status not in ("pending", "approved"):
            return {}
        moves = [
            move
            for move in DirectorPlanningDecision.model_validate_json(
                json.dumps(item["decision"])
            ).moves
            if move.actor.kind == "handler"
        ]
        if not moves:
            return {}
        refs = self.context._current(c, scene)
        row = self.observer._scene(c, scene)
        pilots = [
            role
            for role in self.dossiers.knowledge._actor_views(c, row)
            if role.ref.kind == "pilot"
        ]
        fronts = DirectorFrontService(self.context)
        review: dict[str, Any] = {}
        for move in moves:
            if status == "approved" and fronts._move_raised(c, self._move_id(item["id"], move)):
                review[move.front] = {"status": "delivered", "eligible_listeners": []}
                continue
            review[move.front] = {
                "status": "pending" if status == "pending" else "waiting",
                "eligible_listeners": [
                    {"actor": role.ref.model_dump(mode="json"), "label": role.label}
                    for role in pilots
                    if self._shared_evidence(refs, move, role.ref)
                ],
            }
        return review

    def review(
        self, viewer: GuildViewer, key: str, scene: str, identity: str, decision: str
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject"):
            raise WorkflowError("PLANNING_REVIEW: select approve or reject.")

        def save(c: Connection) -> dict[str, Any]:
            item = self.reactions._get(c, scene, identity, RECORD)
            if self._status(c, scene, item) != "pending":
                raise WorkflowError("STALE_PLANNING: use a current unreviewed proposal.")
            self.reactions._save(c, scene, identity + ":review", REVIEW, decision=decision)
            return {
                "id": identity,
                "status": "approved" if decision == "approve" else "rejected",
                "effects_applied": False,
            }

        return self.store._write(
            viewer,
            key,
            REVIEW,
            {"scene": scene, "id": identity, "decision": decision},
            save,
            authorize=lambda c: self._scope(c, viewer, scene),
            auto_audit=False,
        )

    def _approved_refs(
        self, c: Connection, scene: str, item: dict[str, Any]
    ) -> tuple[KnowledgeReference, ...]:
        from girlframe.services.director_fronts import records

        source = PlanningSource.model_validate(item["source"])
        self._scene(c, scene)
        refs = self.context._current(c, scene)
        if (
            not self._source_refs(c, scene, source, refs)
            or self._binding(c, scene, source.scene) != item["binding"]
        ):
            raise WorkflowError("STALE_PLANNING: the original consent or trigger changed.")
        visible = {ref.id: ref.model_dump(mode="json") for ref in refs}
        if any(visible.get(key) != value for key, value in item["evidence"].items()):
            raise WorkflowError("STALE_PLANNING: cited evidence has changed.")
        fronts = {
            front.id: front
            for front in records(load_state(c, self.store.campaign_id))
            if front.status in ("active", "ready")
        }
        roles = {
            role.ref: role
            for role in self.dossiers.knowledge._actor_views(c, self.observer._scene(c, scene))
        }
        planned_roles = self._planned_roles(c, scene)
        for move in DirectorPlanningDecision.model_validate_json(
            json.dumps(item["decision"])
        ).moves:
            front, role = fronts.get(move.front), roles.get(move.actor)
            if (
                front is None
                or role is None
                or move.actor not in planned_roles
                or not self._owns_front(front, move.actor, role.controller)
            ):
                raise WorkflowError("STALE_PLANNING: Front or actual controller changed.")
            self._scene(c, front.scene_id, closed=True)
            if (
                self.observer._state(c, front.scene_id).consent_generation
                != front.consent_generation
            ):
                raise WorkflowError("STALE_PLANNING: Front consent changed.")
        return refs

    def portrayal(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        *,
        claimed: str | None = None,
        listener: ActorRef | None = None,
    ) -> PortrayalMove | None:
        if not self.observer.activity_shadow or (
            actor.kind != "npc" and (actor.kind != "handler" or listener is None)
        ):
            return None
        from girlframe.services.director_fronts import DirectorFrontService

        for item in self._records(c, scene):
            approval = self._read(c, scene, item["id"] + ":review")
            if not approval or approval["decision"] != "approve":
                continue
            for move in DirectorPlanningDecision.model_validate_json(
                json.dumps(item["decision"])
            ).moves:
                if move.actor != actor:
                    continue
                identity = self._move_id(item["id"], move)
                if (claimed and claimed != identity) or (
                    (not claimed or actor.kind == "handler")
                    and DirectorFrontService(self.context)._move_raised(c, identity)
                ):
                    continue
                try:
                    refs = self._approved_refs(c, scene, item)
                except WorkflowError:
                    continue
                if listener is not None and not self._shared_evidence(refs, move, listener):
                    continue
                return PortrayalMove(
                    id=identity, text=move.text, source_refs=move.evidence, tracked=True
                )
        return None
