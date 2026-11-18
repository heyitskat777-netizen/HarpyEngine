"""Reviewed actor reactions over existing Director contexts, claims and native routes."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director_reactions import ReactionProposal, ReactionProvider
from girlframe.ai.observation import ReviewBatch
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorReactionService:
    def __init__(self, context: DirectorContextService):
        self.context, self.store, self.observer = context, context.store, context.observations

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str) -> None:
        DirectorKnowledgeService(self.context)._scope(c, viewer, scene)

    def _save(self, c: Connection, scene: str, identity: str, kind: str, **body: Any) -> None:
        c.execute(
            t.director_context["shadow"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                scene_id=scene,
                id=identity,
                body_json=json.dumps(dict(id=identity, record_type=kind, **body), sort_keys=True),
            )
        )

    def _get(self, c: Connection, scene: str, identity: str, kind: str) -> dict[str, Any]:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        value = json.loads(raw) if raw else None
        if value is None or value.get("record_type") != kind:
            raise WorkflowError("REACTION_UNAVAILABLE: select actual reaction work.")
        return dict(value)

    def _packet(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        source_id: str,
        request: str,
        run_id: str | None,
        *,
        approved_run: bool = False,
    ) -> dict[str, Any]:
        from girlframe.services.director_dossiers import DirectorDossierService
        from girlframe.services.director_fronts import DirectorFrontService

        self.observer._scope()
        self.observer.game.unpaused(c)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(
            c, self.observer._scene(c, scene), state
        ):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent required.")
        knowledge = DirectorKnowledgeService(self.context)
        row = self.observer._scene(c, scene)
        if actor not in knowledge._actors(c, row):
            raise WorkflowError("ACTOR_UNAVAILABLE: require actual present current casting.")
        source = knowledge._source(c, scene, source_id)
        if run_id:
            runs = t.director["runs"]
            record = (
                c.execute(
                    sa.select(runs).where(
                        runs.c.campaign_id == self.store.campaign_id,
                        runs.c.scene_id == scene,
                        runs.c.run_id == run_id,
                        runs.c.status.in_(
                            ("running", "reviewed") if approved_run else ("running",)
                        ),
                    )
                )
                .mappings()
                .first()
            )
            if not record or (
                record["status"] == "running" and record["lease_until"] <= self.store.clock()
            ):
                raise WorkflowError("STALE_CLAIM: reuse an actual eligible Director batch.")
            batch = ReviewBatch.model_validate_json(record["body_json"])
            if source_id not in {
                x.source_id for x in batch.inputs
            } or batch.guard_digest != self.observer._guard(c, row, self.observer._state(c, scene)):
                raise WorkflowError("STALE_CLAIM: source or claimed context changed.")
        # A GM requests this projection but no private GM packet enters generation.
        dossiers = DirectorDossierService(self.context)
        actual_controller = dossiers._actor(c, scene, actor).controller
        own = dossiers._role_packet(c, scene, actor).model_dump(mode="json")
        fronts = DirectorFrontService(self.context)._actor_view(c, scene, actor)
        refs = self.context._actor_references(self.context._current(c, scene), actor)
        heard = knowledge.heard(c, scene, source_id, actor) if source.kind == "message" else ()
        payload = dict(
            actor=actor.model_dump(mode="json"),
            dossier=own,
            fronts=fronts,
            question="\n".join(heard) or "No newly heard speech.",
            references=[x.model_dump(mode="json") for x in refs],
            available_actions=["WAIT", "SCENE_OFFER", "REQUEST_ACTION"]
            + (["DIALOGUE", "REFUSE", "COMPROMISE", "DELAY"] if actor.kind == "npc" else []),
        )
        guard = _digest(
            dict(
                role=payload,
                source=source.model_dump(mode="json"),
                native=self.observer._guard(c, row, self.observer._state(c, scene)),
                run_id=run_id,
            )
        )
        return dict(
            request_id=request,
            scene_id=scene,
            source_id=source_id,
            run_id=run_id,
            actor=actor.model_dump(mode="json"),
            controller=str(actual_controller),
            role=payload,
            revision=guard,
        )

    def open(
        self,
        gm: GuildViewer,
        key: str,
        scene: str,
        actor: ActorRef,
        source_id: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            identity = "reaction-request:" + str(uuid4())
            packet = self._packet(c, scene, actor, source_id, identity, run_id)
            self._save(c, scene, identity, "reaction_request", packet=packet)
            return dict(id=identity)

        return self.store._write(
            gm,
            key,
            "director.reaction_open",
            dict(scene=scene, actor=actor.model_dump(mode="json"), source=source_id, run=run_id),
            operation,
            authorize=lambda c: self._scope(c, gm, scene),
        )

    def packet(self, gm: GuildViewer, scene: str, request: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
            return dict(self._get(c, scene, request, "reaction_request")["packet"])

    def _fresh(self, c: Connection, packet: dict[str, Any], *, approved_run: bool = False) -> None:
        current = self._packet(
            c,
            packet["scene_id"],
            ActorRef.model_validate_json(json.dumps(packet["actor"])),
            packet["source_id"],
            packet["request_id"],
            packet["run_id"],
            approved_run=approved_run,
        )
        if current != packet:
            raise WorkflowError("STALE_REACTION: refresh actual dossier, sources and context.")

    def propose(
        self, gm: GuildViewer, key: str, scene: str, request: str, proposal: ReactionProposal
    ) -> dict[str, Any]:
        proposal = ReactionProposal.model_validate_json(proposal.model_dump_json())

        return self.store._write(
            gm,
            key,
            "director.reaction_propose",
            dict(scene=scene, request=request, proposal=proposal.model_dump(mode="json")),
            lambda c: self._propose(c, gm, scene, request, proposal),
            authorize=lambda c: self._scope(c, gm, scene),
        )

    def _propose(
        self, c: Connection, gm: GuildViewer, scene: str, request: str, proposal: ReactionProposal
    ) -> dict[str, Any]:
        packet = self._get(c, scene, request, "reaction_request")["packet"]
        self._fresh(c, packet)
        refs = {x["id"] for x in packet["role"]["references"]}
        if (
            proposal.request_id != request
            or proposal.kind not in packet["role"]["available_actions"]
            or len(set(proposal.cited_references)) != len(proposal.cited_references)
            or not set(proposal.cited_references) <= refs
        ):
            raise WorkflowError("REACTION_SCOPE: retain actual actor and known sources.")
        if proposal.kind != "WAIT" and not proposal.text.strip():
            raise WorkflowError("REACTION_TEXT: non-silent proposals need bounded text.")
        if proposal.kind == "REQUEST_ACTION":
            if proposal.route == "none" or not proposal.source_work_id:
                raise WorkflowError("NATIVE_ROUTE_REQUIRED: identify actual pending native work.")
        elif proposal.route != "none" or proposal.source_work_id is not None:
            raise WorkflowError("REACTION_AUTHORITY: dialogue cannot carry native execution.")
        self._route(c, gm, scene, proposal)
        identity = "reaction:" + str(uuid4())
        self._save(
            c,
            scene,
            identity,
            "reaction_proposal",
            request=request,
            proposal=proposal.model_dump(mode="json"),
        )
        return dict(id=identity, effects_applied=False)

    def generate(
        self,
        gm: GuildViewer,
        key: str,
        scene: str,
        request: str,
        provider: ReactionProvider,
    ) -> dict[str, Any]:
        """Provider work stays outside the transaction; freshness is rechecked on save."""
        payload = dict(scene=scene, request=request)
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
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
                expected = _digest(
                    dict(actor=gm.user_id, kind="director.reaction_generate", payload=payload)
                )
                if old["request_hash"] != expected:
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: generation request changed.")
                return dict(json.loads(old["outcome_json"]))
            packet = self._get(c, scene, request, "reaction_request")["packet"]
            self._fresh(c, packet)
        try:
            proposal = ReactionProposal.model_validate_json(
                provider.propose(packet).model_dump_json()
            )
        except Exception:
            raise WorkflowError("REACTION_PROVIDER_UNAVAILABLE: no valid proposal saved.") from None

        def operation(c: Connection) -> dict[str, Any]:
            return self._propose(c, gm, scene, request, proposal)

        return self.store._write(
            gm,
            key,
            "director.reaction_generate",
            payload,
            operation,
            authorize=lambda c: self._scope(c, gm, scene),
        )

    def private(self, gm: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
            record = self._get(c, scene, identity, "reaction_proposal")
            if self.observer._state(c, scene).activity_epoch is not None:
                packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
                if self._stale_review(c, scene, identity, packet):
                    return {"id": identity, "status": "stale_reopen_source"}
            return record

    def _owned(
        self,
        c: Connection,
        viewer: GuildViewer,
        scene: str,
        identity: str,
        *,
        fresh: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from girlframe.engine.m3_actors import resolve
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_actors import profiles

        self.store.guild_member(viewer)
        self.observer._scope()
        row = self.observer._scene(c, scene, viewer)
        state = self.observer._state(c, scene)
        if state.activity_epoch is not None and (
            state.policy.mode != "shadow" or not self.observer._consented(c, row, state)
        ):
            raise WorkflowError("OBSERVATION_DISABLED: current scene consent is required.")
        record = self._get(c, scene, identity, "reaction_proposal")
        packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
        actual = resolve(
            load_state(c, self.store.campaign_id),
            ActorRef.model_validate(packet["actor"]),
            profiles(c, self.store.campaign_id),
            require_current_profile=False,
        )
        if actual.controller != viewer.user_id or packet.get("controller") != str(viewer.user_id):
            raise WorkflowError("REACTION_NOT_OWNED: actual controller must decide.")
        if fresh:
            self._fresh(c, packet)
        return record, packet

    def owner_review(self, controller: GuildViewer, scene: str, identity: str) -> dict[str, Any]:
        """Inspect the actor's proposed reply; private GM reasoning stays excluded."""
        with self.store.engine.connect() as c:
            record, packet = self._owned(c, controller, scene, identity, fresh=False)
            if self.observer._state(c, scene).activity_epoch is not None and self._stale_review(
                c, scene, identity, packet
            ):
                return {"id": identity, "status": "stale_reopen_source", "effects_applied": False}
            return dict(
                id=identity,
                actor=packet["actor"],
                proposal={k: v for k, v in record["proposal"].items() if k != "rationale"},
                publication="private_review_only",
                effects_applied=False,
            )

    def _stale_review(
        self, c: Connection, scene: str, identity: str, packet: dict[str, Any]
    ) -> bool:
        approval = self._review_record(c, scene, identity)
        try:
            self._fresh(
                c, packet, approved_run=bool(approval and approval["decision"] == "approve")
            )
        except WorkflowError:
            return True
        return False

    def _review_record(self, c: Connection, scene: str, identity: str) -> dict[str, Any] | None:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity + ":review",
            )
        )
        return dict(json.loads(raw)) if raw else None

    def _route(
        self, c: Connection, gm: GuildViewer | None, scene: str, p: ReactionProposal
    ) -> None:
        if p.kind != "REQUEST_ACTION":
            return
        if p.route == "gm_outcome":
            from girlframe.services.gm_outcomes import GMOutcomeService

            service = GMOutcomeService(self.context)
            packet, _ = service._load(c, scene, p.source_work_id or "")
            service._current(c, packet)
            if c.scalar(
                sa.select(t.commands.c.interaction_key)
                .where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key.startswith(
                        "gm-outcome:" + (p.source_work_id or "") + ":"
                    ),
                )
                .limit(1)
            ):
                raise WorkflowError("NATIVE_ROUTE_UNAVAILABLE: outcome already confirmed.")
        elif p.route == "worldbuilding":
            from girlframe.services.director_worldbuilding import DirectorWorldbuildingService

            service_world = DirectorWorldbuildingService(self.context)
            packet_world, _ = service_world._load(c, scene, p.source_work_id or "")
            review = service_world._saved(c, scene, (p.source_work_id or "") + ":review")
            if (review and review["decision"] == "reject") or service_world._native_committed(
                c, p.source_work_id or ""
            ):
                raise WorkflowError("NATIVE_ROUTE_UNAVAILABLE: world proposal closed.")
            if gm is not None:
                service_world._current(c, gm, packet_world)
            else:
                # Read-only server validation never impersonates a GM principal.
                state = self.observer._state(c, scene)
                scene_row = self.observer._scene(c, scene)
                revision = _digest(
                    dict(
                        guard=self.observer._guard(c, scene_row, state),
                        references=[
                            x.model_dump(mode="json") for x in self.context._current(c, scene)
                        ],
                    )
                )
                source = DirectorKnowledgeService(self.context)._source(
                    c, scene, packet_world.source.id
                )
                if (
                    packet_world.context.revision != revision
                    or source != packet_world.source
                    or packet_world.frontier != state.sequence
                ):
                    raise WorkflowError("NATIVE_ROUTE_UNAVAILABLE: world context changed.")
        elif p.route == "controller_response":
            from girlframe.services.gm_outcomes import GMOutcomeService

            responses = GMOutcomeService(self.context).responses
            record = responses._load(c, scene, p.source_work_id or "")
            responses._fresh(c, scene, record)
            if responses._answer(c, scene, p.source_work_id or ""):
                raise WorkflowError("NATIVE_ROUTE_UNAVAILABLE: controller already answered.")
        else:
            choices = t.m2["m2_choices"]
            row = (
                c.execute(
                    sa.select(choices).where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.id == p.source_work_id,
                        choices.c.state == "pending",
                    )
                )
                .mappings()
                .first()
            )
            if row is None or self.observer.game.action(c, row["action_id"])["scene_id"] != scene:
                raise WorkflowError("NATIVE_ROUTE_UNAVAILABLE: use actual pending scene work.")

    def pending(self, viewer: GuildViewer, scene: str, *, gm: bool = False) -> list[dict[str, Any]]:
        """Metadata only; reading an Inbox never grants another controller's prose."""
        with self.store.engine.connect() as c:
            if gm:
                self._scope(c, viewer, scene)
            else:
                self.store.guild_member(viewer)
                self.observer._scope()
                row = self.observer._scene(c, scene, viewer)
                state = self.observer._state(c, scene)
                self.observer.game.unpaused(c)
                if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
                    raise WorkflowError("OBSERVATION_DISABLED: current consent required.")
            table = t.director_context["shadow"]
            records = [
                json.loads(raw)
                for raw in c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id, table.c.scene_id == scene
                    )
                )
            ]
            reviewed = {
                r["id"].removesuffix(":review")
                for r in records
                if r.get("record_type") == "reaction_review"
            }
            result = []
            for record in records:
                if record.get("record_type") != "reaction_proposal" or record["id"] in reviewed:
                    continue
                if gm:
                    packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
                else:
                    try:
                        _, packet = self._owned(c, viewer, scene, record["id"], fresh=False)
                    except (WorkflowError, ValueError):
                        continue
                status = "awaiting_controller_review"
                try:
                    self._fresh(c, packet)
                except (WorkflowError, ValueError):
                    status = "stale_reopen_source"
                result.append(
                    dict(
                        id=record["id"],
                        actor=packet["actor"],
                        kind=record["proposal"]["kind"],
                        status=status,
                    )
                )
            return result

    def ensemble(self, gm: GuildViewer, scene: str) -> dict[str, Any]:
        from girlframe.services.director_dossiers import DirectorDossierService
        from girlframe.services.director_fronts import DirectorFrontService

        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
            actors = DirectorKnowledgeService(self.context)._actors(
                c, self.observer._scene(c, scene)
            )
            table = t.director_context["shadow"]
            reviews = list(
                c.scalars(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        sa.func.json_extract(table.c.body_json, "$.record_type")
                        == "reaction_review",
                    )
                )
            )
            history = [json.loads(raw) for raw in reviews]
            opportunities = []
            for actor in actors:
                relevant = [r for r in history if r.get("actor") == actor.model_dump(mode="json")]
                own = DirectorDossierService(self.context)._role_packet(c, scene, actor)
                opportunities.append(
                    dict(
                        actor=actor.model_dump(mode="json"),
                        dossier=own.model_dump(mode="json"),
                        reviewed_count=len(relevant),
                        accepted_count=sum(r["decision"] == "approve" for r in relevant),
                        last_source=relevant[-1]["source_id"] if relevant else None,
                    )
                )
        return dict(
            actors=opportunities,
            fronts=DirectorFrontService(self.context).view(gm, scene),
            reviewed_reactions=len(reviews),
            instruction=(
                "Review neglected opportunities; no required appearances or automatic advancement."
            ),
        )

    def npc_roster(self, gm: GuildViewer, scene: str) -> list[dict[str, Any]]:
        """Canonical living NPCs for the GM, with current cast and native Support origins."""
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
            native = load_state(c, self.store.campaign_id)
            if native.world is None:
                return []
            present = {
                actor.entity
                for actor in DirectorKnowledgeService(self.context)._actors(
                    c, self.observer._scene(c, scene)
                )
                if actor.kind == "npc"
            }
            support = {
                play.effect.npc.id: play.id
                for play in native.handler_plays
                if play.state == "complete"
                and play.selected == "support"
                and play.effect
                and play.effect.npc
            }
            return [
                dict(
                    id=npc.id,
                    name=npc.name,
                    controller=str(npc.controller),
                    present=npc.id in present,
                    support_play=support.get(npc.id),
                )
                for npc in native.world.npcs
                if npc.alive
            ]

    def review(
        self,
        controller: GuildViewer,
        key: str,
        scene: str,
        identity: str,
        decision: Literal["approve", "reject"],
        reason: str,
        *,
        recipients: tuple[ActorRef, ...] = (),
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject") or not reason.strip() or len(reason) > 1200:
            raise WorkflowError("REACTION_REVIEW_INVALID: provide bounded decision/reason.")

        def authorize(c: Connection) -> None:
            self._owned(c, controller, scene, identity, fresh=False)

        def operation(c: Connection) -> dict[str, Any]:
            record = self._get(c, scene, identity, "reaction_proposal")
            packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
            plan = None
            if recipients and decision != "approve":
                raise WorkflowError("NPC_DELIVERY_REVIEW: only approval names listeners.")
            if decision == "approve":
                self._fresh(c, packet)
                if recipients:
                    from girlframe.services.director_npc_delivery import NpcDeliveryService

                    plan = NpcDeliveryService(self.context).plan(
                        c, scene, packet, record["proposal"], recipients
                    )
                self._route(
                    c,
                    None,
                    scene,
                    ReactionProposal.model_validate_json(json.dumps(record["proposal"])),
                )
            table = t.director_context["shadow"]
            if c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    table.c.id == identity + ":review",
                )
            ):
                raise WorkflowError("REACTION_FINAL: review already recorded.")
            slot = "reaction-episode:" + _digest(
                dict(actor=packet["actor"], source=packet["source_id"], run=packet["run_id"])
            )
            if decision == "approve":
                if c.scalar(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        table.c.id == slot,
                    )
                ):
                    raise WorkflowError(
                        "REACTION_ADDRESSED: this actor already addressed this episode."
                    )
                if plan is None:
                    self._save(c, scene, slot, "reaction_episode", reaction_id=identity)
                if packet["run_id"]:
                    runs = t.director["runs"]
                    token = c.scalar(
                        sa.select(runs.c.lease_token).where(
                            runs.c.campaign_id == self.store.campaign_id,
                            runs.c.scene_id == scene,
                            runs.c.run_id == packet["run_id"],
                        )
                    )
                    if not isinstance(token, str):
                        raise WorkflowError("STALE_CLAIM: recover actual worker token.")
                    self.observer.complete_in_transaction(c, packet["run_id"], token, success=True)
            self._save(
                c,
                scene,
                identity + ":review",
                "reaction_review",
                decision=decision,
                reason=reason,
                controller=controller.user_id,
                actor=packet["actor"],
                source_id=packet["source_id"],
                reaction_kind=record["proposal"]["kind"],
                **({"delivery": plan} if plan else {}),
            )
            p = record["proposal"]
            return dict(
                id=identity,
                status=decision,
                kind=p["kind"],
                text=p["text"]
                if (
                    decision == "approve"
                    and p["kind"] != "WAIT"
                    and self.observer._state(c, scene).activity_epoch is None
                )
                else "",
                route=p["route"],
                source_work_id=p["source_work_id"],
                effects_applied=False,
                publication="private_review_only",
                next_step="silent"
                if decision == "reject" or p["kind"] == "WAIT"
                else "native_service_or_scene_invitation"
                if p["kind"] in ("REQUEST_ACTION", "SCENE_OFFER")
                else "ready_for_simulated_delivery"
                if plan
                else "reviewed_private_reply",
            )

        return self.store._write(
            controller,
            key,
            "director.reaction_review",
            dict(
                scene=scene,
                id=identity,
                decision=decision,
                reason=reason,
                **(
                    {"recipients": [x.model_dump(mode="json") for x in recipients]}
                    if recipients
                    else {}
                ),
            ),
            operation,
            authorize=authorize,
            auto_audit=False,
        )
