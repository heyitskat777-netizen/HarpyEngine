"""Offer sourced memories for facilitator review at an Activity scene opening."""

import json
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.ai.director_dossiers import DossierPerspective, DossierPressure
from girlframe.database import tables as t
from girlframe.services import campaign_time_history as calendar
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_continuity import SceneContinuityService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


@dataclass(frozen=True)
class MemorySuggestion:
    review: dict[str, Any]
    references: tuple[KnowledgeReference, ...]
    existing: dict[str, str]


class SceneMemoryReview:
    def __init__(self, context: DirectorContextService):
        self.context = context
        self.store = context.store
        self.observer = context.observations
        self.continuity = SceneContinuityService(context)
        self.dossiers = DirectorDossierService(context)

    def scope(self, c: Connection, viewer: GuildViewer, row: dict[str, Any]) -> None:
        self.observer._scope()
        self.store.administrator(viewer)
        self.observer.game.unpaused(c)
        self.observer.game.scene_unpaused(c, row["id"])
        state = self.observer._state(c, row["id"])
        if (
            viewer.user_id not in row["participants"]
            or state.activity_epoch is None
            or state.policy.mode != "shadow"
            or not self.observer._consented(c, row, state)
        ):
            raise WorkflowError(
                "OBSERVATION_DISABLED: review memory in a consented Activity scene."
            )

    def _scenes(self, c: Connection, dossier_sources: set[str]) -> list[tuple[str, str, str]]:
        scenes = t.m2["m2_scenes"]
        bindings = t.m3["m3_scene_contexts"]
        knowledge = t.director_context["knowledge"]
        body = knowledge.c.body_json
        return [
            (identity, channel, people)
            for identity, channel, people in c.execute(
                sa.select(scenes.c.id, scenes.c.channel_id, scenes.c.participants_json)
                .join(
                    bindings,
                    (bindings.c.campaign_id == scenes.c.campaign_id)
                    & (bindings.c.id == scenes.c.id),
                )
                .join(t.events, t.events.c.id == bindings.c.binding_event)
                .where(
                    scenes.c.campaign_id == self.store.campaign_id,
                    scenes.c.open.is_(False),
                    sa.exists().where(
                        knowledge.c.campaign_id == scenes.c.campaign_id,
                        knowledge.c.scene_id == scenes.c.id,
                        sa.func.json_extract(body, "$.origin_scene").is_(None),
                        sa.or_(
                            knowledge.c.id.in_(dossier_sources),
                            sa.and_(
                                sa.func.json_extract(body, "$.classification") == "reported_claim",
                                sa.or_(
                                    sa.func.json_extract(body, "$.source_revision") > 1,
                                    sa.func.json_extract(body, "$.relations").is_not(None),
                                ),
                            ),
                        ),
                    ),
                )
                .order_by(t.events.c.seq.desc())
            )
        ]

    @staticmethod
    def _selection(
        refs: dict[str, KnowledgeReference],
        roots: tuple[str, ...],
        target: DirectorContext,
        source: str,
    ) -> tuple[tuple[KnowledgeReference, ...], dict[str, str]] | None:
        if not roots:
            return None
        by_source = {ref.source_id: ref for ref in target.references}
        required = set(roots)
        pending = list(roots)
        while pending:
            ref = refs.get(pending.pop())
            if ref is None:
                return None
            new = set(ref.dependencies) - required
            required.update(new)
            pending.extend(new)
        selected = tuple(ref for identity, ref in refs.items() if identity in required)
        existing: dict[str, str] = {}
        for ref in selected:
            copied = by_source.get(ref.source_id)
            if copied is None:
                continue
            if (
                (copied.origin_scene, copied.origin_reference) != (source, ref.id)
                or copied.known_by != ref.known_by
                or copied.dependencies != tuple(existing.get(key) for key in ref.dependencies)
            ):
                return None
            existing[ref.id] = copied.id
        if set(roots) <= existing.keys():
            return None
        if len(target.references) + len(selected) - len(existing) > 100:
            return None
        return selected, existing

    def options(
        self, c: Connection, viewer: GuildViewer, row: dict[str, Any], location: str
    ) -> tuple[DirectorContext, list[MemorySuggestion]]:
        from girlframe.services.activity_scene_opening import opening_head

        target = self.context._build(c, viewer, row["id"])
        roles = {role.ref.token: role for role in self.dossiers.knowledge._actor_views(c, row)}
        canon = load_state(c, self.store.campaign_id)
        casts = {cast.id: cast for cast in canon.scene_casts}
        entries: list[tuple[str, str, DossierPerspective]] = []
        for token, role in roles.items():
            history = self.dossiers._records(canon, role.ref)
            if history and history[-1].controller == role.controller:
                state = history[-1].state
                entries.extend(("promise", token, entry) for entry in state.promises)
                entries.extend(
                    ("relationship_term", token, entry)
                    for entry in state.terms
                    if entry.subject.token in roles
                )
                entries.extend(
                    ("pressure", token, entry)
                    for entry in state.pressures
                    if not isinstance(entry, DossierPressure)
                    or entry.pressure.status in ("open", "deferred")
                )

        ranked = []
        dossier_sources = {key for _, _, entry in entries for key in entry.knowledge_refs}
        for index, (identity, channel, people) in enumerate(self._scenes(c, dossier_sources)):
            if set(json.loads(people)) != set(row["participants"]):
                continue
            try:
                self.observer.game.scene_unpaused(c, identity)
                _, source = self.continuity._source(c, viewer, identity)
            except WorkflowError:
                continue
            cast = casts.get(identity)
            controllers = {role.actor.token: role.controller for role in cast.roles} if cast else {}
            allowed = {
                token
                for token, role in roles.items()
                if controllers.get(token) == role.controller
                or token not in controllers
                and role.ref.kind in ("pilot", "handler")
            }
            refs = {
                ref.id: ref
                for ref in source.references
                if ref.origin_scene is None
                and ref.order >= 0
                and ref.known_by
                and set(ref.known_by) <= allowed
            }
            if not refs:
                continue
            head = opening_head(c, self.store.campaign_id, identity)
            booking = calendar.booking(c, self.store.campaign_id, identity)
            source_location: str = (
                json.loads(head.payload_json)["location"]
                if head
                else booking.location
                if booking
                else None
            ) or ""
            same_place = bool(
                location and location.strip().casefold() == source_location.strip().casefold()
            )
            choices: list[tuple[str, str | None, str, tuple[str, ...]]] = [
                (kind, roles[token].label, entry.text, entry.knowledge_refs)
                for kind, token, entry in entries
                if all(key in refs and token in refs[key].known_by for key in entry.knowledge_refs)
            ]
            choices.extend(
                ("corrected_report", None, ref.text, (ref.id,))
                for ref in reversed(tuple(refs.values()))
                if ref.classification == "reported_claim"
                and (
                    ref.source_revision > 1
                    or any(edge.kind == "corrects" for edge in ref.relations)
                )
            )
            for kind, character, text, roots in choices:
                selection = self._selection(refs, roots, target, identity)
                if selection is None:
                    continue
                selected, existing = selection
                review = {
                    "kind": kind,
                    "character": character,
                    "text": text,
                    "source_scene": identity,
                    "source_label": source_location or f"Scene in channel {channel}",
                    "sources": [
                        {
                            "id": ref.id,
                            "text": ref.text,
                            "audience": [roles[token].label for token in ref.known_by],
                        }
                        for ref in selected
                    ],
                }
                review["review"] = _digest((target.revision, source.revision, review))
                ranked.append((not same_place, index, MemorySuggestion(review, selected, existing)))
        ranked.sort(key=lambda item: item[:2])
        return target, [item[2] for item in ranked[:6]]
