"""GM-proposed, source-quoted acquisition; the engine controls scope and persistence."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.ai.knowledge import (
    ActorDirectoryEntry,
    Disclosure,
    KnowledgePacket,
    KnowledgeProposal,
    KnowledgeProvider,
    KnowledgeSource,
    fact_text,
    reference_text,
)
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_cast import validate_role
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.director_context import DirectorContextService


class DirectorKnowledgeService:
    def __init__(self, context: "DirectorContextService"):
        self.context, self.observer, self.store = context, context.observations, context.store

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        self.observer._scope()
        self.store.administrator(viewer)
        self.observer.game.unpaused(c)
        row = self.observer._scene(c, scene, viewer)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: retain current consent.")
        return row

    def _authorize(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        self._scope(c, viewer, scene)

    def _source(
        self, c: Connection, scene: str, identity: str, *, allow_closed: bool = False
    ) -> KnowledgeSource:
        row = self.observer._scene(c, scene, allow_closed=allow_closed)
        if identity.startswith("world-disclosure:"):
            record = self.context._approved_world(c, scene, identity, allow_closed=allow_closed)
            return KnowledgeSource(
                id=identity,
                revision=record["revision"],
                kind="approved_world",
                text=record["text"],
                allowed_recipients=tuple(
                    ActorRef.model_validate(actor) for actor in record["recipients"]
                ),
            )
        if identity.startswith("gm-narration:"):
            record = self.context._approved_outcome(c, scene, identity, allow_closed=allow_closed)
            return KnowledgeSource(
                id=identity, revision=1, kind="approved_outcome", text=record["text"]
            )
        source = self.observer._latest_source(c, identity)
        inputs = t.director["inputs"]
        if (
            source is None
            or source.kind != "message"
            or not c.scalar(
                sa.select(inputs.c.source_id)
                .where(
                    inputs.c.campaign_id == self.store.campaign_id,
                    inputs.c.scene_id == scene,
                    inputs.c.source_id == identity,
                )
                .limit(1)
            )
        ):
            raise WorkflowError("SOURCE_UNAVAILABLE: select an actual message or approved outcome.")
        if source.audience_ids != tuple(sorted(str(x) for x in row["participants"])):
            raise WorkflowError("SOURCE_SCOPE_CHANGED: reconcile the source audience.")
        return KnowledgeSource(
            id=identity,
            revision=source.source_revision,
            kind="message",
            text=source.text or "",
            actor=source.actor,
            fictional_channel=source.fictional_channel,
        )

    def _actors(self, c: Connection, scene: dict[str, Any]) -> tuple[ActorRef, ...]:
        return tuple(actor.ref for actor in self._actor_views(c, scene))

    def _actor_views(self, c: Connection, scene: dict[str, Any]) -> tuple[ActorView, ...]:
        canon = load_state(c, self.store.campaign_id)
        cast = next((x for x in canon.scene_casts if x.id == scene["id"] and x.open), None)
        refs = [x.actor for x in cast.roles] if cast else []
        for uid in scene["participants"]:
            if str(uid) in canon.sheets:
                refs.append(
                    ActorRef(
                        kind="pilot",
                        entity=str(uid),
                        incarnation=self.observer.game.character_binding(
                            c, canon, uid, require_current_profile=False
                        ),
                    )
                )
        handler = active_handler(canon)
        if handler:
            refs.append(handler)
        available = {}
        for ref in refs:
            try:
                actor = resolve(
                    canon, ref, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                if actor.controller not in scene["participants"] or not actor.alive:
                    continue
                if cast:
                    validate_role(cast, actor)
                available[ref.token] = actor
            except ValueError:
                continue
        return tuple(available.values())

    def _snapshot(
        self, c: Connection, viewer: GuildViewer, scene: str, source: str, request: str
    ) -> KnowledgePacket:
        row = self._scope(c, viewer, scene)
        context = self.context._build(c, viewer, scene)
        actual = self._source(c, scene, source)
        actors = self._actors(c, row)
        if actual.kind == "approved_world":
            if not set(actual.allowed_recipients) <= set(actors):
                raise WorkflowError("STALE_ACTOR: recover the actual disclosed world recipients.")
            actors = tuple(actor for actor in actors if actor in actual.allowed_recipients)
        canon = load_state(c, self.store.campaign_id)
        directory = []
        for actor in actors:
            view = resolve(
                canon, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            directory.append(
                ActorDirectoryEntry(
                    actor=actor,
                    name=view.label,
                    controller=view.controller,
                    aliases=(view.label,) if view.label else (),
                )
            )
        if actual.actor is not None and actual.actor not in actors:
            raise WorkflowError("STALE_ACTOR: recover the original source actor.")
        spoken: dict[str, list[ActorRef]] = {}
        if actual.kind == "message" and actual.fictional_channel != "comms":
            for actor in actors:
                for quote in self.heard(c, scene, source, actor):
                    spoken.setdefault(quote, []).append(actor)
        disclosures = tuple(
            Disclosure(quote=quote, recipients=tuple(listeners))
            for quote, listeners in spoken.items()
        )
        payload = {
            "source": actual.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "recipients": [x.model_dump(mode="json") for x in actors],
            "actor_directory": [x.model_dump(mode="json") for x in directory],
            "accepted_disclosures": [x.model_dump(mode="json") for x in disclosures],
        }
        return KnowledgePacket(
            request_id=request,
            scene_id=scene,
            source=actual,
            context=context,
            recipients=actors,
            actor_directory=tuple(directory),
            accepted_disclosures=disclosures,
            revision=_digest(payload),
        )

    def _record(self, c: Connection, scene: str, identity: str, kind: str) -> dict[str, Any]:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        record = json.loads(raw) if raw else None
        if not record or record.get("record_type") != kind:
            raise WorkflowError("KNOWLEDGE_UNAVAILABLE: reopen the actual GM knowledge work.")
        return dict(record)

    def _save(self, c: Connection, scene: str, identity: str, body: dict[str, Any]) -> None:
        c.execute(
            t.director_context["shadow"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=scene,
                id=identity,
                body_json=json.dumps(body, sort_keys=True),
            )
        )

    def open(self, viewer: GuildViewer, key: str, scene: str, source: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            identity = "knowledge-request:" + str(uuid4())
            packet = self._snapshot(c, viewer, scene, source, identity)
            self._save(
                c,
                scene,
                identity,
                {"record_type": "knowledge_request", "packet": packet.model_dump(mode="json")},
            )
            return {"id": identity}

        return self.store._write(
            viewer,
            key,
            "director.knowledge_open",
            {"scene": scene, "source": source},
            operation,
            authorize=lambda c: self._authorize(c, viewer, scene),
        )

    def _packet(self, c: Connection, scene: str, identity: str) -> KnowledgePacket:
        record = self._record(c, scene, identity, "knowledge_request")
        return KnowledgePacket.model_validate_json(json.dumps(record["packet"]))

    def packet(self, viewer: GuildViewer, scene: str, identity: str) -> KnowledgePacket:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            return self._packet(c, scene, identity)

    def _fresh(self, c: Connection, viewer: GuildViewer, packet: KnowledgePacket) -> None:
        current = self._snapshot(c, viewer, packet.scene_id, packet.source.id, packet.request_id)
        if current.revision != packet.revision:
            raise WorkflowError("STALE_KNOWLEDGE_PROPOSAL: reopen the source and context.")

    def _validate(self, packet: KnowledgePacket, proposal: KnowledgeProposal) -> None:
        if proposal.request_id != packet.request_id:
            raise WorkflowError("SOURCE_SUBSTITUTION: retain the original request.")
        refs = {x.id: x for x in packet.context.references}
        for disclosure in proposal.disclosures:
            if (
                packet.source.kind != "message"
                or packet.source.fictional_channel == "private"
                or not disclosure.quote.strip()
                or packet.source.text.count(disclosure.quote) != 1
            ):
                raise WorkflowError(
                    "UNPROVEN_SPEECH: classify a unique actual nonprivate source quote."
                )
            if not set(disclosure.recipients) <= set(packet.recipients):
                raise WorkflowError("INVALID_RECIPIENT: select actual current listeners.")
        if len({x.quote for x in proposal.disclosures}) != len(proposal.disclosures):
            raise WorkflowError(
                "DUPLICATE_DISCLOSURE: combine listeners for the same speech quote."
            )
        signatures = []
        for update in proposal.updates:
            if not update.quote.strip() or update.quote not in packet.source.text:
                raise WorkflowError("UNGROUNDED_KNOWLEDGE: quote actual source text.")
            if not set(update.recipients) <= set(packet.recipients):
                raise WorkflowError("INVALID_RECIPIENT: select actual current scene actors.")
            if not {relation.reference_id for relation in update.relations} <= refs.keys():
                raise WorkflowError("STALE_RELATION: relate only current source-bound accounts.")
            if update.basis == "perception":
                if packet.source.kind != "message" or update.recipients != (packet.source.actor,):
                    raise WorkflowError(
                        "UNPROVEN_PERCEPTION: an input proves only its own actor's claim."
                    )
            elif update.basis == "report":
                prior = refs.get(update.prior_reference or "")
                if (
                    packet.source.kind != "message"
                    or packet.source.fictional_channel != "comms"
                    or prior is None
                    or packet.source.actor is None
                    or packet.source.actor.token not in prior.known_by
                    or update.quote != fact_text(prior)
                ):
                    raise WorkflowError(
                        "UNPROVEN_REPORT: require comms and actual speaker-known content."
                    )
            elif update.basis in ("testimony", "paraphrase"):
                if packet.source.kind != "message" or packet.source.actor is None:
                    raise WorkflowError(
                        "UNPROVEN_TESTIMONY: require an actual speaker-owned message."
                    )
                for recipient in update.recipients:
                    heard = packet.source.fictional_channel == "comms" or any(
                        recipient in disclosure.recipients and update.quote in disclosure.quote
                        for disclosure in (*packet.accepted_disclosures, *proposal.disclosures)
                    )
                    if not heard:
                        raise WorkflowError(
                            "UNPROVEN_TESTIMONY: recipient lacks classified speech."
                        )
                if update.basis == "paraphrase":
                    prior = refs.get(update.prior_reference or "")
                    if prior is None or packet.source.actor.token not in prior.known_by:
                        raise WorkflowError(
                            "UNPROVEN_PARAPHRASE: cite actual speaker-known content."
                        )
            elif update.basis == "world":
                if packet.source.kind != "approved_world" or update.quote != packet.source.text:
                    raise WorkflowError(
                        "UNPROVEN_WORLD: retain the entire actually approved world disclosure."
                    )
            elif packet.source.kind != "approved_outcome":
                raise WorkflowError(
                    "UNPROVEN_OUTCOME: require an actual confirmed native readback."
                )
            signatures.append((update.basis, update.quote))
        if len(set(signatures)) != len(signatures):
            raise WorkflowError("DUPLICATE_KNOWLEDGE: combine recipients for the same source fact.")

    def feedback(
        self, viewer: GuildViewer, scene: str, request: str, raw: dict[str, Any]
    ) -> dict[str, Any]:
        """GM-private diagnostics; never echo untrusted input or private source prose."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            try:
                packet = self._packet(c, scene, request)
                self._fresh(c, viewer, packet)
                proposal = KnowledgeProposal.model_validate_json(json.dumps(raw))
                self._validate(packet, proposal)
            except ValidationError as error:
                return {
                    "valid": False,
                    "errors": [
                        {
                            "code": "INVALID_CONTRACT",
                            "field": ".".join(map(str, item["loc"])),
                            "message": "Proposal does not satisfy the declared knowledge contract.",
                        }
                        for item in error.errors(include_input=False, include_context=False)
                    ],
                }
            except (ValueError, TypeError, WorkflowError) as error:
                code = (
                    str(error).partition(":")[0]
                    if isinstance(error, WorkflowError)
                    else "INVALID_CONTRACT"
                )
                return {
                    "valid": False,
                    "errors": [
                        {
                            "code": code,
                            "field": "request_or_updates",
                            "message": "Reopen the source and check the acquisition requirements.",
                        }
                    ],
                }
            return {"valid": True, "errors": []}

    def heard(self, c: Connection, scene: str, source_id: str, actor: ActorRef) -> tuple[str, ...]:
        """Only explicit comms or accepted classified speech reaches this listener."""
        self.observer._scope()
        self.observer.game.unpaused(c)
        row = self.observer._scene(c, scene)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: retain current consent.")
        current = {view.ref: view.controller for view in self._actor_views(c, row)}
        if actor not in current:
            raise WorkflowError("INVALID_RECIPIENT: recover the actual current listener.")
        source = self._source(c, scene, source_id)
        if source.kind != "message" or source.fictional_channel == "private":
            return ()
        observation = self.observer._latest_source(c, source_id)
        if observation is not None and observation.gm_addressed:
            return ()
        if (
            observation
            and observation.cast_controllers is not None
            and observation.cast_controllers.get(actor.token) != current[actor]
        ):
            return ()
        if source.fictional_channel == "comms":
            return (source.text,)
        table = t.director_context["shadow"]
        records = [
            json.loads(raw)
            for raw in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type")
                    == "knowledge_disclosure",
                    sa.func.json_extract(table.c.body_json, "$.source_id") == source_id,
                )
            )
        ]
        quotes = set()
        for record in records:
            if (
                record["source_revision"] == source.revision
                and actor.token in record["recipients"]
                and source.text.count(record["quote"]) == 1
            ):
                self._record(c, scene, record["proposal_id"] + ":accepted", "knowledge_acceptance")
                quotes.add(record["quote"])
        return tuple(sorted(quotes, key=source.text.index))

    def propose(
        self, viewer: GuildViewer, key: str, scene: str, request: str, proposal: KnowledgeProposal
    ) -> dict[str, Any]:
        proposal = KnowledgeProposal.model_validate_json(proposal.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            return self._propose(c, viewer, scene, request, proposal)

        return self.store._write(
            viewer,
            key,
            "director.knowledge_propose",
            {"scene": scene, "request": request, "proposal": proposal.model_dump(mode="json")},
            operation,
            authorize=lambda c: self._authorize(c, viewer, scene),
        )

    def _propose(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene: str,
        request: str,
        proposal: KnowledgeProposal,
    ) -> dict[str, Any]:
        packet = self._packet(c, scene, request)
        self._fresh(c, viewer, packet)
        self._validate(packet, proposal)
        identity = "knowledge-proposal:" + str(uuid4())
        self._save(
            c,
            scene,
            identity,
            {"record_type": "knowledge_proposal", "proposal": proposal.model_dump(mode="json")},
        )
        return {"id": identity, "effects_applied": False}

    def generate(
        self, viewer: GuildViewer, key: str, scene: str, request: str, provider: KnowledgeProvider
    ) -> dict[str, Any]:
        # Stable command replay does not need another provider call.
        payload = {"scene": scene, "request": request}
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            saved = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == self.store.campaign_id,
                        t.commands.c.interaction_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if saved:
                expected = _digest(
                    {
                        "actor": viewer.user_id,
                        "kind": "director.knowledge_generate",
                        "payload": payload,
                    }
                )
                if saved["request_hash"] != expected:
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: this acquisition request changed.")
                return dict(json.loads(saved["outcome_json"]))
            packet = self._packet(c, scene, request)
            self._fresh(c, viewer, packet)
        try:
            proposal = KnowledgeProposal.model_validate_json(
                provider.propose(packet).model_dump_json()
            )
        except Exception:
            raise WorkflowError(
                "KNOWLEDGE_PROVIDER_UNAVAILABLE: retry without applying knowledge."
            ) from None
        return self.store._write(
            viewer,
            key,
            "director.knowledge_generate",
            payload,
            lambda c: self._propose(c, viewer, scene, request, proposal),
            authorize=lambda c: self._authorize(c, viewer, scene),
        )

    def acquire(
        self, viewer: GuildViewer, key: str, scene: str, source: str, provider: KnowledgeProvider
    ) -> dict[str, Any]:
        """Trusted GM worker path; the injected provider proposes, engine validates/applies."""
        request = self.open(viewer, key + ":source", scene, source)
        proposal = self.generate(viewer, key + ":proposal", scene, request["id"], provider)
        return self.confirm(viewer, key + ":confirm", scene, proposal["id"])

    def pending(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        """GM-only source metadata for the next acquisition review, including quiet inputs."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            shadow = t.director_context["shadow"]
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(shadow.c.body_json).where(
                        shadow.c.campaign_id == self.store.campaign_id, shadow.c.scene_id == scene
                    )
                )
            ]
            reviewed = {
                (r["source_id"], r["source_revision"])
                for r in records
                if r.get("record_type") == "knowledge_acceptance"
            }
            inputs = t.director["inputs"]
            latest = {}
            for row in c.execute(
                sa.select(inputs.c.source_id, inputs.c.source_revision)
                .where(
                    inputs.c.campaign_id == self.store.campaign_id,
                    inputs.c.scene_id == scene,
                    inputs.c.kind == "message",
                )
                .order_by(inputs.c.source_revision)
            ):
                latest[row.source_id] = row.source_revision
            latest.update(
                {r["id"]: 1 for r in records if r.get("record_type") == "gm_outcome_narration"}
            )
            return [
                {"source_id": identity, "source_revision": revision}
                for identity, revision in latest.items()
                if (identity, revision) not in reviewed
            ]

    def private(self, viewer: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        """GM-only proposal review, including private reasoning and stale status."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            record = self._record(c, scene, identity, "knowledge_proposal")
            proposal = KnowledgeProposal.model_validate_json(json.dumps(record["proposal"]))
            packet = self._packet(c, scene, proposal.request_id)
            table = t.director_context["shadow"]
            accepted = c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity + ":accepted",
                )
            )
            status = "confirmed" if accepted else "awaiting_confirmation"
            if not accepted:
                try:
                    self._fresh(c, viewer, packet)
                except WorkflowError:
                    status = "stale_reopen_source"
            return {
                "id": identity,
                "proposal": proposal.model_dump(mode="json"),
                "request_id": packet.request_id,
                "status": status,
            }

    def confirm(self, viewer: GuildViewer, key: str, scene: str, identity: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            table = t.director_context["shadow"]
            if c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id == identity + ":accepted",
                )
            ):
                raise WorkflowError("KNOWLEDGE_FINAL: this proposal was already applied.")
            record = self._record(c, scene, identity, "knowledge_proposal")
            proposal = KnowledgeProposal.model_validate_json(json.dumps(record["proposal"]))
            packet = self._packet(c, scene, proposal.request_id)
            self._fresh(c, viewer, packet)
            self._validate(packet, proposal)
            previous = self.context._references(c, scene)
            if len(self.context._active(c, scene)) + len(proposal.updates) > 100:
                raise WorkflowError("CONTEXT_LIMIT: retire prompt references explicitly.")
            references = []
            for disclosure in proposal.disclosures:
                event = "knowledge-disclosure:" + str(uuid4())
                self._save(
                    c,
                    scene,
                    event,
                    {
                        "record_type": "knowledge_disclosure",
                        "source_id": packet.source.id,
                        "source_revision": packet.source.revision,
                        "quote": disclosure.quote,
                        "recipients": [actor.token for actor in disclosure.recipients],
                        "source_actor": packet.source.actor.model_dump(mode="json")
                        if packet.source.actor
                        else None,
                        "proposal_id": identity,
                    },
                )
            for index, update in enumerate(proposal.updates, 1):
                signature = _digest(
                    {
                        "source": packet.source.model_dump(mode="json"),
                        "basis": update.basis,
                        "quote": update.quote,
                        "topic": update.topic,
                        "prior": update.prior_reference,
                        **(
                            {
                                "relations": [
                                    relation.model_dump(mode="json")
                                    for relation in update.relations
                                ]
                            }
                            if update.relations
                            else {}
                        ),
                        "recipients": sorted(x.token for x in update.recipients),
                    }
                )
                if c.scalar(
                    sa.select(table.c.id)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.func.json_extract(table.c.body_json, "$.signature") == signature,
                    )
                    .limit(1)
                ):
                    raise WorkflowError(
                        "DUPLICATE_KNOWLEDGE: this source fact and recipients "
                        "were already recorded."
                    )
                event = "knowledge-acquired:" + str(uuid4())
                ref = KnowledgeReference(
                    id=str(uuid4()),
                    source_id=event,
                    source_revision=1,
                    order=len(previous) + index,
                    known_by=tuple(x.token for x in update.recipients),
                    dependencies=tuple(
                        dict.fromkeys(
                            ((update.prior_reference,) if update.prior_reference else ())
                            + tuple(relation.reference_id for relation in update.relations)
                        )
                    ),
                    relations=update.relations,
                    topic=update.topic,
                    classification="approved_outcome"
                    if update.basis == "outcome"
                    else "established_world"
                    if update.basis == "world"
                    else "reported_claim",
                    text=reference_text(update),
                    reported_by=packet.source.actor
                    if update.basis in ("report", "testimony", "paraphrase")
                    else None,
                )
                self._save(
                    c,
                    scene,
                    event,
                    {
                        "record_type": "knowledge_acquisition",
                        "source": packet.source.model_dump(mode="json"),
                        "reference": ref.model_dump(mode="json"),
                        "proposal_id": identity,
                        "basis": update.basis,
                        "signature": signature,
                    },
                )
                c.execute(
                    t.director_context["knowledge"]
                    .insert()
                    .values(
                        campaign_id=self.store.campaign_id,
                        scene_id=scene,
                        id=ref.id,
                        body_json=ref.model_dump_json(),
                    )
                )
                references.append(ref.id)
            self._save(
                c,
                scene,
                identity + ":accepted",
                {
                    "record_type": "knowledge_acceptance",
                    "proposal_id": identity,
                    "source_id": packet.source.id,
                    "source_revision": packet.source.revision,
                    "references": references,
                },
            )
            state = self.observer._state(c, scene)
            self.observer._save(
                c, scene, state.model_copy(update={"generation": state.generation + 1})
            )
            return {"id": identity, "references": references, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.knowledge_confirm",
            {"scene": scene, "proposal": identity},
            operation,
            authorize=lambda c: self._authorize(c, viewer, scene),
        )

    def validate_reference(
        self,
        c: Connection,
        scene: str,
        reference: KnowledgeReference,
        *,
        allow_closed: bool = False,
    ) -> None:
        record = self._record(c, scene, reference.source_id, "knowledge_acquisition")
        if record["reference"] != reference.model_dump(mode="json"):
            raise WorkflowError("UNPROVEN_KNOWLEDGE: preserve the actual accepted reference.")
        original = KnowledgeSource.model_validate_json(json.dumps(record["source"]))
        current = self._source(c, scene, original.id, allow_closed=allow_closed)
        if current != original:
            raise WorkflowError("STALE_KNOWLEDGE: reconcile the corrected acquisition source.")
        self._record(c, scene, record["proposal_id"] + ":accepted", "knowledge_acceptance")
