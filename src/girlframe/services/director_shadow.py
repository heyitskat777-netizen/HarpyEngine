"""Durable synthetic shadow evaluation; external work outside writer transactions."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import DirectorDecision, DirectorProvider, SyntheticDirector
from girlframe.ai.observation import ReviewBatch
from girlframe.database import tables as t
from girlframe.services.director_context import DirectorContextService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorShadowService:
    def __init__(self, context: DirectorContextService, provider: DirectorProvider | None = None):
        self.context = context
        self.observations = context.observations
        self.store = context.store
        self.provider = provider or SyntheticDirector()

    def get(self, viewer: GuildViewer, scene_id: str, run_id: str) -> dict[str, object]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, scene_id)
            body = c.scalar(
                sa.select(t.director_context["shadow"].c.body_json).where(
                    t.director_context["shadow"].c.campaign_id == self.store.campaign_id,
                    t.director_context["shadow"].c.scene_id == scene_id,
                    t.director_context["shadow"].c.id == run_id,
                )
            )
            if body is None:
                raise WorkflowError("SHADOW_UNAVAILABLE: no accessible outcome.")
            return dict(json.loads(body))

    def _authorize(self, c: Connection, viewer: GuildViewer, scene_id: str) -> None:
        self.observations._scope()
        self.store.administrator(viewer)
        scene = self.observations._scene(c, scene_id, viewer)
        state = self.observations._state(c, scene_id)
        if not self.observations._consented(c, scene, state):
            raise WorkflowError("OBSERVATION_DISABLED: current consent is required.")

    def evaluate(self, viewer: GuildViewer, scene_id: str, run_id: str) -> dict[str, object]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, scene_id)
            saved = c.scalar(
                sa.select(t.director_context["shadow"].c.body_json).where(
                    t.director_context["shadow"].c.campaign_id == self.store.campaign_id,
                    t.director_context["shadow"].c.scene_id == scene_id,
                    t.director_context["shadow"].c.id == run_id,
                )
            )
            if saved:
                return dict(json.loads(saved))
        context = self.context.build(viewer, scene_id)
        with self.store.engine.connect() as c:
            saved = c.scalar(
                sa.select(t.director_context["shadow"].c.body_json).where(
                    t.director_context["shadow"].c.campaign_id == self.store.campaign_id,
                    t.director_context["shadow"].c.scene_id == scene_id,
                    t.director_context["shadow"].c.id == run_id,
                )
            )
            if saved:
                return dict(json.loads(saved))
            run = (
                c.execute(
                    sa.select(t.director["runs"]).where(
                        t.director["runs"].c.campaign_id == self.store.campaign_id,
                        t.director["runs"].c.scene_id == scene_id,
                        t.director["runs"].c.run_id == run_id,
                        t.director["runs"].c.status == "running",
                    )
                )
                .mappings()
                .first()
            )
            if not run:
                raise WorkflowError("STALE_CLAIM: claim an eligible review first.")
            token = run["lease_token"]
            batch = ReviewBatch.model_validate_json(run["body_json"])
            self.observations.game.unpaused(c)
            scene = self.observations._scene(c, scene_id, viewer)
            state = self.observations._state(c, scene_id)
            if run[
                "lease_until"
            ] <= self.store.clock() or batch.guard_digest != self.observations._guard(
                c, scene, state
            ):
                raise WorkflowError("STALE_CLAIM: refresh before evaluating.")
            if not {x.source_id for x in batch.inputs} <= {x.source_id for x in context.references}:
                raise WorkflowError(
                    "CONTEXT_INCOMPLETE: record each frozen source before evaluation."
                )
        # Deterministic local provider only is shipped. No lock is held here.
        decision = None
        failure = None
        allowed = {x.id for x in context.references}
        attempts = 0
        for _ in range(2):  # one bounded semantic repair/retry
            attempts += 1
            try:
                candidate = self.provider.decide(context)
                candidate = DirectorDecision.model_validate_json(candidate.model_dump_json())
                if not set(candidate.source_refs) <= allowed or len(
                    set(candidate.source_refs)
                ) != len(candidate.source_refs):
                    raise ValueError("Unknown source")
                if candidate.kind not in ("WAIT", "NEEDS_REVIEW") and not candidate.source_refs:
                    raise ValueError("A contribution requires grounding")
                # Actor/rule/action consumers are deliberately unavailable.
                if candidate.actor_id or candidate.rule_id or candidate.requires_player_choice:
                    raise ValueError("Unsupported actor/rule authority")
                decision = candidate
                break
            except (ValueError, TypeError, AttributeError):
                failure = "INVALID_DECISION"
            except Exception:
                failure = "PROVIDER_UNAVAILABLE"
                break
        result: dict[str, object] = {
            "schema_version": 1,
            "provider": "synthetic-local-v1",
            "context_revision": context.revision,
            "attempts": attempts,
            "external_tokens": 0,
            "external_cost": 0,
            "run_id": run_id,
            "scene_id": scene_id,
            "decision": decision.model_dump(mode="json") if decision else None,
            "failure": None if decision else failure,
            "application": "blocked",
            "publication": "blocked",
            "status": ("wait" if decision.kind == "WAIT" else "needs_review")
            if decision
            else "failed",
        }
        with self.store.transaction() as c:
            # Reentrant read connections are safe: this short transaction owns the writer lock.
            current = self.context._build(c, viewer, scene_id)
            if current.revision != context.revision:
                raise WorkflowError(
                    "STALE_CONTEXT: preserve unread input and evaluate a fresh claim."
                )
            existing = c.scalar(
                sa.select(t.director_context["shadow"].c.body_json).where(
                    t.director_context["shadow"].c.campaign_id == self.store.campaign_id,
                    t.director_context["shadow"].c.id == run_id,
                )
            )
            if existing:
                return dict(json.loads(existing))
            # Complete on this same transaction, so outcome and frontier are atomic.
            self.observations.complete_in_transaction(
                c, run_id, token, success=decision is not None
            )
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=run_id,
                    body_json=json.dumps(result, sort_keys=True),
                )
            )
            return result

    def review(
        self, viewer: GuildViewer, key: str, scene_id: str, run_id: str, *, decision: str
    ) -> dict[str, object]:
        """GM review of a shadow proposal, never mechanical or publication authority."""
        if decision not in ("approve", "reject"):
            raise WorkflowError("INVALID_REVIEW: choose approve or reject.")

        def authorize(c: Connection) -> None:
            self.context._build(c, viewer, scene_id)

        def operation(c: Connection) -> dict[str, Any]:
            table = t.director_context["shadow"]
            body = c.scalar(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene_id,
                    table.c.id == run_id,
                )
            )
            if body is None or json.loads(body)["status"] != "needs_review":
                raise WorkflowError("REVIEW_UNAVAILABLE: use a saved reviewable proposal.")
            identity = run_id + ":review"
            if c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == identity
                )
            ):
                raise WorkflowError("REVIEW_FINAL: the recorded review is immutable.")
            result = {
                "run_id": run_id,
                "decision": decision,
                "application": "blocked",
                "publication": "blocked",
            }
            c.execute(
                table.insert().values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(result),
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "director.shadow_review",
            {"scene_id": scene_id, "run_id": run_id, "decision": decision},
            operation,
            authorize=authorize,
        )
