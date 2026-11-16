"""Explicit synthetic reference chronology; observations never become automatic canon."""

from typing import Literal
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
        if len(rows) > 100:
            raise WorkflowError("CONTEXT_LIMIT: explicit reference archival is required.")
        return tuple(
            sorted((KnowledgeReference.model_validate_json(x) for x in rows), key=lambda x: x.order)
        )

    def _current(self, c: Connection, scene_id: str) -> tuple[KnowledgeReference, ...]:
        references = tuple({x.source_id: x for x in self._references(c, scene_id)}.values())
        for reference in references:
            source = self.observations._latest_source(c, reference.source_id)
            if source is None or source.source_revision != reference.source_revision:
                raise WorkflowError(
                    "STALE_KNOWLEDGE: source correction needs explicit reconciliation."
                )
        return references

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
        topic: Literal["general", "objective", "scope", "status"] = "general",
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
            if len(prior) >= 100:
                raise WorkflowError("CONTEXT_LIMIT: explicit archival is required.")
            if len(prior) != expected_order:
                raise WorkflowError("STALE_CHRONOLOGY: refresh the explicit scene order.")
            if not set(dependencies) <= {x.id for x in prior}:
                raise WorkflowError("INVALID_CHRONOLOGY: dependencies must precede this reference.")
            source = self.observations._latest_source(c, source_id)
            inputs = t.director["inputs"]
            if source is None or not c.scalar(
                sa.select(inputs.c.source_id)
                .where(
                    inputs.c.campaign_id == self.store.campaign_id,
                    inputs.c.scene_id == scene_id,
                    inputs.c.source_id == source_id,
                )
                .limit(1)
            ):
                raise WorkflowError("SOURCE_UNAVAILABLE: use this scene’s actual observation.")
            scene = self.observations._scene(c, scene_id, viewer)
            if source.audience_ids != tuple(sorted(str(x) for x in scene["participants"])):
                raise WorkflowError("SOURCE_SCOPE_CHANGED: privacy reconciliation is required.")
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
                if (
                    previous.source_id == source_id
                    and previous.source_revision == source.source_revision
                ):
                    tokens.extend(previous.known_by)
            reference = KnowledgeReference(
                id=str(uuid4()),
                source_id=source.source_id,
                source_revision=source.source_revision,
                order=len(prior) + 1,
                dependencies=dependencies,
                known_by=tuple(sorted(set(tokens))),
                topic=topic,
                classification="reported_claim" if source.kind == "message" else "committed_play",
                text=("Reported claim: " + (source.text or ""))
                if source.kind == "message"
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
            references = tuple(x for x in references if actor.token in x.known_by)
            visible = {x.id for x in references}
            references = tuple(
                x.model_copy(
                    update={
                        "known_by": (actor.token,),
                        "dependencies": tuple(d for d in x.dependencies if d in visible),
                    }
                )
                for x in references
            )
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
        refs = tuple(x for x in self._current(c, scene_id) if actor.token in x.known_by)
        visible = {x.id for x in refs}
        refs = tuple(
            x.model_copy(
                update={
                    "known_by": (actor.token,),
                    "dependencies": tuple(d for d in x.dependencies if d in visible),
                }
            )
            for x in refs
        )
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
