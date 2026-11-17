"""Explicit synthetic reference chronology; observations never become automatic canon."""

from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_observation import DirectorObservationService, _digest
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorContextService:
    def __init__(self, observations: DirectorObservationService):
        self.observations = observations
        self.store = observations.store

    def _references(self, c: Connection, scene_id: str) -> tuple[KnowledgeReference, ...]:
        table = t.director_context["knowledge"]
        rows = tuple(
            c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.scene_id == scene_id
                )
            )
        )
        return tuple(
            sorted((KnowledgeReference.model_validate_json(x) for x in rows), key=lambda x: x.order)
        )

    def _active(self, c: Connection, scene_id: str) -> tuple[KnowledgeReference, ...]:
        references = tuple({x.source_id: x for x in self._references(c, scene_id)}.values())
        archived = self._archived(c, scene_id)
        references = tuple(x for x in references if x.id not in archived)
        if len(references) > 100:
            raise WorkflowError("CONTEXT_LIMIT: explicit reference archival is required.")
        return references

    def _current(
        self, c: Connection, scene_id: str, *, allow_closed: bool = False
    ) -> tuple[KnowledgeReference, ...]:
        references = self._active(c, scene_id)
        for reference in references:
            if reference.origin_scene is not None:
                from girlframe.services.director_continuity import validate_origin

                validate_origin(self, c, reference, destination_scene=scene_id)
                continue
            if reference.source_id.startswith("knowledge-acquired:"):
                from girlframe.services.director_knowledge import DirectorKnowledgeService

                DirectorKnowledgeService(self).validate_reference(
                    c, scene_id, reference, allow_closed=allow_closed
                )
                continue
            if reference.classification == "approved_outcome":
                record = self._approved_outcome(
                    c, scene_id, reference.source_id, allow_closed=allow_closed
                )
                if reference.source_revision != 1 or reference.text != record["text"]:
                    raise WorkflowError("STALE_KNOWLEDGE: retain the actual approved outcome.")
                continue
            if reference.classification == "established_world":
                record = self._approved_world(
                    c, scene_id, reference.source_id, allow_closed=allow_closed
                )
                if (
                    reference.source_revision != record["revision"]
                    or reference.text != "Established world: " + record["text"]
                    or not set(reference.known_by)
                    <= {ActorRef.model_validate(actor).token for actor in record["recipients"]}
                ):
                    raise WorkflowError("STALE_KNOWLEDGE: preserve the approved world disclosure.")
                continue
            source = self.observations._latest_source(c, reference.source_id)
            if source is None or source.source_revision != reference.source_revision:
                raise WorkflowError(
                    "STALE_KNOWLEDGE: source correction needs explicit reconciliation."
                )
        by_id = {reference.id: reference for reference in references}
        for reference in references:
            for relation in reference.relations:
                target = by_id.get(relation.reference_id)
                if (
                    target is None
                    or target.order >= reference.order
                    or relation.reference_id not in reference.dependencies
                ):
                    raise WorkflowError("STALE_RELATION: reconcile the related account chronology.")
        return references

    @staticmethod
    def _actor_references(
        references: tuple[KnowledgeReference, ...], actor: ActorRef
    ) -> tuple[KnowledgeReference, ...]:
        """A relationship is visible only when both actual accounts are known."""
        known = tuple(x for x in references if actor.token in x.known_by)
        visible = {x.id for x in known}
        return tuple(
            x.model_copy(
                update={
                    "known_by": (actor.token,),
                    "dependencies": tuple(
                        identity for identity in x.dependencies if identity in visible
                    ),
                    "relations": tuple(
                        relation for relation in x.relations if relation.reference_id in visible
                    ),
                }
            )
            for x in known
        )

    def _approved_outcome(
        self, c: Connection, scene: str, identity: str, *, allow_closed: bool = False
    ) -> dict[str, Any]:
        import json

        from girlframe.services.gm_outcomes import GMOutcomeService

        service = GMOutcomeService(self)
        record = service._record(c, scene, identity, "gm_outcome_narration")
        action = self.observations.game.action(c, record["action_id"])
        packet, proposal = service._load(c, scene, record["proposal_id"])
        command = c.scalar(
            sa.select(t.commands.c.outcome_json)
            .where(
                t.commands.c.campaign_id == self.store.campaign_id,
                t.commands.c.interaction_key.like("gm-outcome:" + record["proposal_id"] + ":%"),
            )
            .limit(1)
        )
        if (
            action["scene_id"] != scene
            or action["state"] != "complete"
            or packet.source_kind != "completed"
            or packet.source_id != action["id"]
            or proposal.decision.kind != "narration"
            or proposal.decision.text != record["text"]
            or not command
            or json.loads(command).get("id") != identity
        ):
            raise WorkflowError("UNPROVEN_OUTCOME: retain its actual confirmed native source.")
        if allow_closed:
            raw = c.scalar(
                sa.select(t.m2["m2_scenes"].c.participants_json).where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.id == scene,
                )
            )
            if raw is None:
                raise WorkflowError("SOURCE_UNAVAILABLE: original scene is missing.")
            participants = sorted(str(x) for x in json.loads(raw))
        else:
            participants = sorted(
                str(x) for x in self.observations._scene(c, scene)["participants"]
            )
        if record.get("audience_ids") != participants:
            raise WorkflowError("SOURCE_SCOPE_CHANGED: outcome knowledge requires audience review.")
        return record

    def _approved_world(
        self, c: Connection, scene: str, identity: str, *, allow_closed: bool = False
    ) -> dict[str, Any]:
        """The worldbuilding service owns native/review/disclosure proof, not prose."""
        from girlframe.services.director_worldbuilding import DirectorWorldbuildingService

        return DirectorWorldbuildingService(self)._disclosure_source(
            c, scene, identity, allow_closed=allow_closed
        )

    def _archived(self, c: Connection, scene_id: str) -> set[str]:
        import json

        table = t.director_context["shadow"]
        return {
            identity
            for raw in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene_id,
                    table.c.id.like("reference-archive:%"),
                )
            )
            for identity in json.loads(raw)["reference_ids"]
        }

    def _archive_snapshot(
        self, c: Connection, viewer: GuildViewer, scene_id: str
    ) -> tuple[str, tuple[KnowledgeReference, ...]]:
        # Retirement must remain available when an origin was corrected or its
        # consent withdrawn. This snapshot is never a provider prompt or readback.
        self.observations._scope()
        self.store.administrator(viewer)
        self.observations.game.unpaused(c)
        scene = self.observations._scene(c, scene_id, viewer)
        state = self.observations._state(c, scene_id)
        if state.policy.mode != "shadow" or not self.observations._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent is required.")
        refs = self._active(c, scene_id)
        return _digest(
            {
                "guard": self.observations._guard(c, scene, state),
                "references": [x.model_dump(mode="json") for x in refs],
            }
        ), refs

    def archive_review(self, viewer: GuildViewer, scene_id: str) -> dict[str, Any]:
        """Metadata-only retirement review, including references blocked by old consent."""
        with self.store.engine.connect() as c:
            revision, refs = self._archive_snapshot(c, viewer, scene_id)
            return {
                "revision": revision,
                "references": [
                    {"id": ref.id, "dependencies": list(ref.dependencies)} for ref in refs
                ],
            }

    def archive(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        expected_revision: str,
        reference_ids: tuple[str, ...],
        reason: str,
    ) -> dict[str, str | int]:
        """Retire explicit prompt references, preserving history and fictional knowledge."""
        import json

        self.observations._scope()

        def authorize(c: Connection) -> None:
            self._archive_snapshot(c, viewer, scene_id)

        def operation(c: Connection) -> dict[str, str | int]:
            revision, references = self._archive_snapshot(c, viewer, scene_id)
            selected = set(reference_ids)
            if revision != expected_revision:
                raise WorkflowError("STALE_CONTEXT: refresh references before archival.")
            if (
                not selected
                or len(selected) != len(reference_ids)
                or not selected <= {x.id for x in references}
                or not reason.strip()
                or len(reason) > 1200
            ):
                raise WorkflowError("INVALID_ARCHIVE: select current references and give a reason.")
            if any(
                selected.intersection(x.dependencies) for x in references if x.id not in selected
            ):
                raise WorkflowError("ACTIVE_DEPENDENCY: retain prerequisites or retire dependents.")
            identity = "reference-archive:" + str(uuid4())
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(
                        {
                            "id": identity,
                            "record_type": "reference_archive",
                            "scene_id": scene_id,
                            "owner_id": str(viewer.user_id),
                            "reference_ids": reference_ids,
                            "reason": reason,
                        }
                    ),
                )
            )
            state = self.observations._state(c, scene_id)
            self.observations._save(
                c, scene_id, state.model_copy(update={"generation": state.generation + 1})
            )
            return {"id": identity, "retired": len(selected)}

        return self.store._write(
            viewer,
            key,
            "director.reference_archive",
            {
                "scene": scene_id,
                "revision": expected_revision,
                "reference_ids": reference_ids,
                "reason": reason,
            },
            operation,
            authorize=authorize,
        )

    def record(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        expected_order: int,
        *,
        known_by: tuple[ActorRef, ...] = (),
        dependencies: tuple[str, ...] = (),
        topic: Literal[
            "general", "objective", "scope", "status", "briefing", "tactical", "debrief"
        ] = "general",
    ) -> dict[str, str | int]:
        self.observations._scope()

        def authorize(c: Connection) -> None:
            self.store.administrator(viewer)
            scene = self.observations._scene(c, scene_id, viewer)
            state = self.observations._state(c, scene_id)
            if state.policy.mode != "shadow" or not self.observations._consented(c, scene, state):
                raise WorkflowError("OBSERVATION_DISABLED: current consent is required.")

        def operation(c: Connection) -> dict[str, str | int]:
            self.observations.game.unpaused(c)
            prior = self._references(c, scene_id)
            current = self._active(c, scene_id)
            if len(current) >= 100 and source_id not in {x.source_id for x in current}:
                raise WorkflowError("CONTEXT_LIMIT: explicit archival is required.")
            if len(prior) != expected_order:
                raise WorkflowError("STALE_CHRONOLOGY: refresh the explicit scene order.")
            if not set(dependencies) <= {x.id for x in current}:
                raise WorkflowError("INVALID_CHRONOLOGY: dependencies must precede this reference.")
            approved = (
                self._approved_outcome(c, scene_id, source_id)
                if source_id.startswith("gm-narration:")
                else None
            )
            world = (
                self._approved_world(c, scene_id, source_id)
                if source_id.startswith("world-disclosure:")
                else None
            )
            source = (
                self.observations._latest_source(c, source_id)
                if approved is None and world is None
                else None
            )
            inputs = t.director["inputs"]
            if (
                approved is None
                and world is None
                and (
                    source is None
                    or not c.scalar(
                        sa.select(inputs.c.source_id)
                        .where(
                            inputs.c.campaign_id == self.store.campaign_id,
                            inputs.c.scene_id == scene_id,
                            inputs.c.source_id == source_id,
                        )
                        .limit(1)
                    )
                )
            ):
                raise WorkflowError("SOURCE_UNAVAILABLE: use this scene’s actual observation.")
            scene = self.observations._scene(c, scene_id, viewer)
            if source is not None and source.audience_ids != tuple(
                sorted(str(x) for x in scene["participants"])
            ):
                raise WorkflowError("SOURCE_SCOPE_CHANGED: privacy reconciliation is required.")
            source_revision = (
                source.source_revision if source else world["revision"] if world else 1
            )
            if world is not None and not set(known_by) <= {
                ActorRef.model_validate(actor) for actor in world["recipients"]
            }:
                raise WorkflowError(
                    "INVALID_RECIPIENT: retain the approved world disclosure scope."
                )
            if (
                source is not None
                and source.fictional_channel == "private"
                and any(actor != source.actor for actor in known_by)
            ):
                raise WorkflowError(
                    "UNPROVEN_DISCLOSURE: private narration is known only to its actor."
                )
            tokens = []
            for actor in known_by:
                if actor.kind not in ("pilot", "handler", "npc"):
                    raise WorkflowError("UNSUPPORTED_ACTOR: use a supported actual scene actor.")
                from girlframe.engine.m3_actors import resolve
                from girlframe.services.m2_state import load_state
                from girlframe.services.m3_actors import profiles

                canon = load_state(c, self.store.campaign_id)
                try:
                    actual = resolve(
                        canon,
                        actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    if actual.controller not in scene["participants"] or not actual.alive:
                        raise ValueError("Unavailable actor")
                    cast = next((x for x in canon.scene_casts if x.id == scene_id and x.open), None)
                    if actor.kind == "npc" and cast is None:
                        raise ValueError("NPC presence requires explicit casting")
                    if cast is not None:
                        from girlframe.engine.m3_cast import validate_role

                        validate_role(cast, actual)
                except ValueError:
                    raise WorkflowError("STALE_ACTOR: use an actual current scene role.") from None
                tokens.append(actor.token)
            for previous in prior:
                if previous.source_id == source_id and previous.source_revision == source_revision:
                    tokens.extend(previous.known_by)
            reference = KnowledgeReference(
                id=str(uuid4()),
                source_id=source_id,
                source_revision=source_revision,
                order=len(prior) + 1,
                dependencies=dependencies,
                known_by=tuple(sorted(set(tokens))),
                topic=topic,
                classification="approved_outcome"
                if approved
                else "established_world"
                if world
                else "reported_claim"
                if source and source.kind == "message"
                else "committed_play",
                text=approved["text"]
                if approved
                else "Established world: " + world["text"]
                if world
                else ("Reported claim: " + (source.text or ""))
                if source and source.kind == "message"
                else "Committed native Keep Your Head outcome; use the original receipt.",
            )
            c.execute(
                t.director_context["knowledge"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=reference.id,
                    body_json=reference.model_dump_json(),
                )
            )
            return {"id": reference.id, "order": reference.order}

        # Knowledge assignments are part of semantic intent, not identity verification.
        return self.store._write(
            viewer,
            key,
            "director.reference",
            {
                "scene_id": scene_id,
                "source_id": source_id,
                "known_by": [x.model_dump(mode="json") for x in known_by],
                "dependencies": dependencies,
                **({"topic": topic} if topic != "general" else {}),
            },
            operation,
            authorize=authorize,
        )

    def build(
        self, viewer: GuildViewer, scene_id: str, *, actor: ActorRef | None = None
    ) -> DirectorContext:
        self.observations._scope()
        with self.store.transaction() as c:
            return self._build(c, viewer, scene_id, actor=actor)

    def _build(
        self, c: Connection, viewer: GuildViewer, scene_id: str, *, actor: ActorRef | None = None
    ) -> DirectorContext:
        scene = self.observations._scene(c, scene_id, viewer)
        state = self.observations._state(c, scene_id)
        if state.policy.mode != "shadow" or not self.observations._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: current consent is required.")
        references = self._current(c, scene_id)
        audience: Literal["gm", "actor"]
        if actor is None:
            self.store.administrator(viewer)
            audience = "gm"
        else:
            if actor.kind == "npc":
                from girlframe.engine.m3_cast import validate_role
                from girlframe.services.m2_state import load_state
                from girlframe.services.m3_actors import ActorService
                from girlframe.services.m3_missions import MissionService

                canon = load_state(c, self.store.campaign_id)
                actual_view = ActorService(MissionService(self.store))._actor(
                    c, viewer, canon, actor
                )
                cast = next((x for x in canon.scene_casts if x.id == scene_id and x.open), None)
                if cast is None:
                    raise WorkflowError(
                        "ACTOR_UNAVAILABLE: NPC presence requires explicit casting."
                    )
                try:
                    validate_role(cast, actual_view)
                except ValueError:
                    raise WorkflowError("ACTOR_UNAVAILABLE: recover actual NPC casting.") from None
                actual = actual_view.ref
            else:
                _, _, actual = self.observations._authorize_input(c, viewer, scene_id, actor.kind)
            if actual != actor:
                raise WorkflowError("ACTOR_UNAVAILABLE: use your own actual role.")
            references = self._actor_references(references, actor)
            audience = "actor"
        return DirectorContext(
            campaign_id=self.store.campaign_id,
            scene_id=scene_id,
            audience=audience,
            actor=actor,
            references=references,
            revision=_digest(
                {
                    "guard": self.observations._guard(c, scene, state),
                    "references": [x.model_dump(mode="json") for x in references],
                }
            ),
        )

    def _handler_for_request(
        self, c: Connection, requester: GuildViewer, scene_id: str
    ) -> DirectorContext:
        """Server-mediated Handler view; requester is never impersonated as the Handler."""
        from girlframe.engine.m3_actors import resolve
        from girlframe.engine.m3_cast import validate_role
        from girlframe.engine.m3_handler_consequences import active_handler
        from girlframe.services.handler_setup import HandlerService
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_actors import profiles

        self.observations._scope()
        scene = self.observations._scene(c, scene_id, requester)
        state = self.observations._state(c, scene_id)
        if state.policy.mode != "shadow" or not self.observations._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent is required.")
        canon = load_state(c, self.store.campaign_id)
        appointment_revision, appointment = HandlerService(self.store).current(c)
        actor = active_handler(canon)
        if (
            actor is None
            or appointment.handler_id != canon.handler
            or canon.handler not in scene["participants"]
        ):
            raise WorkflowError(
                "HANDLER_UNAVAILABLE: require the actual current appointed scene Handler."
            )
        try:
            actual = resolve(
                canon, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if not actual.alive or actual.controller != appointment.handler_id:
                raise ValueError("Unavailable Handler")
            cast = next((x for x in canon.scene_casts if x.id == scene_id and x.open), None)
            if cast is not None:
                validate_role(cast, actual)
        except ValueError:
            raise WorkflowError("HANDLER_UNAVAILABLE: recover the actual Handler role.") from None
        refs = self._actor_references(self._current(c, scene_id), actor)
        return DirectorContext(
            campaign_id=self.store.campaign_id,
            scene_id=scene_id,
            audience="actor",
            actor=actor,
            references=refs,
            revision=_digest(
                {
                    "guard": self.observations._guard(c, scene, state),
                    "appointment_revision": appointment_revision,
                    "references": [x.model_dump(mode="json") for x in refs],
                }
            ),
        )
