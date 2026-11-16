"""Private GM judgment over native Play evidence, without substituting owner choices."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.adjudication import (
    AdjudicationProposal,
    AdjudicationProvider,
    AdjudicationRequest,
    SyntheticAdjudicator,
)
from girlframe.ai.conversation import GMRequest
from girlframe.database import tables as t
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorAdjudicationService:
    def __init__(
        self,
        conversation: DirectorConversationService,
        provider: AdjudicationProvider | None = None,
    ):
        self.conversation = conversation
        self.observations = conversation.observations
        self.store = conversation.store
        self.provider = provider if provider is not None else SyntheticAdjudicator()

    def _request(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene_id: str,
        source_id: str,
        source_revision: int,
        action_id: str,
    ) -> tuple[AdjudicationRequest, str]:
        source = self.conversation._authorize_source(c, viewer, scene_id, source_id)
        if source.source_revision != source_revision:
            raise WorkflowError("STALE_SOURCE: use the actual Play-call revision.")
        gm, _ = self.conversation._requests(c, viewer, scene_id, source_id, "gm")
        assert isinstance(gm, GMRequest)
        scene = self.observations._scene(c, scene_id, viewer)
        game = self.observations.game
        action = game.action(c, action_id)
        data = action["data"]
        if (
            action["scene_id"] != scene_id
            or str(action["actor_id"]) != str(viewer.user_id)
            or action["parent_id"] is not None
            or source.actor.kind != "pilot"
            or set(data["participants"]) != set(scene["participants"])
            or any(
                data.get(key)
                for key in (
                    "m3",
                    "actor_basic",
                    "gorgon_play",
                    "void_keep",
                    "handler_play_m3",
                    "kicked_puppy",
                    "nightmare_core",
                    "dampener",
                    "princess_child",
                    "ankou_feedback_child",
                    "bonded_child",
                    "red_queen_child",
                    "changeling_child",
                    "private_audience",
                )
            )
        ):
            raise WorkflowError(
                "UNSUPPORTED_ADJUDICATION_SOURCE: require your original native Play."
            )
        canon = load_state(c, self.store.campaign_id)
        game.action_characters(c, action, canon)
        if source.actor.incarnation != game.character_binding(
            c, canon, viewer.user_id, require_current_profile=False
        ):
            raise WorkflowError("STALE_ACTOR: retain the original Pilot incarnation.")
        if data["prepared"]["context"] != source.text:
            raise WorkflowError("UNBOUND_CONTEXT: native context must retain the actual Play call.")
        actions = t.m2["m2_actions"]
        if c.scalar(
            sa.select(actions.c.id)
            .where(
                actions.c.campaign_id == self.store.campaign_id, actions.c.parent_id == action_id
            )
            .limit(1)
        ):
            raise WorkflowError("UNSUPPORTED_ADJUDICATION_SOURCE: child workflows need an adapter.")
        receipts = t.m2["m2_receipts"]
        receipt = (
            c.execute(
                sa.select(receipts).where(
                    receipts.c.campaign_id == self.store.campaign_id,
                    receipts.c.action_id == action_id,
                )
            )
            .mappings()
            .first()
        )
        if not receipt or json.loads(receipt["body_json"]) != data.get("receipt"):
            raise WorkflowError("UNPROVEN_PLAY: original committed dice are required.")
        pending = game.pending(c, action_id)
        play = data["play"]
        result = data["result"]
        if play == "keep_your_head":
            if action["state"] == "complete":
                raise WorkflowError("RULING_COMMITTED: do not replace an already committed ruling.")
            if (
                len(pending) != 1
                or pending[0]["kind"] != "handler_keep"
                or str(pending[0]["actor_id"]) != str(canon.handler)
                or "positive" not in result
                or "negative" not in result
            ):
                raise WorkflowError("CHOICES_PENDING: preserve the actual Pilot's printed choices.")
            event = c.scalar(
                sa.select(t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == data.get("response_event"),
                    t.events.c.kind == "m2.choice_resolved",
                )
            )
            if not event or json.loads(event).get("action_id") != action_id:
                raise WorkflowError("UNPROVEN_PLAY: original committed actor choice is required.")
            # Resolve/check the actual appointed role without passing the GM's context
            # to the Handler dialogue provider or forging its viewer principal.
            self.conversation.context._handler_for_request(c, viewer, scene_id)
        actual = {
            key: result[key] for key in ("total", "tier", "positive", "negative") if key in result
        }
        request = AdjudicationRequest(
            play_id=play,
            action_id=action_id,
            action_revision=action["revision"],
            source_id=source_id,
            source_revision=source_revision,
            receipt_id=receipt["id"],
            pending_choice_id=pending[0]["id"] if pending else "completed:" + action_id,
            narration=data["prepared"]["context"],
            actual_result=actual,
            gm_context=gm,
        )
        return request, _digest(request.model_dump(mode="json"))

    def adjudicate(
        self,
        viewer: GuildViewer,
        key: str,
        scene_id: str,
        source_id: str,
        source_revision: int,
        action_id: str,
    ) -> dict[str, Any]:
        if type(source_revision) is not int or source_revision < 1:
            raise WorkflowError("STALE_SOURCE: supply a positive original source revision.")
        semantic = {
            "scene_id": scene_id,
            "source_id": source_id,
            "source_revision": source_revision,
            "action_id": action_id,
        }
        with self.store.transaction() as c:
            self.conversation._authorize_source(c, viewer, scene_id, source_id)
            old = (
                c.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == self.store.campaign_id,
                        t.commands.c.interaction_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["request_hash"] != _digest(
                    {"actor": viewer.user_id, "kind": "director.adjudication", "payload": semantic}
                ):
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: this adjudication request changed.")
                return self.get(viewer, scene_id, json.loads(old["outcome_json"])["id"])
            request, fingerprint = self._request(
                c, viewer, scene_id, source_id, source_revision, action_id
            )
        try:
            candidate = self.provider.adjudicate(request)
            proposal = AdjudicationProposal.model_validate_json(candidate.model_dump_json())
            if proposal != SyntheticAdjudicator().adjudicate(request):
                raise ValueError("Unpermitted synthetic adjudication")
        except Exception:
            raise WorkflowError(
                "ADJUDICATION_UNAVAILABLE: no valid grounded ruling was saved."
            ) from None

        def authorize(c: Connection) -> None:
            self.conversation._authorize_source(c, viewer, scene_id, source_id)

        def operation(c: Connection) -> dict[str, str]:
            _, current = self._request(c, viewer, scene_id, source_id, source_revision, action_id)
            if current != fingerprint:
                raise WorkflowError("STALE_ADJUDICATION: source, choices or context changed.")
            identity = "adjudication:" + str(uuid4())
            record = {
                "id": identity,
                "record_type": "gm_adjudication",
                "owner_id": str(viewer.user_id),
                **semantic,
                "receipt_id": request.receipt_id,
                "pending_choice_id": request.pending_choice_id,
                "action_revision": request.action_revision,
                "context_revision": fingerprint,
                "proposal": proposal.model_dump(mode="json"),
                "external_tokens": 0,
                "external_cost": 0,
                "publication": "private_proposal_only",
            }
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene_id,
                    id=identity,
                    body_json=json.dumps(record, sort_keys=True),
                )
            )
            return {"id": identity}

        result = self.store._write(
            viewer, key, "director.adjudication", semantic, operation, authorize=authorize
        )
        return self.get(viewer, scene_id, result["id"])

    def get(self, viewer: GuildViewer, scene_id: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.observations._scope()
            self.observations._scene(c, scene_id, viewer)
            saved = self.conversation._saved(c, identity)
            if (
                not saved
                or saved.get("record_type") != "gm_adjudication"
                or saved.get("owner_id") != str(viewer.user_id)
                or saved.get("scene_id") != scene_id
            ):
                raise WorkflowError("ADJUDICATION_UNAVAILABLE: no accessible GM adjudication.")
            self.conversation._authorize_source(c, viewer, scene_id, saved["source_id"])
            return saved
