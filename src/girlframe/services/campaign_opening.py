"""Private, revisioned opening-scene drafts and previews for the actual cast."""

from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import Field, field_validator
from sqlalchemy import Connection

from girlframe.ai.contracts import Contract
from girlframe.ai.director import KnowledgeReference
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.handler_setup import HandlerService
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


class SessionZero(Contract):
    tone: str = Field(default="", max_length=300)
    offscreen: str = Field(default="", max_length=800)
    handler_initiative: Literal["respond when called", "also offer help when needed"] = (
        "respond when called"
    )
    human_fallback: str = Field(default="", max_length=300)


class OpeningDraft(Contract):
    location: str = Field(min_length=1, max_length=160)
    situation: str = Field(min_length=1, max_length=800)
    first_choice: str = Field(min_length=1, max_length=500)
    gm_pressure: str = Field(default="", max_length=800)
    facts: tuple[OpeningFact, ...] = Field(default=(), max_length=16)
    session_zero: SessionZero = Field(default_factory=SessionZero)
    npc_pilots: tuple[str, ...] = Field(default=(), max_length=25)

    @field_validator("location", "situation", "first_choice")
    @classmethod
    def meaningful(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Use meaningful opening scene text.")
        return value.strip()


class SavedOpening(Contract):
    revision: int
    draft: OpeningDraft


class OpeningRelease(Contract):
    revision: int
    cast: tuple[ActorRef, ...]
    controllers: dict[str, int]
    participants: tuple[int, ...]
    consent_generation: int | None


class CampaignOpeningService:
    def __init__(
        self,
        knowledge: DirectorKnowledgeService,
        *,
        facilitator_id: int | None = None,
        managed_setup: bool = False,
    ):
        self.knowledge, self.observer, self.store = knowledge, knowledge.observer, knowledge.store
        self.facilitator_id = facilitator_id
        self.managed_setup = managed_setup

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        self.observer.game.authorize(c, viewer, game=False)
        if self.facilitator_id == viewer.user_id:
            HandlerService(self.store).authorize(c, viewer)
        else:
            self.store.administrator(viewer)
        return self.observer._scene(c, scene)

    def _latest(
        self, c: Connection, scene: str, revision: int | None = None
    ) -> SavedOpening | None:
        table = t.director_context["shadow"]
        identity = (
            table.c.id.like(f"opening:{scene}:%")
            if revision is None
            else table.c.id == f"opening:{scene}:{revision:012d}"
        )
        raw = c.scalar(
            sa.select(table.c.body_json)
            .where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                identity,
            )
            .order_by(table.c.id.desc())
            .limit(1)
        )
        return SavedOpening.model_validate_json(raw) if raw else None

    def _release(self, c: Connection, scene: str) -> OpeningRelease | None:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == "opening-release:" + scene,
            )
        )
        return OpeningRelease.model_validate_json(raw) if raw else None

    def _review(
        self,
        c: Connection,
        row: dict[str, Any],
        saved: SavedOpening | None,
        cast: tuple[ActorView, ...],
    ) -> tuple[str, list[str]]:
        state = self.observer._state(c, row["id"])
        blockers = []
        if not saved:
            blockers.append("Save an opening draft.")
        if self.managed_setup:
            from girlframe.services.campaign_difficulty import historical_mission, opening

            record = opening(c, self.store.campaign_id)
            if record is None and not historical_mission(c, self.store.campaign_id):
                blockers.append(
                    "Complete Session Zero and its introductory days before publishing."
                )
            elif record and record.scene == row["id"]:
                blockers.append("Publish briefing facts in the first playable mission scene.")
        try:
            self.observer.game.unpaused(c)
        except WorkflowError:
            blockers.append("The participants who paused play must clear their safety pauses.")
        if not cast:
            blockers.append("An active character must join the opening scene.")
        elif saved and not self._valid_audience(saved.draft, cast):
            blockers.append("Review the starting facts for the current cast.")
        if self.observer.synthetic and (
            state.policy.mode != "shadow" or not self.observer._consented(c, row, state)
        ):
            pending = sorted(
                {
                    actor.label
                    for actor in cast
                    if state.consents.get(str(actor.controller)) != state.policy_revision
                }
            )
            if state.policy.mode != "shadow":
                blockers.append("The facilitator must enable synthetic scene review.")
            elif pending:
                blockers.extend(f"{name} needs to review observation consent." for name in pending)
            else:
                blockers.append(
                    "Check scene membership and each participant’s observation consent."
                )
        return _digest(
            {
                "draft": saved.revision if saved else 0,
                "scene": row["id"],
                "scene_revision": row["revision"],
                "cast": sorted((actor.ref.token, actor.controller) for actor in cast),
                "policy": state.policy_revision,
                "consent": state.consent_generation,
            }
        ), blockers

    def view(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        """Only the facilitator can preview another actor's proposed opening facts."""
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            row = self._scope(c, viewer, scene)
            saved = self._latest(c, scene)
            release = self._release(c, scene)
            cast = self.knowledge._actor_views(c, row)
            fingerprint, blockers = self._review(c, row, saved, cast)
            roles = [
                {"id": actor.ref.token, "label": actor.label, "kind": actor.ref.kind}
                for actor in cast
            ]
            facts = saved.draft.facts if saved else ()
            return {
                "revision": saved.revision if saved else 0,
                "review": fingerprint,
                "blockers": blockers,
                "launched": release is not None,
                "draft": saved.draft.model_dump(mode="json") if saved else None,
                "roles": roles,
                "previews": [
                    role | {"facts": [fact.text for fact in facts if role["id"] in fact.known_by]}
                    for role in roles
                ],
                "stale_audience": saved is not None and not self._valid_audience(saved.draft, cast),
            }

    @staticmethod
    def _valid_audience(draft: OpeningDraft, cast: tuple[ActorView, ...]) -> bool:
        available = {actor.ref.token for actor in cast}
        pilots = {actor.ref.token for actor in cast if actor.ref.kind == "pilot"}
        return (
            len(draft.npc_pilots) == len(set(draft.npc_pilots))
            and set(draft.npc_pilots) <= pilots
            and all(
                len(fact.known_by) == len(set(fact.known_by)) and set(fact.known_by) <= available
                for fact in draft.facts
            )
        )

    def save(
        self, viewer: GuildViewer, key: str, scene: str, expected: int, draft: OpeningDraft
    ) -> dict[str, int]:
        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)

        def operation(c: Connection) -> dict[str, int]:
            if self._release(c, scene):
                raise WorkflowError("OPENING_LAUNCHED: use the scene for further developments.")
            current = self._latest(c, scene)
            if expected != (current.revision if current else 0):
                raise WorkflowError("STALE_OPENING: reopen the saved opening before editing.")
            cast = self.knowledge._actor_views(c, self.observer._scene(c, scene))
            if not self._valid_audience(draft, cast):
                raise WorkflowError(
                    "OPENING_AUDIENCE: use distinct actors in the current native cast."
                )
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

    @staticmethod
    def _entries(
        draft: OpeningDraft, cast: tuple[ActorRef, ...]
    ) -> list[tuple[str, tuple[str, ...]]]:
        everyone = tuple(ref.token for ref in cast)
        entries = [
            ("Location: " + draft.location, everyone),
            ("Opening situation: " + draft.situation, everyone),
            ("First decision: " + draft.first_choice, everyone),
            *((fact.text, fact.known_by) for fact in draft.facts),
        ]
        if draft.gm_pressure.strip():
            entries.append(("Campaign pressure: " + draft.gm_pressure, ()))
        return entries

    def launch(self, viewer: GuildViewer, key: str, scene: str, review: str) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)

        def operation(c: Connection) -> dict[str, Any]:
            if self._release(c, scene):
                raise WorkflowError("OPENING_LAUNCHED: this scene has a saved launch.")
            row = self.observer._scene(c, scene)
            saved = self._latest(c, scene)
            cast = self.knowledge._actor_views(c, row)
            fingerprint, blockers = self._review(c, row, saved, cast)
            if review != fingerprint:
                raise WorkflowError("STALE_OPENING: refresh the draft, cast and consent review.")
            if saved is None or blockers:
                raise WorkflowError("OPENING_BLOCKED: " + " ".join(blockers))
            state = self.observer._state(c, scene)
            release = OpeningRelease(
                revision=saved.revision,
                cast=tuple(actor.ref for actor in cast),
                controllers={actor.ref.token: actor.controller for actor in cast},
                participants=tuple(sorted(row["participants"])),
                consent_generation=state.consent_generation if self.observer.synthetic else None,
            )
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene,
                    id="opening-release:" + scene,
                    body_json=release.model_dump_json(),
                )
            )
            if release.consent_generation is not None:
                context = self.knowledge.context
                entries = self._entries(saved.draft, release.cast)
                if len(context._active(c, scene)) + len(entries) > 100:
                    raise WorkflowError("CONTEXT_LIMIT: retire references before launching.")
                offset = len(context._references(c, scene))
                for i, (text, recipients) in enumerate(entries):
                    ref = KnowledgeReference(
                        id=str(uuid4()),
                        source_id=f"opening-source:{scene}:{i}",
                        source_revision=saved.revision,
                        order=offset + i + 1,
                        known_by=recipients,
                        topic="briefing" if i != 2 else "objective",
                        classification="established_world",
                        text="Established world: " + text,
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
                self.observer._save(
                    c, scene, state.model_copy(update={"generation": state.generation + 1})
                )
            return {"launched": True, "revision": saved.revision}

        return self.store._write(
            viewer,
            key,
            "campaign.opening_launched",
            {
                "scene": scene,
                "review": review,
            },
            operation,
            authorize=authorize,
        )

    def brief(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            row = self.observer._scene(c, scene, viewer)
            release = self._release(c, scene)
            saved = self._latest(c, scene, release.revision) if release else None
            if release is None or saved is None:
                return {"launched": False}
            own = [
                actor
                for actor in self.knowledge._actor_views(c, row)
                if actor.controller == viewer.user_id
                and release.controllers.get(actor.ref.token) == viewer.user_id
            ]
            if not own:
                raise WorkflowError("OPENING_AUDIENCE: use one of your original cast roles.")
            return {
                "launched": True,
                "location": saved.draft.location,
                "situation": saved.draft.situation,
                "first_choice": saved.draft.first_choice,
                "session_zero": saved.draft.session_zero.model_dump(mode="json"),
                "roles": [
                    {
                        "label": actor.label,
                        "facts": [
                            f.text for f in saved.draft.facts if actor.ref.token in f.known_by
                        ],
                    }
                    for actor in own
                ],
            }

    def source(
        self, c: Connection, scene: str, identity: str, *, allow_closed: bool
    ) -> dict[str, Any]:
        release = self._release(c, scene)
        saved = self._latest(c, scene, release.revision) if release else None
        row = self.observer._scene(c, scene, allow_closed=allow_closed)
        state = self.observer._state(c, scene)
        if (
            not release
            or not saved
            or release.consent_generation != state.consent_generation
            or state.policy.mode != "shadow"
            or not self.observer._consented(c, row, state)
            or release.participants != tuple(sorted(row["participants"]))
        ):
            raise WorkflowError("STALE_OPENING_SOURCE: review the original scene and consent.")
        from girlframe.services.director_worldbuilding import DirectorWorldbuildingService

        for i, (text, tokens) in enumerate(self._entries(saved.draft, release.cast)):
            if identity != f"opening-source:{scene}:{i}":
                continue
            recipients = tuple(ref for ref in release.cast if ref.token in tokens)
            if DirectorWorldbuildingService(self.knowledge.context)._disclosure_actors(
                c, row, recipients, {"recipient_controllers": release.controllers}, allow_closed
            ):
                return {
                    "text": text,
                    "revision": saved.revision,
                    "recipients": [actor.model_dump(mode="json") for actor in recipients],
                }
            break
        raise WorkflowError("STALE_OPENING_SOURCE: retain the original actors and source.")
