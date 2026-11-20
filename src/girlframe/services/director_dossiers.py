"""Append-only actor dossiers; actual controllers alone confirm their self portrayal."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import DirectorContext
from girlframe.ai.director_dossiers import (
    DossierNote,
    DossierPacket,
    DossierProfile,
    DossierProposal,
    DossierRecord,
    DossierState,
    HandlerExperience,
    HandlerIdentity,
    Personnel,
    StartingRelationship,
)
from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_development import current as current_developments
from girlframe.services.director_closeout import handler_experiences
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.director_worldbuilding import DirectorWorldbuildingService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorDossierService:
    def __init__(self, context: DirectorContextService):
        self.context, self.observer, self.store = context, context.observations, context.store
        self.game = self.observer.game
        self.knowledge = DirectorKnowledgeService(context)
        self.actors = ActorService(MissionService(self.store))

    def _scope(self, c: Connection, viewer: GuildViewer, scene: str, *, gm: bool = False) -> None:
        self.store.guild_member(viewer)
        self.observer._scope()
        self.game.unpaused(c)
        row = self.observer._scene(c, scene, viewer)
        state = self.observer._state(c, scene)
        if state.policy.mode != "shadow" or not self.observer._consented(c, row, state):
            raise WorkflowError("OBSERVATION_DISABLED: retain current scene consent.")
        if gm:
            self.store.administrator(viewer)

    def _actor(self, c: Connection, scene: str, actor: ActorRef) -> ActorView:
        row = self.observer._scene(c, scene)
        if actor not in self.knowledge._actors(c, row):
            raise WorkflowError("DOSSIER_ACTOR_UNAVAILABLE: select an actual current scene role.")
        try:
            return resolve(
                load_state(c, self.store.campaign_id), actor, profiles(c, self.store.campaign_id)
            )
        except ValueError:
            raise WorkflowError("DOSSIER_ACTOR_UNAVAILABLE: recover this actual actor.") from None

    @staticmethod
    def _records(canon: GameState, actor: ActorRef) -> tuple[DossierRecord, ...]:
        values = tuple(
            DossierRecord.model_validate_json(fact["body"])
            for fact in canon.facts
            if fact.get("kind") == "director_dossier"
        )
        history = tuple(value for value in values if value.actor == actor)
        for index, value in enumerate(history):
            if value.version != index + 1 or value.supersedes != (
                history[index - 1].id if index else None
            ):
                raise WorkflowError("DOSSIER_HISTORY_INVALID: retain exact dossier revisions.")
        return history

    @staticmethod
    def _notes(canon: GameState, actor: ActorRef) -> tuple[DossierNote, ...]:
        values = tuple(
            DossierNote.model_validate_json(fact["body"])
            for fact in canon.facts
            if fact.get("kind") == "director_dossier_note"
        )
        history = tuple(value for value in values if value.actor == actor)
        for index, value in enumerate(history):
            if value.version != index + 1 or value.supersedes != (
                history[index - 1].id if index else None
            ):
                raise WorkflowError("DOSSIER_HISTORY_INVALID: retain exact private note revisions.")
        return history

    def _context(self, c: Connection, scene: str, actor: ActorRef) -> DirectorContext:
        self._actor(c, scene, actor)
        refs = self.context._actor_references(self.context._current(c, scene), actor)
        return DirectorContext(
            campaign_id=self.store.campaign_id,
            scene_id=scene,
            audience="actor",
            actor=actor,
            references=refs,
            revision=_digest([ref.model_dump(mode="json") for ref in refs]),
        )

    def _visible_identity(self, c: Connection, perspective: ActorRef, subject: ActorRef) -> bool:
        canon = load_state(c, self.store.campaign_id)
        if subject == perspective:
            return True
        if subject.kind == "pilot":
            return (
                int(subject.entity) in canon.order
                and str(subject.entity) in canon.sheets
                and canon.sheets[subject.entity].character_id == subject.incarnation
            )
        if subject.kind == "handler":
            return (
                str(canon.handler) == subject.entity
                and subject.incarnation is None
                and not any(value.active for value in canon.director_contexts)
            )
        if subject.kind == "npc" and canon.world:
            linked = any(
                link.npc == subject.entity
                and perspective.kind == "pilot"
                and link.owner == int(perspective.entity)
                and link.character_id == perspective.incarnation
                for link in canon.world.starting_npc_links
            )
            return any(
                npc.id == subject.entity and npc.alive and (npc.revealed or linked)
                for npc in canon.world.npcs
            )
        return False

    def _known_goals(self, c: Connection, scene: str, context: DirectorContext) -> set[str]:
        world = DirectorWorldbuildingService(self.context)
        known = set()
        for ref in context.references:
            if ref.classification != "established_world":
                continue
            origin, source = ref.origin_scene or scene, ref.source_id
            if source.startswith("knowledge-acquired:"):
                source = self.knowledge._record(c, origin, source, "knowledge_acquisition")[
                    "source"
                ]["id"]
            if not source.startswith("world-disclosure:"):
                continue
            disclosure = world._record(c, origin, source, "worldbuilding_disclosure")
            commit, _ = world._prove_commit(c, origin, disclosure["commit_id"])
            identity = commit["native_result"].get("id")
            if isinstance(identity, str):
                known.add(identity)
        return known

    def _validate_state(
        self, c: Connection, scene: str, actor: ActorRef, state: DossierState
    ) -> None:
        context = self._context(c, scene, actor)
        visible = {
            identity
            for ref in context.references
            for identity in (ref.id, ref.origin_reference)
            if identity is not None
        }
        perspectives = (
            *state.pressures,
            *state.promises,
            *state.beliefs,
            *state.obligations,
            *state.experiences,
            *state.relationships,
        )
        if not set(state.resource_refs) <= visible or any(
            not set(value.knowledge_refs) <= visible for value in perspectives
        ):
            raise WorkflowError("DOSSIER_UNKNOWN_SOURCE: cite only this actor's known references.")
        if any(
            not self._visible_identity(c, actor, relation.subject)
            for relation in state.relationships
        ):
            raise WorkflowError(
                "DOSSIER_UNKNOWN_ACTOR: relationship subjects require native visibility."
            )
        goals = set(state.goal_refs) | ({state.objective_ref} if state.objective_ref else set())
        current = {
            value.id
            for value in current_developments(load_state(c, self.store.campaign_id))
            if value.kind == "goal"
        }
        if goals and (not goals <= current or not goals <= self._known_goals(c, scene, context)):
            raise WorkflowError(
                "DOSSIER_GOAL_UNAVAILABLE: disclose actual current canonical goals."
            )

    def _binding(self, c: Connection, scene: str, actor: ActorRef) -> str:
        actual = self._actor(c, scene, actor)
        canon = load_state(c, self.store.campaign_id)
        history = self._records(canon, actor)
        row = self.observer._scene(c, scene)
        observation = self.observer._state(c, scene).model_copy(update={"generation": 0})
        return _digest(
            {
                "actor": actor.model_dump(mode="json"),
                "controller": actual.controller,
                "head": history[-1].id if history else None,
                "context": self._context(c, scene, actor).model_dump(mode="json"),
                "guard": self.observer._guard(c, row, observation),
                "consent_generation": observation.consent_generation,
            }
        )

    def _proposal(self, c: Connection, scene: str, identity: str) -> DossierProposal:
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id,
                table.c.scene_id == scene,
                table.c.id == identity,
            )
        )
        body = json.loads(raw) if raw else None
        if not body or body.get("record_type") != "dossier_proposal":
            raise WorkflowError("DOSSIER_PROPOSAL_UNAVAILABLE: reopen the actual dossier proposal.")
        return DossierProposal.model_validate_json(json.dumps(body["proposal"]))

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        actor: ActorRef,
        expected_version: int,
        profile: DossierProfile,
        state: DossierState,
        personnel: Personnel | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            actual = self._actor(c, scene, actor)
            if actual.controller != viewer.user_id:
                self.store.administrator(viewer)
            history = self._records(load_state(c, self.store.campaign_id), actor)
            if expected_version != len(history):
                raise WorkflowError("STALE_DOSSIER: use the exact current dossier revision.")
            self._validate_state(c, scene, actor, state)
            proposal = DossierProposal(
                id="dossier-proposal:" + str(uuid4()),
                scene_id=scene,
                actor=actor,
                controller=actual.controller,
                proposer=viewer.user_id,
                expected_version=expected_version,
                profile=profile,
                state=state,
                personnel=personnel or Personnel(),
                binding=self._binding(c, scene, actor),
            )
            c.execute(
                t.director_context["shadow"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    scene_id=scene,
                    id=proposal.id,
                    body_json=json.dumps(
                        {
                            "record_type": "dossier_proposal",
                            "proposal": proposal.model_dump(mode="json"),
                        }
                    ),
                )
            )
            return {"id": proposal.id, "application": "controller_review_only"}

        return self.store._write(
            viewer,
            key,
            "director.dossier_propose",
            {
                "scene": scene,
                "actor": actor.model_dump(mode="json"),
                "version": expected_version,
                "profile": profile.model_dump(mode="json"),
                "state": state.model_dump(mode="json"),
                "personnel": (personnel or Personnel()).model_dump(mode="json"),
            },
            operation,
            authorize=lambda c: self._scope(c, viewer, scene),
            auto_audit=False,
        )

    def review(self, viewer: GuildViewer, scene: str, identity: str) -> DossierProposal:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            proposal = self._proposal(c, scene, identity)
            actual = self._actor(c, scene, proposal.actor)
            if proposal.controller != viewer.user_id or actual.controller != viewer.user_id:
                raise WorkflowError(
                    "DOSSIER_NOT_OWNED: only its original actual controller reviews."
                )
            return proposal

    def pending(self, viewer: GuildViewer, scene: str, *, gm: bool = False) -> list[dict[str, Any]]:
        """Current-owner discovery only; self portrayal never enters work metadata."""
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=gm)
            canon = load_state(c, self.store.campaign_id)
            confirmed = {
                DossierRecord.model_validate_json(fact["body"]).proposal_id
                for fact in canon.facts
                if fact.get("kind") == "director_dossier"
            }
            table = t.director_context["shadow"]
            ids = c.scalars(
                sa.select(table.c.id).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.scene_id == scene,
                    sa.func.json_extract(table.c.body_json, "$.record_type") == "dossier_proposal",
                )
            )
            result = []
            for identity in ids:
                if identity in confirmed:
                    continue
                proposal = self._proposal(c, scene, identity)
                try:
                    actual = self._actor(c, scene, proposal.actor)
                except WorkflowError:
                    continue
                if not gm and (
                    proposal.controller != viewer.user_id or actual.controller != viewer.user_id
                ):
                    continue
                try:
                    current = proposal.binding == self._binding(c, scene, proposal.actor)
                except WorkflowError:
                    # Recovery metadata must remain usable when an old source needs retirement.
                    current = False
                result.append(
                    {
                        "id": identity,
                        "actor": proposal.actor.model_dump(mode="json"),
                        "controller": proposal.controller,
                        "expected_version": proposal.expected_version,
                        "status": "awaiting_controller_confirmation"
                        if current
                        else "stale_reopen_source",
                    }
                )
            return result

    def confirm(self, viewer: GuildViewer, key: str, scene: str, identity: str) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)
            proposal = self._proposal(c, scene, identity)
            if (
                proposal.controller != viewer.user_id
                or self._actor(c, scene, proposal.actor).controller != viewer.user_id
            ):
                raise WorkflowError("DOSSIER_NOT_OWNED: only the actual controller confirms.")

        def operation(c: Connection) -> dict[str, Any]:
            proposal = self._proposal(c, scene, identity)
            actual = self._actor(c, scene, proposal.actor)
            if proposal.controller != viewer.user_id or actual.controller != viewer.user_id:
                raise WorkflowError("DOSSIER_NOT_OWNED: only the actual controller confirms.")
            if proposal.binding != self._binding(c, scene, proposal.actor):
                raise WorkflowError("STALE_DOSSIER: reopen current actor, knowledge and revision.")
            self._validate_state(c, scene, proposal.actor, proposal.state)
            canon = load_state(c, self.store.campaign_id)
            history = self._records(canon, proposal.actor)
            event = str(uuid4())
            record = DossierRecord(
                id="dossier:" + str(uuid4()),
                actor=proposal.actor,
                controller=viewer.user_id,
                version=len(history) + 1,
                supersedes=history[-1].id if history else None,
                profile=proposal.profile,
                state=proposal.state,
                personnel=proposal.personnel,
                scene_id=scene,
                proposal_id=identity,
                source_event=event,
            )
            canon.facts.append({"kind": "director_dossier", "body": record.model_dump_json()})
            self.game.event(
                c,
                viewer.user_id,
                key,
                "director.dossier_confirmed",
                canon,
                event_id=event,
                actor_token=record.actor.token,
                version=record.version,
            )
            return {"id": record.id, "version": record.version, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.dossier_confirm",
            {"scene": scene, "proposal": identity},
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def gm_notes(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        actor: ActorRef,
        expected_version: int,
        text: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._actor(c, scene, actor)
            canon = load_state(c, self.store.campaign_id)
            history = self._notes(canon, actor)
            if expected_version != len(history):
                raise WorkflowError("STALE_DOSSIER: refresh private author notes.")
            event = str(uuid4())
            note = DossierNote(
                id="dossier-note:" + str(uuid4()),
                actor=actor,
                version=len(history) + 1,
                supersedes=history[-1].id if history else None,
                text=text,
                author=viewer.user_id,
                scene_id=scene,
                source_event=event,
            )
            canon.facts.append({"kind": "director_dossier_note", "body": note.model_dump_json()})
            self.game.event(
                c,
                viewer.user_id,
                key,
                "director.dossier_note_recorded",
                canon,
                event_id=event,
                actor_token=actor.token,
                version=note.version,
            )
            return {"id": note.id, "version": note.version, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.dossier_note",
            {
                "scene": scene,
                "actor": actor.model_dump(mode="json"),
                "version": expected_version,
                "text": text,
            },
            operation,
            authorize=lambda c: self._scope(c, viewer, scene, gm=True),
            auto_audit=False,
        )

    def gm(self, viewer: GuildViewer, scene: str, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene, gm=True)
            self._actor(c, scene, actor)
            canon = load_state(c, self.store.campaign_id)
            return {
                "history": [value.model_dump(mode="json") for value in self._records(canon, actor)],
                "private_notes": [
                    value.model_dump(mode="json") for value in self._notes(canon, actor)
                ],
            }

    def _role_packet(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        *,
        subjects: tuple[ActorRef, ...] | None = None,
        omit_stale_portrayal: bool = False,
    ) -> DossierPacket:
        """Internal projection; caller separately establishes actual GM/controller access."""
        actual = self._actor(c, scene, actor)
        canon = load_state(c, self.store.campaign_id)
        history = self._records(canon, actor)
        head = history[-1] if history else None
        entitled = head is not None and head.controller == actual.controller
        context = self._context(c, scene, actor)
        portrayal = head if entitled else None
        if portrayal is not None:
            try:
                self._validate_state(c, scene, actor, portrayal.state)
            except WorkflowError as error:
                if not omit_stale_portrayal or not str(error).startswith(
                    ("DOSSIER_UNKNOWN_", "DOSSIER_GOAL_UNAVAILABLE:")
                ):
                    raise
                portrayal = None
        identity = None
        experiences: tuple[HandlerExperience, ...] = ()
        if actor.kind == "handler" and actor == active_handler(canon):
            row = self.observer._scene(c, scene)
            pilots = tuple(
                subject
                for subject in self.knowledge._actors(c, row)
                if subject.kind == "pilot" and (subjects is None or subject in subjects)
            )
            experiences = handler_experiences(self.context, c, actor, pilots)
            sheet = canon.handler_persona
            if sheet is not None and sheet.id == actor.incarnation:
                # Native activation verifies acceptance of each exact starting history.
                agreed = next((x for x in sheet.draft.starting if x.pilot in pilots), None)
                identity = HandlerIdentity(
                    name=sheet.draft.name,
                    activation_event=sheet.source_event,
                    starting_relationship=StartingRelationship(
                        pilot=agreed.pilot, shared_history=agreed.history
                    )
                    if agreed
                    else None,
                )
        payload = {
            "actor": actor.model_dump(mode="json"),
            "controller": actual.controller,
            "dossier": portrayal.model_dump(mode="json") if portrayal else None,
            "context": context.model_dump(mode="json"),
            **({"handler_identity": identity.model_dump(mode="json")} if identity else {}),
            **(
                {"handler_experiences": [x.model_dump(mode="json") for x in experiences]}
                if experiences
                else {}
            ),
        }
        return DossierPacket(
            actor=actor,
            dossier_version=head.version if head else 0,
            dossier_id=portrayal.id if portrayal else None,
            profile=portrayal.profile if portrayal else None,
            state=portrayal.state if portrayal else None,
            handler_identity=identity,
            handler_experiences=experiences,
            context=context,
            source_refs=tuple(ref.id for ref in context.references),
            revision=_digest(payload),
            controller_rebase_required=head is not None and not entitled,
        )

    def role_packet(self, viewer: GuildViewer, scene: str, actor: ActorRef) -> DossierPacket:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            if self._actor(c, scene, actor).controller != viewer.user_id:
                raise WorkflowError("DOSSIER_NOT_OWNED: use your own actual actor.")
            return self._role_packet(c, scene, actor)

    def personnel(
        self, viewer: GuildViewer, scene: str, perspective: ActorRef, subject: ActorRef
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            if self._actor(c, scene, perspective).controller != viewer.user_id:
                raise WorkflowError("DOSSIER_NOT_OWNED: use your own actual perspective.")
            known = self.actors.known(viewer, perspective, require_current_profile=True)["actors"]
            if subject not in [ActorRef.model_validate(value["ref"]) for value in known]:
                raise WorkflowError(
                    "DOSSIER_IDENTITY_UNKNOWN: native identity visibility is required."
                )
            actual = self._actor(c, scene, subject)
            history = self._records(load_state(c, self.store.campaign_id), subject)
            head = history[-1] if history and history[-1].controller == actual.controller else None
            return {
                "actor": subject.model_dump(mode="json"),
                "label": actual.label,
                "personnel": head.personnel.model_dump(mode="json")
                if head
                else Personnel().model_dump(mode="json"),
            }
