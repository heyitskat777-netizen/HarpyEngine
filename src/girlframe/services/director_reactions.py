"""Reviewed actor reactions over existing Director contexts, claims and native routes."""

import json
from contextlib import nullcontext
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director_reactions import ReactionProposal, ReactionProvider
from girlframe.ai.observation import ReviewBatch
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.activity_dialogue import npc_owned
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_initiative import DirectorInitiative
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

_initiative_generation = Lock()


class DirectorReactionService:
    def __init__(self, context: DirectorContextService):
        self.context, self.store, self.observer = context, context.store, context.observations
        self.initiative = DirectorInitiative(context)

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
        activity_pilot: bool = False,
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
        if activity_pilot:
            self.observer.game.scene_unpaused(c, scene)
            if npc_owned(c, self.store.campaign_id, scene, (source_id,)):
                raise WorkflowError("NPC_HAS_FLOOR: this turn is addressed to an NPC.")
            if run_id is None or actor not in dossiers.activity_pilots(c, scene):
                raise WorkflowError(
                    "AI_PILOT_UNAVAILABLE: recover the approved AI Pilot and batch."
                )
        own = dossiers._role_packet(c, scene, actor, activity_pilot=activity_pilot).model_dump(
            mode="json"
        )
        fronts = DirectorFrontService(self.context)._actor_view(c, scene, actor)
        refs = self.context._actor_references(self.context._current(c, scene), actor)
        heard = knowledge.heard(c, scene, source_id, actor) if source.kind == "message" else ()
        if activity_pilot and (not heard or source.actor == actor):
            raise WorkflowError("AI_PILOT_HEARING: use a new source this Girl actually heard.")
        payload = dict(
            actor=actor.model_dump(mode="json"),
            dossier=own,
            fronts=fronts,
            question="\n".join(heard) or "No newly heard speech.",
            references=[x.model_dump(mode="json") for x in refs],
            available_actions=(
                ["WAIT", "SCENE_OFFER", "DIALOGUE"]
                if activity_pilot
                else ["WAIT", "SCENE_OFFER", "REQUEST_ACTION"]
                + (["DIALOGUE", "REFUSE", "COMPROMISE", "DELAY"] if actor.kind == "npc" else [])
            ),
        )
        if activity_pilot and actor.kind == "pilot":
            from girlframe.services.director_play_options import initiative_play_options

            payload["native_plays"] = list(initiative_play_options(self.context, c, scene, actor))
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
            **({"activity_pilot": True} if activity_pilot else {}),
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

    def initiative_options(self, gm: GuildViewer, scene: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.initiative.scope(c, gm, scene)
            return [item["option"] for item in self.initiative.candidates(c, scene)]

    def _initiative_proposal(self, c: Connection, scene: str, request: str) -> str | None:
        table = t.director_context["shadow"]
        return c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                sa.func.json_extract(table.c.body_json, "$.record_type") == "reaction_proposal",
                sa.func.json_extract(table.c.body_json, "$.request") == request,
            )
        )

    def open_initiative(self, gm: GuildViewer, key: str, scene: str, option: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            packet = self.initiative.packet(c, scene, option)
            identity = packet["request_id"]
            table = t.director_context["shadow"]
            if (
                c.scalar(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        table.c.id == identity,
                    )
                )
                is None
            ):
                self._save(c, scene, identity, "reaction_request", packet=packet)
            return {"id": identity, "proposal": self._initiative_proposal(c, scene, identity)}

        return self.store._write(
            gm,
            key,
            "director.initiative_open",
            {"scene": scene, "option": option},
            operation,
            authorize=lambda c: self.initiative.scope(c, gm, scene),
            auto_audit=False,
        )

    def _fresh(self, c: Connection, packet: dict[str, Any], *, approved_run: bool = False) -> None:
        if option := packet.get("initiative"):
            if self.initiative.packet(c, packet["scene_id"], option) != packet:
                raise WorkflowError("STALE_REACTION: refresh actual agenda, opening and context.")
            return
        current = self._packet(
            c,
            packet["scene_id"],
            ActorRef.model_validate_json(json.dumps(packet["actor"])),
            packet["source_id"],
            packet["request_id"],
            packet["run_id"],
            approved_run=approved_run or packet.get("activity_pilot", False),
            activity_pilot=packet.get("activity_pilot", False),
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
        self,
        c: Connection,
        gm: GuildViewer,
        scene: str,
        request: str,
        proposal: ReactionProposal,
        *,
        front_move: str | None = None,
    ) -> dict[str, Any]:
        packet = self._get(c, scene, request, "reaction_request")["packet"]
        self._fresh(c, packet)
        if packet.get("initiative"):
            self.initiative.scope(c, gm, scene)
        refs = {x["id"] for x in packet["role"]["references"]}
        if (
            proposal.request_id != request
            or proposal.kind not in packet["role"]["available_actions"]
            or len(set(proposal.cited_references)) != len(proposal.cited_references)
            or not set(proposal.cited_references) <= refs
        ):
            raise WorkflowError("REACTION_SCOPE: retain actual actor and known sources.")
        if proposal.play_id is not None and (
            proposal.kind != "SCENE_OFFER"
            or proposal.play_id
            not in {play["id"] for play in packet["role"].get("native_plays", ())}
        ):
            raise WorkflowError("INITIATIVE_PLAY: select a current native Play as a suggestion.")
        if (proposal.fiction is not None or proposal.intended_recipients) and (
            not packet.get("activity_pilot") or proposal.kind != "DIALOGUE"
        ):
            raise WorkflowError("FICTION_INTENT_ONLY: use a reviewed AI Pilot contribution.")
        if proposal.kind != "WAIT" and not proposal.text.strip():
            raise WorkflowError("REACTION_TEXT: non-silent proposals need bounded text.")
        if packet.get("activity_alternate") and proposal.play_id and len(proposal.text) > 1200:
            raise WorkflowError("REACTION_TEXT: native Play accounts use at most 1200 characters.")
        if proposal.kind == "REQUEST_ACTION":
            if proposal.route == "none" or not proposal.source_work_id:
                raise WorkflowError("NATIVE_ROUTE_REQUIRED: identify actual pending native work.")
        elif proposal.route != "none" or proposal.source_work_id is not None:
            raise WorkflowError("REACTION_AUTHORITY: dialogue cannot carry native execution.")
        self._route(c, gm, scene, proposal)
        if packet.get("initiative") and (prior := self._initiative_proposal(c, scene, request)):
            return {"id": prior, "effects_applied": False}
        if front_move:
            from girlframe.services.director_fronts import DirectorFrontService

            if DirectorFrontService(self.context)._move_raised(c, front_move):
                raise WorkflowError("FRONT_MOVE_RAISED: review the existing proposal.")
            self._front_current(c, scene, {"front_move": front_move}, packet)
        identity = "reaction:" + str(uuid4())
        self._save(
            c,
            scene,
            identity,
            "reaction_proposal",
            request=request,
            proposal=proposal.model_dump(mode="json"),
            **({"front_move": front_move} if front_move else {}),
        )
        return dict(id=identity, effects_applied=False)

    def _front_current(
        self, c: Connection, scene: str, record: dict[str, Any], packet: dict[str, Any]
    ) -> None:
        if move := record.get("front_move"):
            from girlframe.services.director_fronts import DirectorFrontService

            if (
                DirectorFrontService(self.context).tracked_portrayal(
                    c, scene, ActorRef.model_validate(packet["actor"]), claimed=move
                )
                is None
            ):
                raise WorkflowError("STALE_FRONT_MOVE: review the current source and authority.")

    def generate(
        self,
        gm: GuildViewer,
        key: str,
        scene: str,
        request: str,
        provider: ReactionProvider,
    ) -> dict[str, Any]:
        """Provider work stays outside the transaction; freshness is rechecked on save."""
        with (
            _initiative_generation if request.startswith("reaction-initiative:") else nullcontext()
        ):
            return self._generate(gm, key, scene, request, provider)

    def _generate(
        self, gm: GuildViewer, key: str, scene: str, request: str, provider: ReactionProvider
    ) -> dict[str, Any]:
        payload = dict(scene=scene, request=request)
        with self.store.engine.connect() as c:
            self._scope(c, gm, scene)
            packet = self._get(c, scene, request, "reaction_request")["packet"]
            if packet.get("initiative"):
                self.initiative.scope(c, gm, scene)
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
            self._fresh(c, packet)
            if packet.get("initiative"):
                if prior := self._initiative_proposal(c, scene, request):
                    return {"id": prior, "effects_applied": False}
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
            authorize=lambda c: (
                self.initiative.scope(c, gm, scene)
                if packet.get("initiative")
                else self._scope(c, gm, scene)
            ),
        )

    def _handler_initiative(
        self, c: Connection, gm: GuildViewer, scene: str, identity: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self.initiative.scope(c, gm, scene)
        record = self._get(c, scene, identity, "reaction_proposal")
        packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
        if (
            not packet.get("initiative")
            or packet["actor"]["kind"] != "handler"
            or packet["controller"] not in (str(gm.user_id), str(self.store.policy.application_id))
        ):
            raise WorkflowError("INITIATIVE_REVIEW_OWNER: use the authorized Handler review.")
        return record, packet

    def handler_initiative_review(
        self, gm: GuildViewer, scene: str, identity: str
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            record, packet = self._handler_initiative(c, gm, scene, identity)
            if self._stale_review(c, scene, identity, packet):
                return {"id": identity, "status": "stale_reopen_source"}
            return {
                "id": identity,
                "actor": packet["actor"],
                "proposal": {k: v for k, v in record["proposal"].items() if k != "rationale"},
                "effects_applied": False,
                "publication": "private_review_only",
                **self._native_play_preview(c, scene, identity, record, packet),
            }

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
            if packet.get("activity_alternate") and (
                receipt := self._alternate_receipt(c, scene, identity)
            ):
                return dict(id=identity, status="native_started", receipt=receipt)
            if (
                packet.get("initiative")
                or self.observer._state(c, scene).activity_epoch is not None
            ) and self._stale_review(c, scene, identity, packet):
                return {"id": identity, "status": "stale_reopen_source", "effects_applied": False}
            return dict(
                id=identity,
                actor=packet["actor"],
                proposal={k: v for k, v in record["proposal"].items() if k != "rationale"},
                publication="private_review_only",
                effects_applied=False,
                **self._pilot_review_options(c, scene, identity, record, packet),
                **self._native_play_preview(c, scene, identity, record, packet),
            )

    def _native_play_preview(
        self,
        c: Connection,
        scene: str,
        identity: str,
        record: dict[str, Any],
        packet: dict[str, Any],
    ) -> dict[str, Any]:
        selected = next(
            (
                play
                for play in packet["role"].get("native_plays", ())
                if play["id"] == record["proposal"].get("play_id")
            ),
            None,
        )
        if selected is None:
            return {}
        review = self._review_record(c, scene, identity)
        return {
            "native_play": selected,
            "native_play_approved": bool(review and review["decision"] == "approve"),
        }

    def start_alternate_play(
        self,
        viewer: GuildViewer,
        scene: str,
        identity: str,
        choices: dict[str, Any],
    ) -> dict[str, Any]:
        """Start the one approved exact-role Play through its existing native command."""
        from girlframe.engine.m2 import PlayInput
        from girlframe.engine.m3_gorgon_play_state import Declaration
        from girlframe.services.m3_actor_plays import ActorPlayService
        from girlframe.services.m3_gorgon_play import GorgonPlayService
        from girlframe.services.m3_npc_handover import LABELS, NpcHandoverService

        key = "director-alternate-play:" + _digest((scene, identity))

        def approved(c: Connection) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            record, packet = self._owned(c, viewer, scene, identity, fresh=False)
            row = self.observer._scene(c, scene, viewer)
            state = self.observer._state(c, scene)
            actor = ActorRef.model_validate(packet["actor"])
            role = self.initiative._alternate_roles(c, row).get(actor)
            if (
                not packet.get("activity_alternate")
                or role is None
                or self.initiative._delegated(c, row, role) != packet["activity_alternate"]
            ):
                raise WorkflowError(
                    "INITIATIVE_CONTROL_OWNER: recover the original delegated role."
                )
            if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
                raise WorkflowError("OBSERVATION_DISABLED: current scene consent required.")
            result = self._native_play_preview(c, scene, identity, record, packet)
            binding = result.get("native_play", {}).get("alternate")
            if not result.get("native_play_approved") or binding is None:
                raise WorkflowError("INITIATIVE_PLAY_REVIEW: approve this exact native Play first.")
            return record, packet, binding

        with self.store.engine.connect() as c:
            record, packet, binding = approved(c)
        actor = ActorRef.model_validate(packet["actor"])
        channel = binding["channel"]
        account = record["proposal"]["text"]
        values = binding["choices"]
        if choices.keys() != values.keys() or any(
            type(value) is not (int if field == "heat" else str) or value not in values[field]
            for field, value in choices.items()
        ):
            raise WorkflowError("INITIATIVE_PLAY_CHOICES: confirm only the listed native choices.")

        def guard(c: Connection) -> None:
            if approved(c) != (record, packet, binding):
                raise WorkflowError("STALE_REACTION: the approved Play changed.")
            if not c.scalar(
                sa.select(t.commands.c.interaction_key).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == key,
                )
            ):
                self._fresh(c, packet)
                slot = "alternate-start:" + _digest(packet["source_id"])
                table = t.director_context["shadow"]
                if c.scalar(
                    sa.select(table.c.id).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.scene_id == scene,
                        table.c.id == slot,
                    )
                ):
                    raise WorkflowError(
                        "REACTION_ADDRESSED: this actor already acted in this episode."
                    )
                self._save(c, scene, slot, "alternate_native_start", reaction_id=identity)

        game = self.observer.game
        with self.store.source_guard(guard):
            if actor.kind == "npc" and binding["play"] in LABELS:
                return NpcHandoverService(game).propose(
                    viewer,
                    key,
                    channel,
                    actor,
                    binding["play"],
                    binding["revision"],
                    binding["target_token"],
                    account,
                    choices.get("item"),
                )
            if binding["play"] == "harpy_beneath" and actor.kind == "external_pilot":
                return ActorPlayService(game).begin(
                    viewer,
                    key,
                    channel,
                    actor,
                    binding["actor_sha256"],
                    ActorRef.model_validate(binding["adjudicator"])
                    if binding["adjudicator"]
                    else None,
                    binding["cast_revision"],
                    PlayInput(
                        play="put_someone_beneath_you",
                        context=account,
                        trigger_confirmed=True,
                        heat=choices["heat"],
                        target_actor=ActorRef.model_validate(binding["target"]),
                    ),
                )
            if binding["play"] == "gorgon_attack" and actor.kind == "gorgon":
                return GorgonPlayService(game).begin(
                    viewer,
                    key,
                    channel,
                    binding["revision"],
                    Declaration(
                        kind="attack",
                        actor=actor,
                        assets=(choices["asset"],),
                        actor_sha256=binding["actor_sha256"],
                        target=ActorRef.model_validate(binding["target"]),
                        target_sha256=binding["target_sha256"],
                        account=account,
                        reach_confirmed=True,
                    ),
                )
        raise WorkflowError("NATIVE_ROUTE_REQUIRED: recover the original alternate actor's Play.")

    def _alternate_receipt(self, c: Connection, scene: str, identity: str) -> dict[str, Any] | None:
        key = "director-alternate-play:" + _digest((scene, identity))
        raw = c.scalar(
            sa.select(t.commands.c.outcome_json).where(
                t.commands.c.campaign_id == self.store.campaign_id,
                t.commands.c.interaction_key == key,
            )
        )
        return json.loads(raw) if raw else None

    def alternate_action_ids(self, c: Connection, scene: str) -> set[str]:
        table = t.director_context["shadow"]
        proposals = c.scalars(
            sa.select(sa.func.json_extract(table.c.body_json, "$.reaction_id")).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                sa.func.json_extract(table.c.body_json, "$.record_type")
                == "alternate_native_start",
            )
        )
        return {
            receipt["action_id"]
            for proposal in proposals
            if (receipt := self._alternate_receipt(c, scene, proposal)) and "action_id" in receipt
        }

    def _pilot_review_options(
        self,
        c: Connection,
        scene: str,
        identity: str,
        record: dict[str, Any],
        packet: dict[str, Any],
    ) -> dict[str, Any]:
        if not packet.get("activity_pilot") or record["proposal"]["kind"] != "DIALOGUE":
            return {}
        approval = self._review_record(c, scene, identity)
        if approval is not None:
            return {"approved_recipients": (approval.get("delivery") or {}).get("recipients", [])}
        from girlframe.services.director_dossiers import DirectorDossierService
        from girlframe.services.director_npc_delivery import NpcDeliveryService

        delivery = NpcDeliveryService(self.context)
        dossiers = DirectorDossierService(self.context)
        actor = ActorRef.model_validate(packet["actor"])
        row = self.observer._scene(c, scene)
        eligible = []
        intended = tuple(
            ActorRef.model_validate(value)
            for value in record["proposal"].get("intended_recipients", ())
        )
        for listener in delivery.knowledge._actor_views(c, row):
            if (
                listener.ref.kind == "npc"
                and listener.controller != int(packet["controller"])
                and not dossiers._visible_identity(c, actor, listener.ref)
            ):
                continue
            if intended and listener.ref not in intended:
                continue
            try:
                delivery.plan(c, scene, packet, record["proposal"], intended or (listener.ref,))
            except WorkflowError:
                continue
            eligible.append(
                {"actor": listener.ref.model_dump(mode="json"), "label": listener.label}
            )
        return {"delivery_candidates": eligible}

    def _stale_review(
        self, c: Connection, scene: str, identity: str, packet: dict[str, Any]
    ) -> bool:
        approval = self._review_record(c, scene, identity)
        try:
            self._fresh(
                c, packet, approved_run=bool(approval and approval["decision"] == "approve")
            )
            self._front_current(
                c, scene, self._get(c, scene, identity, "reaction_proposal"), packet
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

    def pending(
        self, viewer: GuildViewer, scene: str, *, gm: bool = False, handler_initiative: bool = False
    ) -> list[dict[str, Any]]:
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
                r["id"].removesuffix(":review"): r
                for r in records
                if r.get("record_type") == "reaction_review"
            }
            delivered = {
                r["id"].removeprefix("npc-delivery:")
                for r in records
                if r.get("record_type") == "npc_delivery"
            }
            result = []
            for record in records:
                if record.get("record_type") != "reaction_proposal":
                    continue
                approval = reviewed.get(record["id"])
                native = bool(
                    approval
                    and approval["decision"] == "approve"
                    and record["proposal"].get("play_id")
                )
                if (
                    approval
                    and not native
                    and (gm or not approval.get("delivery") or record["id"] in delivered)
                ):
                    continue
                if handler_initiative:
                    try:
                        _, packet = self._handler_initiative(c, viewer, scene, record["id"])
                    except WorkflowError:
                        continue
                elif gm:
                    packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
                else:
                    try:
                        _, packet = self._owned(c, viewer, scene, record["id"], fresh=False)
                    except (WorkflowError, ValueError):
                        continue
                if approval and not native and not packet.get("activity_pilot"):
                    continue
                status = (
                    "approved_native_suggestion"
                    if native
                    else "awaiting_delivery"
                    if approval
                    else "awaiting_controller_review"
                )
                if packet.get("activity_alternate") and self._alternate_receipt(
                    c, scene, record["id"]
                ):
                    status = "native_started"
                else:
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
                        **({"ai_pilot": True} if packet.get("activity_pilot") else {}),
                        **({"ai_alternate": True} if packet.get("activity_alternate") else {}),
                        **({"initiative": True} if packet.get("initiative") else {}),
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
        handler_initiative: bool = False,
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject") or not reason.strip() or len(reason) > 1200:
            raise WorkflowError("REACTION_REVIEW_INVALID: provide bounded decision/reason.")

        def authorize(c: Connection) -> None:
            if handler_initiative:
                self._handler_initiative(c, controller, scene, identity)
            else:
                self._owned(c, controller, scene, identity, fresh=False)

        def operation(c: Connection) -> dict[str, Any]:
            record = self._get(c, scene, identity, "reaction_proposal")
            packet = self._get(c, scene, record["request"], "reaction_request")["packet"]
            plan = None
            if recipients and decision != "approve":
                raise WorkflowError("NPC_DELIVERY_REVIEW: only approval names listeners.")
            if decision == "approve":
                self._fresh(c, packet)
                self._front_current(c, scene, record, packet)
                if packet.get("activity_pilot") and record["proposal"]["kind"] == "DIALOGUE":
                    if not recipients:
                        raise WorkflowError("AI_PILOT_AUDIENCE: choose the actual listeners.")
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
            if decision == "approve" and not packet.get("activity_alternate"):
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
                    and not packet.get("initiative")
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
