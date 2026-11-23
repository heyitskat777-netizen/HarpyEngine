"""Explicit same-roster scene handoff; no new knowledge, effects or player consent."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import DirectorContext, KnowledgeReference, KnowledgeRelation
from girlframe.database import tables as t
from girlframe.services.director_observation import _digest
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.director_context import DirectorContextService


def _relation_origins(
    context: "DirectorContextService", c: Connection, scene: str, reference: KnowledgeReference
) -> set[tuple[str, str, str]]:
    if not reference.relations:
        return set()
    history = {item.id: item for item in context._references(c, scene)}
    origins: set[tuple[str, str, str]] = set()
    for relation in reference.relations:
        target = history.get(relation.reference_id)
        if target is None:
            raise WorkflowError("STALE_CONTINUITY: reconcile the related account provenance.")
        origins.add(
            (relation.kind, target.origin_scene or scene, target.origin_reference or target.id)
        )
    return origins


def validate_origin(
    context: "DirectorContextService",
    c: Connection,
    reference: KnowledgeReference,
    *,
    destination_scene: str,
) -> None:
    scene_id = reference.origin_scene
    original = next(
        (x for x in context._references(c, scene_id or "") if x.id == reference.origin_reference),
        None,
    )
    row = (
        c.execute(
            sa.select(t.m2["m2_scenes"]).where(
                t.m2["m2_scenes"].c.campaign_id == context.store.campaign_id,
                t.m2["m2_scenes"].c.id == scene_id,
            )
        )
        .mappings()
        .first()
    )
    state = context.observations._state(c, scene_id or "")
    if (
        not row
        or row["open"]
        or state.policy.mode != "shadow"
        or not context.observations._consented(
            c, {"participants": json.loads(row["participants_json"])}, state
        )
        or original is None
        or original.origin_scene is not None
        or original.id in context._archived(c, scene_id or "")
        or not set(reference.known_by) <= set(original.known_by)
        or any(
            getattr(reference, name) != getattr(original, name)
            for name in (
                "source_id",
                "source_revision",
                "topic",
                "classification",
                "text",
                "reported_by",
            )
        )
    ):
        raise WorkflowError("STALE_CONTINUITY: reconcile the original knowledge and consent.")
    if _relation_origins(context, c, scene_id or "", original) != _relation_origins(
        context, c, destination_scene, reference
    ):
        raise WorkflowError("STALE_CONTINUITY: preserve the original account relationships.")
    if state.activity_epoch is not None:
        from girlframe.engine.m3_actors import resolve
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_actors import profiles

        canon = load_state(c, context.store.campaign_id)
        cast = next((cast for cast in canon.scene_casts if cast.id == scene_id), None)
        roles = (
            tuple(role for role in cast.roles if role.actor.token in reference.known_by)
            if cast
            else ()
        )
        if roles:
            current = profiles(c, context.store.campaign_id)
            for role in roles:
                try:
                    actor = resolve(canon, role.actor, current, require_current_profile=False)
                    if not actor.alive or actor.controller != role.controller:
                        raise ValueError("Original controller unavailable")
                except ValueError:
                    raise WorkflowError(
                        "STALE_CONTINUITY: retain the original role and controller."
                    ) from None
    if original.source_id.startswith("npc-delivery:"):
        from girlframe.services.director_npc_delivery import NpcDeliveryService

        NpcDeliveryService(context).validate_reference(
            c, scene_id or "", original, allow_closed=True
        )
    elif original.source_id.startswith("knowledge-acquired:"):
        from girlframe.services.director_knowledge import DirectorKnowledgeService

        DirectorKnowledgeService(context).validate_reference(
            c, scene_id or "", original, allow_closed=True
        )
    elif original.source_id.startswith("handler-delivery:"):
        from girlframe.services.director_handler_delivery import validate_delivery_reference

        validate_delivery_reference(context, c, scene_id or "", original)
    elif original.classification == "approved_outcome":
        record = context._approved_outcome(c, scene_id or "", original.source_id, allow_closed=True)
        if original.source_revision != 1 or original.text != record["text"]:
            raise WorkflowError("STALE_CONTINUITY: the original outcome changed.")
    elif original.classification == "established_world":
        from girlframe.engine.m3_actor_state import ActorRef

        record = context._approved_world(c, scene_id or "", original.source_id, allow_closed=True)
        if (
            original.source_revision != record["revision"]
            or original.text != "Established world: " + record["text"]
            or not set(original.known_by)
            <= {ActorRef.model_validate(actor).token for actor in record["recipients"]}
        ):
            raise WorkflowError("STALE_CONTINUITY: the original world disclosure changed.")
    else:
        source = context.observations._latest_source(c, original.source_id)
        if source is None or source.source_revision != original.source_revision:
            raise WorkflowError("STALE_CONTINUITY: the original source changed.")


class SceneContinuityService:
    def __init__(self, context: "DirectorContextService"):
        self.context = context
        self.observer = context.observations
        self.store = context.store

    def _source(
        self, c: Connection, viewer: GuildViewer, scene_id: str
    ) -> tuple[dict[str, Any], DirectorContext]:
        self.store.administrator(viewer)
        self.observer.game.unpaused(c)
        scene = self.observer._scene(c, scene_id, viewer, allow_closed=True)
        state = self.observer._state(c, scene_id)
        if state.policy.mode != "shadow" or not self.observer._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: original scene consent is required.")
        refs = self.context._current(c, scene_id, allow_closed=True)
        return scene, DirectorContext(
            campaign_id=self.store.campaign_id,
            scene_id=scene_id,
            audience="gm",
            references=refs,
            revision=_digest(
                {
                    "guard": self.observer._guard(c, scene, state),
                    "open": scene["open"],
                    "references": [x.model_dump(mode="json") for x in refs],
                }
            ),
        )

    def preview(self, viewer: GuildViewer, source_scene: str) -> DirectorContext:
        """Private, read-only handoff source; the preceding scene may be closed."""
        self.observer._scope()
        with self.store.engine.connect() as c:
            return self._source(c, viewer, source_scene)[1]

    def carry(
        self,
        viewer: GuildViewer,
        key: str,
        source_scene: str,
        target_scene: str,
        source_revision: str,
        target_revision: str,
        reference_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        self.observer._scope()

        def authorize(c: Connection) -> None:
            self.store.administrator(viewer)
            self.observer.game.unpaused(c)
            for identity in (source_scene, target_scene):
                scene = self.observer._scene(
                    c, identity, viewer, allow_closed=identity == source_scene
                )
                state = self.observer._state(c, identity)
                if state.policy.mode != "shadow" or not self.observer._consented(c, scene, state):
                    raise WorkflowError(
                        "OBSERVATION_DISABLED: both scenes require current consent."
                    )

        def operation(c: Connection) -> dict[str, Any]:
            if (
                source_scene == target_scene
                or not reference_ids
                or len(set(reference_ids)) != len(reference_ids)
            ):
                raise WorkflowError("Select distinct existing references for a different scene.")
            before, source = self._source(c, viewer, source_scene)
            if before["open"]:
                raise WorkflowError(
                    "SCENE_REPORT_OPEN: close the original scene before carrying knowledge."
                )
            target = self.context._build(c, viewer, target_scene)
            if (source.revision, target.revision) != (source_revision, target_revision):
                raise WorkflowError("STALE_CONTEXT: reopen both scene contexts.")
            after = self.observer._scene(c, target_scene)
            if set(before["participants"]) != set(after["participants"]):
                raise WorkflowError("CONTINUITY_SCOPE: only the same roster is supported.")
            selected = [x for x in source.references if x.id in reference_ids]
            if len(selected) != len(reference_ids) or any(
                not set(x.dependencies) <= set(reference_ids) for x in selected
            ):
                raise WorkflowError(
                    "CONTINUITY_DEPENDENCY: select actual references and dependencies."
                )
            return self._copy(c, source_scene, after, target, tuple(selected), {})

        return self.store._write(
            viewer,
            key,
            "director.scene_handoff",
            {
                "source_scene": source_scene,
                "target_scene": target_scene,
                "source_revision": source_revision,
                "target_revision": target_revision,
                "reference_ids": reference_ids,
            },
            operation,
            authorize=authorize,
        )

    def _copy(
        self,
        c: Connection,
        source_scene: str,
        after: dict[str, Any],
        target: DirectorContext,
        selected: tuple[KnowledgeReference, ...],
        existing: dict[str, str],
    ) -> dict[str, Any]:
        target_scene = target.scene_id
        if len(target.references) + len(selected) - len(existing) > 100:
            raise WorkflowError("CONTEXT_LIMIT: archive explicitly before carrying references.")
        tokens = {x for ref in selected for x in ref.known_by}
        from girlframe.engine.m3_actor_state import ActorRef
        from girlframe.engine.m3_actors import resolve
        from girlframe.engine.m3_cast import validate_role
        from girlframe.engine.m3_handler_consequences import active_handler
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_actors import profiles

        canon = load_state(c, self.store.campaign_id)
        cast = next((x for x in canon.scene_casts if x.id == target_scene and x.open), None)
        actors = [r.actor for r in cast.roles] if cast is not None else []
        for uid in after["participants"]:
            if str(uid) in canon.sheets:
                actors.append(
                    ActorRef(
                        kind="pilot",
                        entity=str(uid),
                        incarnation=self.observer.game.character_binding(
                            c, canon, int(uid), require_current_profile=False
                        ),
                    )
                )
        handler = active_handler(canon)
        if handler is not None:
            actors.append(handler)
        actor_map = {actor.token: actor for actor in actors}
        for token in tokens:
            try:
                if token not in actor_map:
                    raise ValueError("Unknown original actor")
                actual = resolve(
                    canon,
                    actor_map[token],
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if actual.controller not in after["participants"] or not actual.alive:
                    raise ValueError("Unavailable actor")
                if actual.ref.kind == "npc" and cast is None:
                    raise ValueError("Explicit NPC casting required")
                if cast is not None:
                    validate_role(cast, actual)
            except ValueError:
                raise WorkflowError("STALE_ACTOR: recover the actual destination role.") from None
        ids = existing | {x.id: str(uuid4()) for x in selected if x.id not in existing}
        order = len(self.context._references(c, target_scene))
        for ref in selected:
            if ref.id in existing:
                continue
            order += 1
            copied = ref.model_copy(
                update={
                    "id": ids[ref.id],
                    "order": order,
                    "dependencies": tuple(ids[d] for d in ref.dependencies),
                    "relations": tuple(
                        KnowledgeRelation(
                            kind=relation.kind, reference_id=ids[relation.reference_id]
                        )
                        for relation in ref.relations
                    ),
                    "origin_scene": ref.origin_scene or source_scene,
                    "origin_reference": ref.origin_reference or ref.id,
                }
            )
            c.execute(
                t.director_context["knowledge"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=target_scene,
                    id=copied.id,
                    body_json=copied.model_dump_json(),
                )
            )
        return {
            "source_scene": source_scene,
            "target_scene": target_scene,
            "references": ids,
            "effects_applied": False,
        }
