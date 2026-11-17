"""Reviewed world authorship through narrow native services and deliberate disclosures."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.ai.worldbuilding import (
    DevelopmentAction,
    FactionAction,
    NpcAction,
    WorldbuildingPacket,
    WorldbuildingProposal,
    WorldbuildingProvider,
)
from girlframe.database import tables as t
from girlframe.engine import m3_world as world_rules
from girlframe.engine import m3_world_development as development_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

WorldTopic = Literal["general", "objective", "scope", "status", "briefing", "tactical", "debrief"]


class DirectorWorldbuildingService:
    def __init__(
        self, context: DirectorContextService, provider: WorldbuildingProvider | None = None
    ):
        self.context, self.observer, self.store = context, context.observations, context.store
        self.knowledge = DirectorKnowledgeService(context)
        self.world = WorldService(MissionService(self.store))
        self.world.game = self.observer.game
        self.provider = provider

    def _scope(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene: str,
        *,
        gm: bool = False,
        native_access: bool = True,
    ) -> None:
        self.observer._scope()
        self.observer.game.unpaused(c)
        row = self.observer._scene(c, scene, viewer)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: retain current scene consent.")
        if native_access:
            self.world.missions.access.authorize(c, viewer, "world")
        if gm:
            self.store.administrator(viewer)

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
            raise WorkflowError("WORLD_RECORD_UNAVAILABLE: reopen actual worldbuilding work.")
        return dict(value)

    def _saved(self, c: Connection, scene: str, identity: str) -> dict[str, Any] | None:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        return json.loads(raw) if raw else None

    def _save(self, c: Connection, scene: str, identity: str, kind: str, **fields: Any) -> None:
        c.execute(
            t.director_context["shadow"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=scene,
                id=identity,
                body_json=json.dumps(
                    {"id": identity, "scene_id": scene, "record_type": kind, **fields},
                    sort_keys=True,
                ),
            )
        )

    def _snapshot(
        self, c: Connection, viewer: GuildViewer, scene: str, source: str, identity: str
    ) -> WorldbuildingPacket:
        self._scope(c, viewer, scene, gm=True)
        canon = load_state(c, self.store.campaign_id)
        row = self.observer._scene(c, scene)
        if canon.world is None or canon.handler not in row["participants"]:
            raise WorkflowError(
                "WORLD_REQUIRED: initialize the world and recover its actual owner."
            )
        if self.observer.game.pending_actions(c):
            raise WorkflowError("WORLD_BUSY: finish pending native Plays before world additions.")
        context = self.context._build(c, viewer, scene)
        actual = self.knowledge._source(c, scene, source)
        observation = self.observer._state(c, scene)
        payload = {
            "source": actual.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "canonical": canon.model_dump(mode="json"),
            "guard": self.observer._guard(c, row, observation),
            "consent_generation": observation.consent_generation,
        }
        return WorldbuildingPacket(
            request_id=identity,
            scene_id=scene,
            source=actual,
            context=context,
            canonical_state=canon.model_dump(mode="json"),
            world_revision=canon.revision,
            owner_id=str(canon.handler),
            frontier=observation.sequence,
            revision=_digest(payload),
            native_guard=self._guard(c, scene),
        )

    def _guard(self, c: Connection, scene: str) -> str:
        row = self.observer._scene(c, scene)
        state = self.observer._state(c, scene)
        return _digest(
            {
                "guard": self.observer._guard(c, row, state),
                "consent_generation": state.consent_generation,
            }
        )

    def open(self, viewer: GuildViewer, key: str, scene: str, source_id: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            identity = "world-request:" + str(uuid4())
            packet = self._snapshot(c, viewer, scene, source_id, identity)
            self._save(
                c, scene, identity, "worldbuilding_request", packet=packet.model_dump(mode="json")
            )
            return {"id": identity}

        return self.store._write(
            viewer,
            key,
            "director.world_open",
            {"scene": scene, "source": source_id},
            operation,
            authorize=lambda c: self._scope(c, viewer, scene, gm=True),
        )

    def _packet(self, c: Connection, scene: str, request: str) -> WorldbuildingPacket:
        return WorldbuildingPacket.model_validate_json(
            json.dumps(self._record(c, scene, request, "worldbuilding_request")["packet"])
        )

    def packet(self, viewer: GuildViewer, scene: str, request: str) -> WorldbuildingPacket:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            return self._packet(c, scene, request)

    def _current(self, c: Connection, viewer: GuildViewer, packet: WorldbuildingPacket) -> None:
        if (
            self._snapshot(c, viewer, packet.scene_id, packet.source.id, packet.request_id)
            != packet
        ):
            raise WorkflowError("STALE_WORLDBUILDING: reopen current canon, source and authority.")

    def _validate(self, packet: WorldbuildingPacket, proposal: WorldbuildingProposal) -> None:
        allowed = {"source", "native", *("reference:" + x.id for x in packet.context.references)}
        citations = set(proposal.cited_evidence)
        if (
            proposal.request_id != packet.request_id
            or len(citations) != len(proposal.cited_evidence)
            or not {"source", "native"} <= citations
            or not citations <= allowed
        ):
            raise WorkflowError(
                "WORLD_EVIDENCE_INVALID: cite this source and actual native context."
            )
        canon = GameState.model_validate_json(json.dumps(packet.canonical_state))
        action = proposal.action
        try:
            if isinstance(action, DevelopmentAction):
                development_rules.validate(canon, action.development, int(packet.owner_id))
            elif isinstance(action, NpcAction):
                npc = action.npc
                if (
                    npc.controller != int(packet.owner_id)
                    or npc.source_kind is not None
                    or npc.revealed
                    or npc.tags
                    or npc.bonds
                    or npc.captive_of
                    or npc.custody_event
                    or npc.secret_factions
                    or npc.employment != "unrecorded"
                    or "director" in npc.jobs
                    or "prisoner" in npc.jobs
                ):
                    raise ValueError(
                        "WORLD_NPC_AUTHORITY: introduce a pristine owned ordinary NPC; "
                        "special roles, custody and other controllers need native sources"
                    )
                assert canon.world is not None
                world_rules.introduce_npc(canon.world, npc)
            elif isinstance(action, FactionAction):
                if not action.faction.active or action.faction.underfunded:
                    raise ValueError(
                        "WORLD_FACTION_SOURCE: new factions cannot import consequence state"
                    )
                assert canon.world is not None
                world_rules.update(canon.world, factions=(*canon.world.factions, action.faction))
        except (ValueError, ValidationError) as error:
            raise WorkflowError(str(error).partition("\n")[0]) from None

    def _propose(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene: str,
        request: str,
        proposal: WorldbuildingProposal,
    ) -> dict[str, Any]:
        packet = self._packet(c, scene, request)
        self._current(c, viewer, packet)
        self._validate(packet, proposal)
        identity = "world-proposal:" + str(uuid4())
        self._save(
            c,
            scene,
            identity,
            "worldbuilding_proposal",
            request=request,
            proposal=proposal.model_dump(mode="json"),
        )
        return {"id": identity, "effects_applied": False}

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        request: str,
        proposal: WorldbuildingProposal,
    ) -> dict[str, Any]:
        proposal = WorldbuildingProposal.model_validate_json(proposal.model_dump_json())
        return self.store._write(
            viewer,
            key,
            "director.world_propose",
            {"scene": scene, "request": request, "proposal": proposal.model_dump(mode="json")},
            lambda c: self._propose(c, viewer, scene, request, proposal),
            authorize=lambda c: self._scope(c, viewer, scene, gm=True),
        )

    def generate(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        request: str,
        provider: WorldbuildingProvider | None = None,
    ) -> dict[str, Any]:
        payload = {"scene": scene, "request": request}
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
                    {"actor": viewer.user_id, "kind": "director.world_generate", "payload": payload}
                ):
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: world generation request changed.")
                return dict(json.loads(old["outcome_json"]))
            packet = self._packet(c, scene, request)
            self._current(c, viewer, packet)
        transport = provider or self.provider
        if transport is None:
            raise WorkflowError(
                "WORLD_PROVIDER_REQUIRED: supply a manual proposal or trusted provider."
            )
        try:
            proposal = WorldbuildingProposal.model_validate_json(
                transport.propose(packet).model_dump_json()
            )
        except Exception:
            raise WorkflowError(
                "WORLD_PROVIDER_UNAVAILABLE: no valid proposal was committed."
            ) from None
        return self.store._write(
            viewer,
            key,
            "director.world_generate",
            payload,
            lambda c: self._propose(c, viewer, scene, request, proposal),
            authorize=lambda c: self._scope(c, viewer, scene, gm=True),
        )

    def _load(
        self, c: Connection, scene: str, identity: str
    ) -> tuple[WorldbuildingPacket, WorldbuildingProposal]:
        record = self._record(c, scene, identity, "worldbuilding_proposal")
        return self._packet(c, scene, record["request"]), WorldbuildingProposal.model_validate_json(
            json.dumps(record["proposal"])
        )

    def private(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            packet, proposal = self._load(c, scene, identity)
            review = self._saved(c, scene, identity + ":review")
            status = review["decision"] if review else "awaiting_gm_review"
            if not self._saved(c, scene, "world-commit:" + identity):
                try:
                    self._current(c, viewer, packet)
                except WorkflowError:
                    status = "stale_reopen_source"
            else:
                status = "committed"
            return {
                "id": identity,
                "packet": packet.model_dump(mode="json"),
                "proposal": proposal.model_dump(mode="json"),
                "status": status,
                "semantic_review_required": True,
                "publication": "private_only",
            }

    def feedback(
        self, viewer: GuildViewer, scene: str, request: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            packet = self._packet(c, scene, request)
            self._current(c, viewer, packet)
            try:
                candidate = WorldbuildingProposal.model_validate_json(json.dumps(raw))
                self._validate(packet, candidate)
            except ValidationError:
                return {
                    "valid": False,
                    "errors": [
                        {
                            "code": "WORLD_SCHEMA_INVALID",
                            "field": "action",
                            "message": "Use the schema; effects require native operations.",
                        }
                    ],
                }
            except WorkflowError as error:
                return {
                    "valid": False,
                    "errors": [
                        {
                            "code": str(error).partition(":")[0],
                            "field": "action_or_evidence",
                            "message": "Use actual owned subjects, "
                            "current predecessor and source/native citations.",
                        }
                    ],
                }
            return {"valid": True, "errors": []}

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        decision: Literal["approve", "reject"],
        reason: str,
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject") or not reason.strip() or len(reason) > 1200:
            raise WorkflowError("WORLD_REVIEW_INVALID: provide an explicit decision and reason.")

        def operation(c: Connection) -> dict[str, Any]:
            packet, proposal = self._load(c, scene, identity)
            if self._saved(c, scene, identity + ":review"):
                raise WorkflowError("WORLD_REVIEW_FINAL: this proposal already has a review.")
            if decision == "approve":
                self._current(c, viewer, packet)
                self._validate(packet, proposal)
            self._save(
                c,
                scene,
                identity + ":review",
                "worldbuilding_review",
                decision=decision,
                reason=reason,
                reviewer_id=str(viewer.user_id),
            )
            return {"id": identity, "status": decision, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.world_review",
            {"scene": scene, "proposal": identity, "decision": decision, "reason": reason},
            operation,
            authorize=lambda c: self._scope(c, viewer, scene, gm=True),
        )

    def owner_review(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            packet, proposal = self._load(c, scene, identity)
            if packet.owner_id != str(viewer.user_id):
                raise WorkflowError("WORLD_NOT_OWNED: retain the actual native world authority.")
            return {
                "id": identity,
                "action": proposal.action.model_dump(mode="json"),
                "notice": "Review canon continuity, prose effects and disclosure. "
                "This is OOC world authority, not fictional Handler knowledge.",
            }

    def confirm(self, viewer: GuildViewer, key: str, scene: str, identity: str) -> dict[str, Any]:
        native_key = "worldbuilding-native:" + identity
        commit_id = "world-commit:" + identity
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            packet, proposal = self._load(c, scene, identity)
            if packet.owner_id != str(viewer.user_id):
                raise WorkflowError(
                    "WORLD_NOT_OWNED: only the original native world owner confirms."
                )
            review = self._record(c, scene, identity + ":review", "worldbuilding_review")
            if review["decision"] != "approve":
                raise WorkflowError(
                    "WORLD_REVIEW_REQUIRED: a rejected proposal cannot become canon."
                )

        def guard(c: Connection) -> None:
            self._scope(c, viewer, scene)
            if c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == native_key,
                )
            ):
                return
            # Read permission/GM review above is separate from this transaction-time guard.
            if (
                self._guard(c, scene) != packet.native_guard
                or load_state(c, self.store.campaign_id).model_dump(mode="json")
                != packet.canonical_state
                or self.knowledge._source(c, scene, packet.source.id) != packet.source
                or self.context._current(c, scene) != packet.context.references
            ):
                raise WorkflowError(
                    "STALE_WORLDBUILDING: reopen current canon, source and authority."
                )
            self._validate(packet, proposal)

        with self.store.source_guard(guard):
            action = proposal.action
            if isinstance(action, DevelopmentAction):
                native = self.world.develop(
                    viewer,
                    native_key,
                    packet.world_revision,
                    action.development,
                    source_proposal=identity,
                )
            elif isinstance(action, NpcAction):
                native = self.world.npc(viewer, native_key, packet.world_revision, action.npc)
            else:
                native = self.world.faction(
                    viewer, native_key, packet.world_revision, action.faction
                )

        def finalize(c: Connection) -> dict[str, Any]:
            old = self._saved(c, scene, commit_id)
            if old is None:
                event = (
                    c.execute(
                        sa.select(t.events).where(
                            t.events.c.campaign_id == self.store.campaign_id,
                            t.events.c.command_key == native_key,
                            t.events.c.kind
                            == {
                                "development": "m3.world_development_recorded",
                                "introduce_npc": "m3.npc_introduced",
                                "introduce_faction": "m3.faction_introduced",
                            }[proposal.action.kind],
                        )
                    )
                    .mappings()
                    .one()
                )
                self._save(
                    c,
                    scene,
                    commit_id,
                    "worldbuilding_commit",
                    proposal_id=identity,
                    native_key=native_key,
                    native_event=event["id"],
                    native_result=native,
                    owner_id=packet.owner_id,
                )
            self._prove_commit(c, scene, commit_id)
            return {
                "id": commit_id,
                "proposal_id": identity,
                "native": native,
                "canon_committed": True,
                "publication": "undisclosed",
            }

        return self.store._write(
            viewer,
            key,
            "director.world_confirm",
            {"scene": scene, "proposal": identity},
            finalize,
            authorize=lambda c: self._scope(c, viewer, scene),
            auto_audit=False,
        )

    def _prove_commit(self, c: Connection, scene: str, identity: str) -> tuple[dict[str, Any], str]:
        record = self._record(c, scene, identity, "worldbuilding_commit")
        packet, proposal = self._load(c, scene, record["proposal_id"])
        review = self._record(c, scene, record["proposal_id"] + ":review", "worldbuilding_review")
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == record["native_event"],
                )
            )
            .mappings()
            .first()
        )
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == record["native_event"],
            )
        )
        command = c.scalar(
            sa.select(t.commands.c.outcome_json).where(
                t.commands.c.campaign_id == self.store.campaign_id,
                t.commands.c.interaction_key == record["native_key"],
            )
        )
        if (
            not event
            or not history
            or not command
            or review["decision"] != "approve"
            or event["command_key"] != record["native_key"]
            or event["actor_id"] != packet.owner_id
            or record["owner_id"] != packet.owner_id
            or json.loads(command) != record["native_result"]
        ):
            raise WorkflowError("UNPROVEN_WORLD_COMMIT: retain actual reviewed native provenance.")
        canon = GameState.model_validate_json(history)
        action = proposal.action
        if isinstance(action, DevelopmentAction):
            development = next(
                (
                    x
                    for x in development_rules.records(canon)
                    if x.id == record["native_result"]["id"]
                ),
                None,
            )
            if (
                event["kind"] != "m3.world_development_recorded"
                or development is None
                or development.source_proposal != record["proposal_id"]
                or development.source_event != event["id"]
                or development.model_dump(include=set(type(action.development).model_fields))
                != action.development.model_dump()
            ):
                raise WorkflowError("UNPROVEN_WORLD_COMMIT: retain the exact original development.")
            text = development.title + "\n" + development.text
        elif isinstance(action, NpcAction):
            if (
                event["kind"] != "m3.npc_introduced"
                or canon.world is None
                or not any(
                    x.id == action.npc.id
                    and x.name == action.npc.name
                    and x.detail == action.npc.detail
                    for x in canon.world.npcs
                )
            ):
                raise WorkflowError("UNPROVEN_WORLD_COMMIT: retain the original native NPC.")
            text = action.npc.name + "\n" + action.npc.detail
        else:
            if (
                event["kind"] != "m3.faction_introduced"
                or canon.world is None
                or action.faction not in canon.world.factions
            ):
                raise WorkflowError("UNPROVEN_WORLD_COMMIT: retain the original native faction.")
            text = action.faction.name + "\n" + action.faction.description
        return record, text

    def disclose(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        commit_id: str,
        quote: str,
        recipients: tuple[ActorRef, ...],
        topic: WorldTopic = "general",
    ) -> dict[str, Any]:
        if (
            not quote.strip()
            or len(quote) > 1000
            or not recipients
            or len(set(recipients)) != len(recipients)
        ):
            raise WorkflowError(
                "WORLD_DISCLOSURE_INVALID: select exact bounded text and distinct actors."
            )

        def operation(c: Connection) -> dict[str, Any]:
            _, text = self._prove_commit(c, scene, commit_id)
            row = self.observer._scene(c, scene)
            if text.count(quote) != 1 or not set(recipients) <= set(self.knowledge._actors(c, row)):
                raise WorkflowError(
                    "WORLD_DISCLOSURE_INVALID: use actual text and current recipients."
                )
            identity = "world-disclosure:" + str(uuid4())
            state = self.observer._state(c, scene)
            prior = self.context._references(c, scene)
            if len(self.context._active(c, scene)) >= 100:
                raise WorkflowError(
                    "CONTEXT_LIMIT: retire references explicitly before disclosure."
                )
            canon = load_state(c, self.store.campaign_id)
            controllers = {
                actor.token: resolve(
                    canon, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                ).controller
                for actor in recipients
            }
            self._save(
                c,
                scene,
                identity,
                "worldbuilding_disclosure",
                commit_id=commit_id,
                text=quote,
                recipients=[x.model_dump(mode="json") for x in recipients],
                revision=1,
                audience_ids=sorted(str(x) for x in row["participants"]),
                recipient_controllers=controllers,
                consent_generation=state.consent_generation,
            )
            self._disclosure_source(c, scene, identity)
            reference = KnowledgeReference(
                id=str(uuid4()),
                source_id=identity,
                source_revision=1,
                order=len(prior) + 1,
                known_by=tuple(x.token for x in recipients),
                topic=topic,
                classification="established_world",
                text="Established world: " + quote,
            )
            c.execute(
                t.director_context["knowledge"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene,
                    id=reference.id,
                    body_json=reference.model_dump_json(),
                )
            )
            self.observer._save(
                c, scene, state.model_copy(update={"generation": state.generation + 1})
            )
            return {"id": identity, "reference_ids": [reference.id], "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.world_disclose",
            {
                "scene": scene,
                "commit": commit_id,
                "quote": quote,
                "recipients": [x.model_dump(mode="json") for x in recipients],
                "topic": topic,
            },
            operation,
            authorize=lambda c: self._scope(c, viewer, scene, gm=True),
            auto_audit=False,
        )

    def _disclosure_source(
        self, c: Connection, scene: str, identity: str, *, allow_closed: bool = False
    ) -> dict[str, Any]:
        self.observer._scope()
        record = self._record(c, scene, identity, "worldbuilding_disclosure")
        row = self.observer._scene(c, scene, allow_closed=allow_closed)
        state = self.observer._state(c, scene)
        _, text = self._prove_commit(c, scene, record["commit_id"])
        recipients = tuple(
            ActorRef.model_validate_json(json.dumps(x)) for x in record["recipients"]
        )
        if (
            state.policy.mode != "shadow"
            or not self.observer._consented(c, row, state)
            or state.consent_generation != record["consent_generation"]
            or record["audience_ids"] != sorted(str(x) for x in row["participants"])
            or text.count(record["text"]) != 1
            or not self._disclosure_actors(c, row, recipients, record, allow_closed)
        ):
            raise WorkflowError(
                "STALE_WORLD_DISCLOSURE: reconcile source consent, audience and actors."
            )
        return {"text": record["text"], "recipients": record["recipients"], "revision": 1}

    def _disclosure_actors(
        self,
        c: Connection,
        row: dict[str, Any],
        recipients: tuple[ActorRef, ...],
        record: dict[str, Any],
        allow_closed: bool,
    ) -> bool:
        canon = load_state(c, self.store.campaign_id)
        cast = next((x for x in canon.scene_casts if x.id == row["id"]), None)
        for actor in recipients:
            try:
                actual = resolve(
                    canon, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                )
            except ValueError:
                return False
            if (
                not actual.alive
                or actual.controller not in row["participants"]
                or actual.controller != record["recipient_controllers"].get(actor.token)
            ):
                return False
            if (
                not row["open"]
                and allow_closed
                and actor.kind == "npc"
                and (
                    cast is None
                    or not any(
                        role.actor == actor and role.controller == actual.controller
                        for role in cast.roles
                    )
                )
            ):
                return False
        if row["open"] or not allow_closed:
            return set(recipients) <= set(self.knowledge._actors(c, row))
        return True

    def pending(self, viewer: GuildViewer, scene: str, *, gm: bool = False) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=gm, native_access=False)
            table = t.director_context["shadow"]
            ids = list(
                c.scalars(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.func.json_extract(table.c.body_json, "$.record_type")
                        == "worldbuilding_proposal",
                    )
                )
            )
            result = []
            for identity in ids:
                packet, proposal = self._load(c, scene, identity)
                if not gm and packet.owner_id != str(viewer.user_id):
                    continue
                review = self._saved(c, scene, identity + ":review")
                if (
                    self._saved(c, scene, "world-commit:" + identity)
                    or review
                    and review["decision"] == "reject"
                ):
                    continue
                result.append(
                    {
                        "id": identity,
                        "owner_id": packet.owner_id,
                        "kind": proposal.action.kind,
                        "status": "stale_reopen_source"
                        if packet.native_guard != self._guard(c, scene)
                        else "awaiting_confirmation"
                        if review
                        else "awaiting_gm_review",
                    }
                )
            return result
