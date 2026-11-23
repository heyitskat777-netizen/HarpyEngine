"""Publish shared scene framing through the existing ledger and cast authority."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Row

from girlframe.ai.activity_batch import scene_details
from girlframe.ai.conversation import RULES_IN_PROSE
from girlframe.database import tables as t
from girlframe.scenes.opening import OpeningDetail, OpeningDraft, SceneOpening
from girlframe.services import campaign_time_history as calendar
from girlframe.services.campaign_difficulty import review_facilitator
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.director_scene_memory import SceneMemoryReview
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "scene.opening_published"


def opening_head(c: Connection, campaign: str, scene: str) -> Row[tuple[str, str]] | None:
    return c.execute(
        sa.select(t.events.c.id, t.events.c.payload_json)
        .where(
            t.events.c.campaign_id == campaign,
            t.events.c.kind == EVENT,
            sa.func.json_extract(t.events.c.payload_json, "$.scene") == scene,
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    ).first()


class ActivitySceneOpening:
    def __init__(self, context: DirectorContextService, facilitator_id: int | None = None):
        self.context, self.store = context, context.store
        self.observer = context.observations
        self.knowledge = DirectorKnowledgeService(context)
        self.memory = SceneMemoryReview(context)
        self.facilitator_id = facilitator_id

    def _can_publish(self, c: Connection, viewer: GuildViewer) -> bool:
        if self.observer.reviewed_activity_trial:
            self.observer._check_activity_reviewer(c, viewer)
        fallback = self.store.policy.canon_facilitator_id or self.facilitator_id
        assigned = (
            review_facilitator(c, self.store.campaign_id, fallback)
            if self.observer.reviewed_activity_trial
            else fallback
        )
        if assigned is not None:
            return viewer.user_id == assigned
        return bool(viewer.is_administrator and self.store.policy.allow_guild_administrators)

    def _latest(self, c: Connection, scene: str) -> dict[str, Any]:
        row = opening_head(c, self.store.campaign_id, scene)
        return json.loads(row.payload_json) | {"receipt": row.id} if row else {}

    def _scope(self, c: Connection, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "binding": row["binding_event"],
            "participants": sorted(row["participants"]),
            "roles": {
                role.ref.token: role.controller for role in self.knowledge._actor_views(c, row)
            },
        }

    def _details(
        self, c: Connection, scene: str, scope: dict[str, Any]
    ) -> tuple[OpeningDetail, ...]:
        roles = scope["roles"]
        if not roles or set(scope["participants"]) != set(roles.values()):
            return ()
        state = self.observer._state(c, scene)
        if state.activity_epoch is not None:
            row = self.observer._scene(c, scene)
            if not self.observer._consented(c, row, state):
                return ()
        return tuple(
            OpeningDetail(id=ref.id, text=ref.text.removeprefix("Established world: "))
            for ref in scene_details(
                tuple(
                    ref
                    for ref in self.context._current(c, scene)
                    if roles.keys() <= set(ref.known_by) and not RULES_IN_PROSE.search(ref.text)
                ),
                limit=100,
            )
        )

    def current(self, c: Connection, row: dict[str, Any]) -> SceneOpening | None:
        scene = row["id"]
        latest = self._latest(c, scene)
        if not latest or latest["scope"] != (scope := self._scope(c, row)):
            return None
        details = self._details(c, scene, scope) if latest["details"] else ()
        indexed = {detail.id: detail.model_dump() for detail in details}
        selected = [part for part in latest["details"] if indexed.get(part["id"]) == part]
        # A retracted source is left in history. The renewed opening needs an explicit review.
        if len(selected) != len(latest["details"]):
            return None
        return SceneOpening.model_validate_json(
            json.dumps(
                {key: latest[key] for key in ("receipt", "location", "position", "intro")}
                | {"details": selected, "off_duty": latest.get("off_duty", False)}
            )
        )

    def _draft(self, c: Connection, row: dict[str, Any]) -> dict[str, Any]:
        scene, campaign = row["id"], self.store.campaign_id
        latest = self._latest(c, scene)
        previous = latest.get("receipt")
        booking = calendar.booking(c, campaign, scene)
        anchor = calendar.anchor(c, campaign)
        position = booking.start if booking else anchor[1].position if anchor else None
        scope = self._scope(c, row)
        details = self._details(c, scene, scope)
        location = latest.get("location") or (booking.location if booking else None) or ""
        if not latest and location:
            world = load_state(c, campaign).world
            if world is not None:
                location = next(
                    (place.name for place in world.locations if place.id == location), location
                )
        selected = (
            [detail.id for detail in details if detail.model_dump() in latest["details"]]
            if latest
            else [detail.id for detail in details[-2:]]
        )
        offered = set(selected) | {detail.id for detail in details[-3:]}
        draft = {
            "location": location,
            "position": position.model_dump(mode="json") if position else None,
            "intro": latest.get("intro", ""),
            "suggestions": [detail.model_dump() for detail in details if detail.id in offered],
            "selected": selected,
        }
        if latest.get("off_duty"):
            draft["off_duty"] = True
        return draft | {"revision": _digest((previous, row["revision"], scope, draft))}

    def view(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.observer.game.authorize(c, viewer, game=False)
            can_publish = self._can_publish(c, viewer)
            row = self.observer._scene(c, scene, None if can_publish else viewer)
            opening = self.current(c, row)
            view: dict[str, Any] = {"opening": opening.model_dump(mode="json") if opening else None}
            if can_publish:
                draft = self._draft(c, row)
                view["draft"] = draft
                try:
                    self.memory.scope(c, viewer, row)
                except WorkflowError:
                    return view
                _, suggestions = self.memory.options(c, viewer, row, draft["location"])
                view["memory"] = [item.review for item in suggestions]
            return view

    def carry_memory(
        self, viewer: GuildViewer, key: str, scene: str, source: str, review: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            if not self._can_publish(c, viewer):
                raise WorkflowError(
                    "SCENE_OPENING_AUTHORITY: only the facilitator can carry memory."
                )
            row = self.observer._scene(c, scene, viewer)
            self.memory.scope(c, viewer, row)
            original = self.observer._scene(c, source, viewer, allow_closed=True)
            self.memory.scope(c, viewer, original)
            if original["open"] or set(original["participants"]) != set(row["participants"]):
                raise WorkflowError(
                    "STALE_SCENE_MEMORY: review a closed scene with the same roster."
                )

        def operation(c: Connection) -> dict[str, Any]:
            row = self.observer._scene(c, scene)
            target, options = self.memory.options(c, viewer, row, self._draft(c, row)["location"])
            suggestion = next(
                (
                    item
                    for item in options
                    if item.review["review"] == review and item.review["source_scene"] == source
                ),
                None,
            )
            if suggestion is None:
                raise WorkflowError(
                    "STALE_SCENE_MEMORY: refresh the scene opening and review again."
                )
            return self.memory.continuity._copy(
                c, source, row, target, suggestion.references, suggestion.existing
            )

        return self.store._write(
            viewer,
            key,
            "director.scene_memory_carry",
            {"scene": scene, "source_scene": source, "review": review},
            operation,
            authorize=authorize,
        )

    def publish(
        self, viewer: GuildViewer, key: str, scene: str, revision: str, draft: OpeningDraft
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.observer.game.authorize(c, viewer, game=False)
            if not self._can_publish(c, viewer):
                raise WorkflowError(
                    "SCENE_OPENING_AUTHORITY: only the scene facilitator can publish."
                )
            self.observer._scene(c, scene)
            self.observer.game.unpaused(c)
            self.observer.game.scene_unpaused(c, scene)

        def operation(c: Connection) -> dict[str, Any]:
            row = self.observer._scene(c, scene)
            suggested = self._draft(c, row)
            if suggested["revision"] != revision:
                raise WorkflowError("STALE_SCENE_OPENING: reopen the current scene framing.")
            details = {detail["id"]: detail for detail in suggested["suggestions"]}
            if not set(draft.details) <= details.keys():
                raise WorkflowError("SCENE_OPENING_DETAIL: use current shared details.")
            if any(RULES_IN_PROSE.search(text) for text in (draft.location, draft.intro)):
                raise WorkflowError("SCENE_OPENING_TEXT: keep mechanics out of the introduction.")
            record = {
                "scene": scene,
                "scope": self._scope(c, row),
                "location": draft.location,
                "position": suggested["position"],
                "intro": draft.intro.strip(),
                "details": [details[identity] for identity in draft.details],
            }
            off_duty = draft.off_duty if draft.off_duty is not None else suggested.get("off_duty")
            if off_duty:
                record["off_duty"] = True
            receipt = self.store._audit(c, viewer.user_id, key, EVENT, record)
            return {"receipt": receipt}

        return self.store._write(
            viewer,
            key,
            EVENT,
            {"scene": scene, "revision": revision, **draft.model_dump(mode="json")},
            operation,
            authorize=authorize,
            auto_audit=False,
        )
