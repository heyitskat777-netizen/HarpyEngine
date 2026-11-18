"""Recipient-scoped delivery of reviewed Handler contributions and their follow-through."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.conversation import (
    ConversationReply,
    HandlerConcern,
    HandlerDecision,
    HandlerRequest,
)
from girlframe.ai.director import KnowledgeReference
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.director_context import DirectorContextService, next_contribution_ordinal
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.director_conversation import DirectorConversationService


class HandlerDeliveryService:
    def __init__(self, conversation: "DirectorConversationService"):
        self.conversation = conversation
        self.context, self.store = conversation.context, conversation.store
        self.observer = conversation.observations
        self.knowledge = DirectorKnowledgeService(self.context)

    def _audience(
        self, c: Connection, scene: str, roles: tuple[ActorRef, ...], *, allow_closed: bool = False
    ) -> dict[str, int]:
        available = self.knowledge._actors(
            c, self.observer._scene(c, scene, allow_closed=allow_closed)
        )
        if not set(roles) <= set(available):
            raise WorkflowError("HANDLER_DELIVERY_AUDIENCE: recover the original current roles.")
        state = load_state(c, self.store.campaign_id)
        bound = profiles(c, self.store.campaign_id)
        return {
            actor.token: resolve(state, actor, bound, require_current_profile=False).controller
            for actor in roles
        }

    def plan(
        self,
        c: Connection,
        scene: str,
        source: Observation,
        request: HandlerRequest,
        reply: ConversationReply,
        decision: HandlerDecision,
        recipients: tuple[ActorRef, ...],
    ) -> dict[str, Any]:
        actor = request.context.actor
        assert actor is not None
        one_listener = decision.cue == "personal" or (
            decision.reason == "reviewed_character_cue" and source.fictional_channel != "comms"
        )
        if (
            source.actor not in recipients
            or actor in recipients
            or len(set(recipients)) != len(recipients)
            or (one_listener and recipients != (source.actor,))
        ):
            raise WorkflowError(
                "HANDLER_DELIVERY_AUDIENCE: select the addressed Pilot and actual listeners."
            )
        if decision.concern_id:
            origin = self.conversation._saved(c, decision.concern_id)
            actual = [x.model_dump(mode="json") for x in recipients]
            if (
                not origin
                or origin["speaker"] not in actual
                or any(x not in origin["recipients"] for x in actual)
            ):
                raise WorkflowError(
                    "HANDLER_CONCERN_AUDIENCE: report back to the original Pilot and listeners."
                )
        current = self.context._current(c, scene)
        if any(
            not set(reply.source_refs)
            <= {x.id for x in self.context._actor_references(current, recipient)}
            for recipient in recipients
        ):
            raise WorkflowError(
                "HANDLER_DELIVERY_KNOWLEDGE: disclose the cited facts separately first."
            )
        text = "Reported claim: " + reply.text
        if reply.handler_action:
            text += "\nHandler action: " + reply.handler_action
        if len(text) > 1200:
            raise WorkflowError("HANDLER_DELIVERY_TEXT: shorten the reviewed scene contribution.")
        controllers = self._audience(c, scene, (actor, *recipients))
        return dict(
            handler=actor.model_dump(mode="json"),
            recipients=[x.model_dump(mode="json") for x in recipients],
            controllers=controllers,
            text=text,
            closes=decision.concern_id,
            concern=reply.handler_concern,
            **({"character_cue": True} if decision.reason == "reviewed_character_cue" else {}),
            appointment=HandlerService(self.store).current(c)[0],
            consent=self.observer._state(c, scene).consent_generation,
        )

    def _scope(
        self, c: Connection, viewer: GuildViewer, scene: str, *, allow_closed: bool = False
    ) -> dict[str, Any]:
        self.observer._scope()
        self.observer.game.unpaused(c)
        row = self.observer._scene(c, scene, viewer, allow_closed=allow_closed)
        policy = self.observer._state(c, scene)
        if policy.policy.mode != "shadow" or not self.observer._consented(c, row, policy):
            raise WorkflowError("OBSERVATION_DISABLED: retain current scene consent.")
        return row

    def _records(self, c: Connection, scene: str) -> list[dict[str, Any]]:
        table = t.director_context["shadow"]
        return [
            json.loads(raw)
            for raw in c.scalars(
                sa.select(table.c.body_json)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    table.c.id.like("handler-delivery:%"),
                )
                .order_by(sa.func.json_extract(table.c.body_json, "$.ordinal"))
            )
        ]

    def open_concerns(
        self,
        c: Connection,
        scene: str,
        handler: ActorRef,
        speaker: ActorRef,
        reference_ids: set[str],
    ) -> tuple[HandlerConcern, ...]:
        records = self._records(c, scene)
        closed = {row["closes"] for row in records if row["closes"]}
        return tuple(
            HandlerConcern(id=row["id"], text=row["concern"])
            for row in records
            if row["id"] not in closed
            and row["concern"]
            and row["reference"] in reference_ids
            and row["handler"] == handler.model_dump(mode="json")
            and speaker.model_dump(mode="json") in row["recipients"]
        )[-8:]

    def _approved(
        self, c: Connection, controller: GuildViewer, scene: str, draft_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._scope(c, controller, scene)
        draft = self.conversation._handler_draft(c, scene, draft_id)
        review = self.conversation._saved(c, draft_id + ":review")
        plan = review.get("delivery") if review else None
        if not review or review["decision"] != "approve" or not plan:
            raise WorkflowError("HANDLER_DELIVERY_REVIEW: choose a GM-approved delivery.")
        handler = ActorRef.model_validate(plan["handler"])
        role = self.context._handler_for_request(c, controller, scene)
        if (
            handler != role.actor
            or plan["controllers"][handler.token] != controller.user_id
            or plan["appointment"] != HandlerService(self.store).current(c)[0]
        ):
            raise WorkflowError("HANDLER_DELIVERY_OWNER: the approved Handler must deliver.")
        if plan["consent"] != self.observer._state(c, scene).consent_generation:
            raise WorkflowError("HANDLER_DELIVERY_CONSENT: renew the actual review.")
        if plan.get("character_cue") and not self.conversation._saved(
            c, "handler-delivery:" + draft_id
        ):
            source = self.conversation._need_source(c, scene, draft["source_id"])
            if self.conversation.peer_covered(c, scene, source, handler):
                raise WorkflowError(
                    "HANDLER_PEER_RESPONSE: another Pilot already attended to this cue."
                )
        return draft, plan

    def deliver(
        self, controller: GuildViewer, key: str, scene: str, draft_id: str
    ) -> dict[str, Any]:
        identity = "handler-delivery:" + draft_id

        def operation(c: Connection) -> dict[str, Any]:
            prior = self.conversation._saved(c, identity)
            if prior:
                return {"id": identity, "reference": prior["reference"], "effects_applied": False}
            draft, plan = self._approved(c, controller, scene, draft_id)
            source = self.conversation._need_source(c, scene, draft["source_id"])
            if (
                source.source_revision != draft["source_revision"]
                or source.actor.model_dump(mode="json") != draft["actor"]
            ):
                raise WorkflowError("HANDLER_DELIVERY_SOURCE: re-review the original turn.")
            handler = ActorRef.model_validate(plan["handler"])
            recipients = tuple(ActorRef.model_validate(x) for x in plan["recipients"])
            if self._audience(c, scene, (handler, *recipients)) != plan["controllers"]:
                raise WorkflowError("HANDLER_DELIVERY_AUDIENCE: the approved controllers changed.")
            current = self.context._current(c, scene)
            reply = ConversationReply.model_validate_json(json.dumps(draft["reply"]))
            if any(
                not set(reply.source_refs)
                <= {ref.id for ref in self.context._actor_references(current, actor)}
                for actor in (handler, *recipients)
            ):
                raise WorkflowError("HANDLER_DELIVERY_KNOWLEDGE: the scoped facts changed.")
            if plan["closes"] and plan["closes"] not in {
                x.id
                for x in self.open_concerns(
                    c,
                    scene,
                    handler,
                    source.actor,
                    {x.id for x in current if handler.token in x.known_by},
                )
            }:
                raise WorkflowError("HANDLER_CONCERN_CLOSED: this concern was already addressed.")
            if len(current) >= 100:
                raise WorkflowError(
                    "CONTEXT_LIMIT: retire a reference before delivering the reply."
                )
            ref = KnowledgeReference(
                id=str(uuid4()),
                source_id=identity,
                source_revision=1,
                order=len(self.context._references(c, scene)) + 1,
                known_by=tuple(sorted(plan["controllers"])),
                reported_by=handler,
                classification="reported_claim",
                text=plan["text"],
            )
            record = dict(
                id=identity,
                reference=ref.id,
                ordinal=next_contribution_ordinal(c, self.store.campaign_id, scene),
                after_sequence=self.observer._state(c, scene).sequence,
                delivered_at=float(self.store.clock()),
                record_type="handler_delivery",
                speaker=draft["actor"],
                dialogue=reply.text,
                action=reply.handler_action,
                **plan,
            )
            self.conversation._save_handler_record(c, scene, identity, record)
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
            return {"id": identity, "reference": ref.id, "effects_applied": False}

        def authorize(c: Connection) -> None:
            self._approved(c, controller, scene, draft_id)

        return self.store._write(
            controller,
            key,
            "director.handler_delivered",
            {"scene": scene, "draft": draft_id},
            operation,
            authorize=authorize,
        )

    def preview(self, controller: GuildViewer, scene: str, draft_id: str) -> dict[str, Any]:
        """Show the approved contribution to its actual Handler before delivery."""
        with self.store.engine.connect() as c:
            draft, plan = self._approved(c, controller, scene, draft_id)
            return {
                "id": draft_id,
                "recipients": plan["recipients"],
                "text": draft["reply"]["text"],
                "action": draft["reply"].get("handler_action"),
            }

    def pending(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        """For the original Handler, list scoped deliveries awaiting confirmation."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            if load_state(c, self.store.campaign_id).handler != viewer.user_id:
                return []
            table = t.director_context["shadow"]
            records = c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type")
                    == "handler_reply_review",
                    sa.func.json_type(table.c.body_json, "$.delivery") == "object",
                )
            )
            result = []
            for raw in records:
                draft_id = json.loads(raw)["draft_id"]
                if self.conversation._saved(c, "handler-delivery:" + draft_id):
                    continue
                try:
                    _, plan = self._approved(c, viewer, scene, draft_id)
                except WorkflowError:
                    continue
                result.append({"id": draft_id, "recipients": plan["recipients"]})
            return result

    def contributions(self, viewer: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._contributions(c, viewer, scene)

    def _contributions(
        self, c: Connection, viewer: GuildViewer, scene: str, *, allow_closed: bool = False
    ) -> list[dict[str, Any]]:
        self._scope(c, viewer, scene, allow_closed=allow_closed)
        result = []
        for row in self._records(c, scene):
            audience = tuple(
                ActorRef.model_validate(x) for x in (row["handler"], *row["recipients"])
            )
            if viewer.user_id not in row["controllers"].values():
                continue
            try:
                current = self._audience(c, scene, audience, allow_closed=allow_closed)
            except WorkflowError:
                continue
            if (
                current != row["controllers"]
                or row["consent"] != self.observer._state(c, scene).consent_generation
            ):
                continue
            result.append(
                dict(
                    id=row["id"],
                    ordinal=row["ordinal"],
                    after_sequence=row.get("after_sequence"),
                    delivered_at=row.get("delivered_at"),
                    text=row["dialogue"],
                    action=row["action"],
                    actor=row["handler"],
                    route="handler",
                    canon_effects=False,
                    publication="scoped_scene_delivery",
                )
            )
        return result


def validate_delivery_reference(
    context: DirectorContextService, c: Connection, scene: str, reference: KnowledgeReference
) -> None:
    table = t.director_context["shadow"]
    raw = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == context.store.campaign_id,
            table.c.scene_id == scene,
            table.c.id == reference.source_id,
        )
    )
    record = json.loads(raw) if raw else None
    if (
        not record
        or record.get("record_type") != "handler_delivery"
        or record["reference"] != reference.id
        or record["text"] != reference.text
        or record["handler"]
        != (reference.reported_by.model_dump(mode="json") if reference.reported_by else None)
        or reference.classification != "reported_claim"
        or reference.source_revision != 1
        or set(record["controllers"]) != set(reference.known_by)
        or record["consent"] != context.observations._state(c, scene).consent_generation
    ):
        raise WorkflowError("STALE_HANDLER_DELIVERY: reconcile the original scoped contribution.")
    state = load_state(c, context.store.campaign_id)
    bound = profiles(c, context.store.campaign_id)
    for ref in record["recipients"]:
        actor = ActorRef.model_validate(ref)
        try:
            owner = resolve(state, actor, bound, require_current_profile=False).controller
        except ValueError:
            raise WorkflowError("STALE_HANDLER_DELIVERY: recover the original listeners.") from None
        if owner != record["controllers"][actor.token]:
            raise WorkflowError("STALE_HANDLER_DELIVERY: the original listener changed controller.")
