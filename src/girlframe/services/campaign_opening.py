"""Private, revisioned opening-scene drafts and previews for the actual cast."""

from typing import Any

import sqlalchemy as sa
from pydantic import Field, field_validator
from sqlalchemy import Connection

from girlframe.ai.contracts import Contract
from girlframe.database import tables as t
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class OpeningFact(Contract):
    text: str = Field(min_length=1, max_length=800)
    learned_from: str = Field(min_length=1, max_length=300)
    known_by: tuple[str, ...] = Field(default=(), max_length=25)

    @field_validator("text", "learned_from")
    @classmethod
    def meaningful(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Use meaningful opening fact and source text.")
        return value.strip()


class OpeningDraft(Contract):
    location: str = Field(min_length=1, max_length=160)
    situation: str = Field(min_length=1, max_length=800)
    first_choice: str = Field(min_length=1, max_length=500)
    gm_pressure: str = Field(default="", max_length=800)
    facts: tuple[OpeningFact, ...] = Field(default=(), max_length=16)

    @field_validator("location", "situation", "first_choice")
    @classmethod
    def meaningful(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Use meaningful opening scene text.")
        return value.strip()


class SavedOpening(Contract):
    revision: int
    draft: OpeningDraft


class CampaignOpeningService:
    def __init__(self, knowledge: DirectorKnowledgeService):
        self.knowledge, self.observer, self.store = knowledge, knowledge.observer, knowledge.store

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        self.store.administrator(viewer)
        self.observer.game.authorize(c, viewer, game=False)
        return self.observer._scene(c, scene)

    def _latest(self, c: Connection, scene: str) -> SavedOpening | None:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id.like(f"opening:{scene}:%"),
            )
            .order_by(table.c.id.desc())
            .limit(1)
        )
        return SavedOpening.model_validate_json(raw) if raw else None

    def view(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        """Only the facilitator can preview another actor's proposed opening facts."""
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            row = self._scope(c, viewer, scene)
            saved = self._latest(c, scene)
            roles = [
                {"id": actor.ref.token, "label": actor.label}
                for actor in self.knowledge._actor_views(c, row)
            ]
            allowed = {role["id"] for role in roles}
            facts = saved.draft.facts if saved else ()
            return {
                "revision": saved.revision if saved else 0,
                "draft": saved.draft.model_dump(mode="json") if saved else None,
                "roles": roles,
                "previews": [
                    role | {"facts": [fact.text for fact in facts if role["id"] in fact.known_by]}
                    for role in roles
                ],
                "stale_audience": any(set(fact.known_by) - allowed for fact in facts),
            }

    def save(
        self, viewer: GuildViewer, key: str, scene: str, expected: int, draft: OpeningDraft
    ) -> dict[str, int]:
        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)

        def operation(c: Connection) -> dict[str, int]:
            current = self._latest(c, scene)
            if expected != (current.revision if current else 0):
                raise WorkflowError("STALE_OPENING: reopen the saved opening before editing.")
            available = {
                role.token for role in self.knowledge._actors(c, self.observer._scene(c, scene))
            }
            if any(
                len(fact.known_by) != len(set(fact.known_by)) or set(fact.known_by) - available
                for fact in draft.facts
            ):
                raise WorkflowError("OPENING_AUDIENCE: use distinct actors in the current cast.")
            saved = SavedOpening(revision=expected + 1, draft=draft)
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene,
                    id=f"opening:{scene}:{saved.revision:012d}",
                    body_json=saved.model_dump_json(),
                )
            )
            return {"revision": saved.revision}

        return self.store._write(
            viewer,
            key,
            "campaign.opening_saved",
            {"scene": scene, "revision": expected, "draft": draft.model_dump(mode="json")},
            operation,
            authorize=authorize,
        )
