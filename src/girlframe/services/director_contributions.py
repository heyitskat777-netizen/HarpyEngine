"""Source-proved synthetic NPC report contributions; no real delivery or mechanics."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_dialogue import DirectorDialogueService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorContributionService:
    def __init__(self, dialogue: DirectorDialogueService):
        self.dialogue = dialogue
        self.context = dialogue.context
        self.observations = self.context.observations
        self.store = self.context.store

    def commit_synthetic_report(
        self, viewer: GuildViewer, key: str, scene_id: str, draft_id: str, venue_id: str
    ) -> dict[str, Any]:
        self.observations._scope()

        def authorize(c: Connection) -> None:
            self.dialogue._owned(c, viewer, scene_id, draft_id)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m2_state import load_state
            from girlframe.services.m3_actors import ActorService
            from girlframe.services.m3_appearance_matrix import prove_context
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_scene_requisitions import guard

            self.observations.game.unpaused(c)
            scene = self.observations._scene(c, scene_id, viewer)
            lock = self.observations.game.lock(c, scene["channel_id"])
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: preserve pending Play and human choices.")
            draft = self.dialogue._owned(c, viewer, scene_id, draft_id)
            actor = ActorRef.model_validate_json(json.dumps(draft["actor"]))
            if actor.kind != "npc":
                raise WorkflowError(
                    "UNSUPPORTED_SPEAKER: this adapter proves native NPC reports only."
                )
            current = self.context._build(c, viewer, scene_id, actor=actor)
            if current.revision != draft["context_revision"]:
                raise WorkflowError(
                    "STALE_CONTEXT: regenerate and approve this actual role’s draft."
                )
            table = t.director_context["shadow"]
            review = c.scalar(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene_id,
                    table.c.id == draft_id + ":review",
                )
            )
            if not review or json.loads(review).get("decision") != "approve":
                raise WorkflowError(
                    "REVIEW_REQUIRED: the actual controller must approve this draft."
                )
            canon = load_state(c, self.store.campaign_id)
            venue = prove_context(self.observations.game, c, canon, venue_id)
            actual = ActorService(MissionService(self.store))._actor(c, viewer, canon, actor)
            if (
                venue.scene != scene_id
                or actual.cell is None
                or actual.cell != venue.cell
                or actual.custody
            ):
                raise WorkflowError(
                    "PRESENCE_UNPROVEN: require the actual reachable NPC and scene location."
                )
            guard(c, self.store, scene_id, actor)
            # The template is recomputed, so storage or approval cannot authorize arbitrary prose.
            refs = {x.id: x for x in current.references}
            if not set(draft["source_refs"]) <= refs.keys():
                raise WorkflowError("UNKNOWN_KNOWLEDGE: recover actual source references.")
            text = "Reports available to me:\n" + "\n".join(
                json.dumps(refs[x].text, ensure_ascii=False) for x in draft["source_refs"]
            )
            if text != draft["text"]:
                raise WorkflowError(
                    "UNSUPPORTED_NARRATION: only the grounded report template is allowed."
                )
            identity = draft_id + ":contribution"
            if c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == identity
                )
            ):
                raise WorkflowError(
                    "CONTRIBUTION_FINAL: this draft already has a stable contribution."
                )
            result = {
                "id": identity,
                "scene_id": scene_id,
                "actor": draft["actor"],
                "owner_id": str(viewer.user_id),
                "venue_id": venue_id,
                "source_refs": draft["source_refs"],
                "text": text,
                "audience_ids": sorted(str(x) for x in scene["participants"]),
                "scope": "synthetic_report_only",
                "delivery": "projection_ready",
                "application": "no_mechanical_effects",
            }
            c.execute(
                table.insert().values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(result, sort_keys=True),
                )
            )
            return {
                "id": identity,
                "scope": "synthetic_report_only",
                "delivery": "projection_ready",
            }

        return self.store._write(
            viewer,
            key,
            "director.synthetic_report",
            {"scene_id": scene_id, "draft_id": draft_id, "venue_id": venue_id},
            operation,
            authorize=authorize,
        )

    def projections(self, viewer: GuildViewer, scene_id: str) -> tuple[dict[str, Any], ...]:
        self.observations._scope()
        with self.store.transaction() as c:
            scene = self.observations._scene(c, scene_id, viewer)
            state = self.observations._state(c, scene_id)
            if state.policy.mode == "off" or not self.observations._consented(c, scene, state):
                return ()
            lock = self.observations.game.lock(c, scene["channel_id"])
            if lock and lock["state"] != "released":
                return ()
            # Optional output is suppressed during pause; required engine receipts are separate.
            if c.execute(
                sa.select(t.pauses).where(t.pauses.c.campaign_id == self.store.campaign_id)
            ).first():
                return ()
            table = t.director_context["shadow"]
            rows = c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene_id,
                    table.c.id.like("%:contribution"),
                )
            )
            people = sorted(str(x) for x in scene["participants"])
            from girlframe.engine.m3_actors import resolve
            from girlframe.engine.m3_cast import validate_role
            from girlframe.services.m2_state import load_state
            from girlframe.services.m3_actors import profiles
            from girlframe.services.m3_appearance_matrix import prove_context
            from girlframe.services.m3_scene_requisitions import guard

            canon = load_state(c, self.store.campaign_id)
            result = []
            references = {x.id: x for x in self.context._current(c, scene_id)}
            for body in rows:
                row = json.loads(body)
                if row["audience_ids"] != people or str(viewer.user_id) not in row["audience_ids"]:
                    continue
                try:
                    ref = ActorRef.model_validate_json(json.dumps(row["actor"]))
                    actual = resolve(canon, ref, profiles(c, self.store.campaign_id))
                    cast = next((x for x in canon.scene_casts if x.id == scene_id and x.open), None)
                    if cast is None:
                        continue
                    validate_role(cast, actual)
                    venue = prove_context(self.observations.game, c, canon, row["venue_id"])
                    guard(c, self.store, scene_id, ref)
                    if (
                        actual.controller != int(row["owner_id"])
                        or actual.cell != venue.cell
                        or actual.custody
                    ):
                        continue
                    if any(
                        x not in references or ref.token not in references[x].known_by
                        for x in row["source_refs"]
                    ):
                        continue
                except (ValueError, WorkflowError):
                    continue
                # A public scene projection must not reveal a hidden NPC's internal ID/name,
                # owner, venue metadata or private knowledge-assignment record IDs.
                result.append(
                    {
                        "id": row["id"],
                        "scene_id": scene_id,
                        "speaker": "NPC report",
                        "text": row["text"],
                        "scope": "synthetic_report_only",
                    }
                )
            return tuple(result)
