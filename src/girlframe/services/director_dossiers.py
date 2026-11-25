"""Append-only actor dossiers; actual controllers alone confirm their self portrayal."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import DirectorContext, KnowledgeReference
from girlframe.ai.director_dossiers import (
    CharacterSetup,
    DossierContinuity,
    DossierContinuityEdit,
    DossierMemorySource,
    DossierNote,
    DossierPacket,
    DossierProfile,
    DossierProposal,
    DossierRecord,
    DossierState,
    HandlerExperience,
    HandlerIdentity,
    Personnel,
    PilotDossierOrigin,
    RelationshipTerm,
    StartingRelationship,
)
from girlframe.database import tables as t
from girlframe.engine.campaign_opening import PlannedAIPilot
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_development import current as current_developments
from girlframe.engine.pilot_portrayal import PilotPortrayal
from girlframe.services.campaign_difficulty import opening
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
            return subject == active_handler(canon)
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
        if subject.kind in ("gorgon", "external_pilot"):
            from girlframe.services.m3_consume_support import knowledge_allowed

            if not knowledge_allowed(canon, subject):
                return False
            if subject.kind == "gorgon":
                return canon.world is not None and any(
                    x.id == subject.entity and x.alive and x.revealed for x in canon.world.gorgons
                )
            if any(
                x.id == subject.entity and x.alive and x.revealed for x in canon.harpy_states
            ) or any(x.id == subject.entity and x.alive and x.revealed for x in canon.janus_cores):
                return True
            return canon.world is not None and any(
                x.kind == "harpy" and x.id == subject.entity and x.alive and x.revealed
                for x in canon.world.pilots
            )
        return False

    def _continuity_sources(
        self, c: Connection, scene: str, actor: ActorRef, context: DirectorContext
    ) -> dict[str, KnowledgeReference]:
        """Use exact heard words in this scene, not raw mixed narration or another role."""
        return {
            ref.id: ref
            for ref in context.references
            if ref.origin_scene is None
            and ref.classification == "reported_claim"
            and (
                ref.source_id.startswith(
                    ("handler-delivery:", "npc-delivery:", "knowledge-acquired:")
                )
                or ref.text.removeprefix("Reported claim: ")
                in self.knowledge.heard(c, scene, ref.source_id, actor)
            )
        }

    def _continuity_updates(
        self, c: Connection, scene: str, actor: ActorRef, edits: tuple[DossierContinuityEdit, ...]
    ) -> tuple[DossierContinuity, ...]:
        sources = self._continuity_sources(c, scene, actor, self._context(c, scene, actor))
        participants = set(self.knowledge._actors(c, self.observer._scene(c, scene))) - {actor}
        consent = self.observer._state(c, scene).consent_generation
        updates = []
        for edit in edits:
            if not set(edit.knowledge_refs) <= sources.keys():
                raise WorkflowError("CONTINUITY_SOURCE: choose words this character heard here.")
            if edit.subject is not None and (
                edit.subject not in participants
                or not self._visible_identity(c, actor, edit.subject)
            ):
                raise WorkflowError("CONTINUITY_SUBJECT: choose an actual known scene counterpart.")
            updates.append(
                DossierContinuity(
                    kind=edit.kind,
                    text=edit.text,
                    knowledge_refs=edit.knowledge_refs,
                    subject=edit.subject,
                    origin_scene=scene,
                    consent_generation=consent,
                )
            )
        return tuple(updates)

    def _visible_continuity(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        controller: int,
        entries: tuple[DossierContinuity, ...],
    ) -> tuple[DossierContinuity, ...]:
        origins: dict[tuple[str, int], set[str]] = {}
        visible = []
        for entry in entries:
            key = (entry.origin_scene, entry.consent_generation)
            if key not in origins:
                origins[key] = self._continuity_origin_refs(c, scene, actor, controller, *key)
            if set(entry.knowledge_refs) <= origins[key] and (
                entry.subject is None or self._visible_identity(c, actor, entry.subject)
            ):
                visible.append(entry)
        return tuple(visible[-6:])

    def _continuity_origin_refs(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        controller: int,
        origin: str,
        consent: int,
    ) -> set[str]:
        try:
            row = self.observer._scene(c, origin, allow_closed=True)
            state = self.observer._state(c, origin)
            if (
                (origin != scene and row["open"])
                or controller not in row["participants"]
                or state.policy.mode != "shadow"
                or state.consent_generation != consent
                or not self.observer._consented(c, row, state)
            ):
                return set()
            return {
                ref.id
                for ref in self.context._current(c, origin, allow_closed=True)
                if actor.token in ref.known_by and ref.origin_scene is None
            }
        except WorkflowError:
            return set()

    def _personal_memory_sources(
        self,
        c: Connection,
        scene: str,
        context: DirectorContext,
        selected: tuple[str, ...],
    ) -> tuple[DossierMemorySource, ...]:
        consent = self.observer._state(c, scene).consent_generation
        return tuple(
            DossierMemorySource(reference_id=ref.id, origin_scene=scene, consent_generation=consent)
            for ref in context.references
            if ref.origin_scene is None and ref.id in selected
        )

    def _visible_memory_sources(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        controller: int,
        sources: tuple[DossierMemorySource, ...],
    ) -> set[str]:
        origins: dict[tuple[str, int], set[str]] = {}
        proven = set()
        for source in sources:
            key = (source.origin_scene, source.consent_generation)
            if key not in origins:
                origins[key] = self._continuity_origin_refs(c, scene, actor, controller, *key)
            if source.reference_id in origins[key]:
                proven.add(source.reference_id)
        return proven

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
        visible = self._reference_ids(context)
        perspectives = (
            *state.pressures,
            *state.promises,
            *state.beliefs,
            *state.obligations,
            *state.experiences,
            *state.relationships,
            *state.terms,
        )
        if not set(state.resource_refs) <= visible or any(
            not set(value.knowledge_refs) <= visible for value in perspectives
        ):
            raise WorkflowError("DOSSIER_UNKNOWN_SOURCE: cite only this actor's known references.")
        sources = tuple(
            source
            for entry in (*state.pressures, *state.terms)
            for source in getattr(entry, "memory_sources", ())
        )
        if sources and set(sources) - set(
            self._personal_memory_sources(c, scene, context, tuple(visible))
        ):
            raise WorkflowError("DOSSIER_UNKNOWN_SOURCE: keep native memory provenance.")
        if any(
            not self._visible_identity(c, actor, relation.subject)
            for relation in state.relationships
        ):
            raise WorkflowError(
                "DOSSIER_UNKNOWN_ACTOR: relationship subjects require native visibility."
            )
        for entry in state.terms:
            self._validate_term(c, scene, actor, entry)
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

    def _validate_term(
        self, c: Connection, scene: str, actor: ActorRef, entry: RelationshipTerm
    ) -> None:
        actors = {actor.token, entry.subject.token}
        if len(actors) != 2 or not self._visible_identity(c, actor, entry.subject):
            raise WorkflowError("DOSSIER_UNKNOWN_ACTOR: use a known counterpart.")
        heard = set()
        for ref in self.context._current(c, scene):
            identity = ref.origin_reference or ref.id
            if identity not in entry.knowledge_refs or not actors <= set(ref.known_by):
                continue
            if ref.reported_by in (actor, entry.subject):
                heard.add(identity)
            elif (
                ref.reported_by is None
                and ref.origin_scene is None
                and ref.classification == "reported_claim"
            ):
                source = self.observer._latest_source(c, ref.source_id)
                words = ref.text.removeprefix("Reported claim: ")
                if (
                    source
                    and source.actor in (actor, entry.subject)
                    and all(
                        words in self.knowledge.heard(c, scene, ref.source_id, listener)
                        for listener in (actor, entry.subject)
                    )
                ):
                    heard.add(identity)
        if not set(entry.knowledge_refs) <= heard:
            raise WorkflowError("TERM_SOURCE: cite words spoken and heard by both characters.")

    def _pilot_memory(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        controller: int,
        context: DirectorContext,
        state: DossierState,
    ) -> DossierState:
        """Keep an authorized portrayal usable when only some memories carried forward."""
        seen = self._reference_ids(context)
        referenced = tuple(
            source
            for entry in (*state.pressures, *state.terms)
            for source in getattr(entry, "memory_sources", ())
        )
        known_memory = (seen - {source.reference_id for source in referenced}) | (
            self._visible_memory_sources(c, scene, actor, controller, referenced)
        )
        goals = set()
        if state.goal_refs or state.objective_ref:
            goals = self._known_goals(c, scene, context) & {
                value.id
                for value in current_developments(load_state(c, self.store.campaign_id))
                if value.kind == "goal"
            }
        return state.model_copy(
            update={
                "objective_ref": state.objective_ref if state.objective_ref in goals else None,
                "goal_refs": tuple(goal for goal in state.goal_refs if goal in goals),
                "resource_refs": tuple(ref for ref in state.resource_refs if ref in seen),
                **{
                    name: tuple(
                        item for item in getattr(state, name) if set(item.knowledge_refs) <= seen
                    )
                    for name in ("promises", "beliefs", "obligations", "experiences")
                },
                "pressures": tuple(
                    entry for entry in state.pressures if set(entry.knowledge_refs) <= known_memory
                ),
                "relationships": tuple(
                    entry
                    for entry in state.relationships
                    if set(entry.knowledge_refs) <= seen
                    and self._visible_identity(c, actor, entry.subject)
                ),
                "terms": tuple(
                    entry
                    for entry in state.terms
                    if set(entry.knowledge_refs) <= known_memory
                    and self._visible_identity(c, actor, entry.subject)
                ),
            }
        )

    @staticmethod
    def _reference_ids(context: DirectorContext) -> set[str]:
        return {
            identity
            for ref in context.references
            for identity in (ref.id, ref.origin_reference)
            if identity is not None
        }

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

    @staticmethod
    def _matches_pilot(actual: ActorView, pilot: PlannedAIPilot) -> bool:
        if actual.ref.kind == "pilot":
            portrayal = pilot.portrayal
            return bool(
                actual.rules == "girl_frame"
                and portrayal
                and portrayal.girl_playbook
                and portrayal.frame_playbook
                and portrayal.girl_playbook == actual.girl
                and portrayal.frame_playbook == actual.frame
            )
        return (
            actual.ref.kind == "npc"
            and actual.rules == "npc"
            and bool({"pilot_candidate", "ex_pilot"}.intersection(actual.jobs))
        )

    @staticmethod
    def _may_bind_pilot(actual: ActorView, head: DossierRecord | None, plan: str) -> bool:
        return head is None or (
            actual.ref.kind == "pilot"
            and head.controller == actual.controller
            and (head.pilot_origin is None or head.pilot_origin.plan != plan)
        )

    @staticmethod
    def _used_pilots(canon: GameState) -> set[PilotDossierOrigin]:
        return {
            dossier.pilot_origin
            for fact in canon.facts
            if fact.get("kind") == "director_dossier"
            and (dossier := DossierRecord.model_validate_json(fact["body"])).pilot_origin
            is not None
        }

    def activity_pilots(
        self, c: Connection, scene: str
    ) -> dict[ActorRef, tuple[str, PilotPortrayal | None]]:
        """Current cast with a controller-confirmed and still-approved AI Pilot origin."""
        record = opening(c, self.store.campaign_id)
        if record is None or record.seats is None:
            return {}
        seats = {pilot.callsign: pilot for pilot in record.seats.ai_pilots}
        canon = load_state(c, self.store.campaign_id)
        pilots = {}
        for actual in self.knowledge._actor_views(c, self.observer._scene(c, scene)):
            if actual.ref.kind not in ("pilot", "npc") or actual.controller not in record.audience:
                continue
            history = self._records(canon, actual.ref)
            if not history or history[-1].controller != actual.controller:
                continue
            origin = history[-1].pilot_origin
            if origin is None or origin.plan != record.plan:
                continue
            seat = seats.get(origin.callsign)
            if seat is None or not self._matches_pilot(actual, seat):
                continue
            portrayal = history[-1].profile.pilot_portrayal
            if actual.ref.kind == "pilot" and portrayal:
                portrayal = portrayal.model_copy(
                    update={"girl_playbook": actual.girl, "frame_playbook": actual.frame}
                )
            label = actual.label if actual.ref.kind == "pilot" else origin.callsign
            pilots[actual.ref] = (label, portrayal)
        return pilots

    def pilot_options(self, viewer: GuildViewer, scene: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            record = opening(c, self.store.campaign_id)
            if record is None or record.seats is None or viewer.user_id not in record.audience:
                return {"pilots": [], "actors": []}
            canon = load_state(c, self.store.campaign_id)
            used = self._used_pilots(canon)
            seats = [
                p
                for p in record.seats.ai_pilots
                if PilotDossierOrigin(plan=record.plan, callsign=p.callsign) not in used
            ]
            actors = []
            for actual in self.knowledge._actor_views(c, self.observer._scene(c, scene)):
                if actual.controller != viewer.user_id:
                    continue
                eligible = [pilot.callsign for pilot in seats if self._matches_pilot(actual, pilot)]
                if not eligible:
                    continue
                history = self._records(canon, actual.ref)
                head = history[-1] if history else None
                if not self._may_bind_pilot(actual, head, record.plan):
                    continue
                actors.append(
                    {
                        "actor": actual.ref.model_dump(mode="json"),
                        "label": actual.label,
                        "version": len(history),
                        "eligible_pilots": eligible,
                    }
                )
            return {"plan": record.plan, "pilots": [p.callsign for p in seats], "actors": actors}

    def _approved_pilot(
        self, c: Connection, viewer: GuildViewer, actual: ActorView, origin: PilotDossierOrigin
    ) -> PlannedAIPilot:
        record = opening(c, self.store.campaign_id)
        if actual.controller != viewer.user_id:
            raise WorkflowError("PILOT_DOSSIER_OWNER: use your own present Pilot or pilot NPC.")
        if (
            record is None
            or record.seats is None
            or viewer.user_id not in record.audience
            or origin.plan != record.plan
        ):
            raise WorkflowError("PILOT_DOSSIER_PLAN: use the group's approved Session Zero plan.")
        canon = load_state(c, self.store.campaign_id)
        if origin in self._used_pilots(canon):
            raise WorkflowError("PILOT_DOSSIER_USED: this approved Pilot has a dossier.")
        history = self._records(canon, actual.ref)
        head = history[-1] if history else None
        if not self._may_bind_pilot(actual, head, record.plan):
            raise WorkflowError("PILOT_DOSSIER_USED: this actor already has a bound dossier.")
        for pilot in record.seats.ai_pilots:
            if pilot.callsign == origin.callsign:
                if not self._matches_pilot(actual, pilot):
                    raise WorkflowError(
                        "PILOT_DOSSIER_SHEET: choose a matching native Girl and Frame or pilot NPC."
                    )
                return pilot
        raise WorkflowError("PILOT_DOSSIER_PLAN: choose a Pilot on the approved plan.")

    def propose_pilot(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        actor: ActorRef,
        origin: PilotDossierOrigin,
        version: int = 0,
    ) -> dict[str, Any]:
        return self.propose(
            viewer,
            key,
            scene,
            actor,
            version,
            DossierProfile(),
            DossierState(),
            pilot_origin=origin,
        )

    @staticmethod
    def _pilot_profile(pilot: PlannedAIPilot) -> DossierProfile:
        traits = pilot.portrayal
        if traits is None:
            return DossierProfile(presence="recurring", background=pilot.concept.strip())
        style = " · ".join(x.strip() for x in (traits.archetype, traits.vibe) if x.strip())
        background = "\n".join(
            x
            for x in (
                style,
                pilot.concept.strip(),
                "Personal aim: " + traits.goal.strip() if traits.goal.strip() else "",
            )
            if x
        )
        behavior = "\n".join(
            x
            for x in (
                traits.approach.strip(),
                "After a mistake: " + traits.repair.strip() if traits.repair.strip() else "",
            )
            if x
        )
        return DossierProfile(
            presence="recurring",
            background=background,
            voice=traits.voice.strip(),
            behavior=behavior[:1000],
            reaction_tendencies=(traits.pressure.strip(),) if traits.pressure.strip() else (),
            values=(traits.value.strip(),) if traits.value.strip() else (),
            fears=(traits.fear.strip(),) if traits.fear.strip() else (),
            contradictions=(traits.contradiction.strip(),) if traits.contradiction.strip() else (),
            pilot_portrayal=traits,
        )

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
        *,
        pilot_origin: PilotDossierOrigin | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            actual = self._actor(c, scene, actor)
            if actual.controller != viewer.user_id:
                self.store.administrator(viewer)
            history = self._records(load_state(c, self.store.campaign_id), actor)
            if expected_version != len(history):
                raise WorkflowError("STALE_DOSSIER: use the exact current dossier revision.")
            previous = (
                history[-1] if history and history[-1].controller == actual.controller else None
            )
            portrayal = profile
            proposed_state = state
            projected_personnel = personnel or Personnel()
            if pilot_origin is not None:
                approved = self._approved_pilot(c, viewer, actual, pilot_origin)
                generated = self._pilot_profile(approved)
                if previous:
                    portrayal = previous.profile.model_copy(
                        update={
                            "pilot_portrayal": previous.profile.pilot_portrayal
                            or generated.pilot_portrayal
                        }
                    )
                    proposed_state = previous.state
                    projected_personnel = previous.personnel
                else:
                    portrayal = generated
            elif previous and portrayal.character_setup is None:
                portrayal = portrayal.model_copy(
                    update={"character_setup": previous.profile.character_setup}
                )
            continuity = previous.state.continuity if previous else ()
            if state.continuity and state.continuity != continuity:
                raise WorkflowError(
                    "CONTINUITY_REVIEW: save changes through owned continuity review."
                )
            proposed_state = proposed_state.model_copy(update={"continuity": continuity})
            self._validate_state(c, scene, actor, proposed_state)
            proposal = DossierProposal(
                id="dossier-proposal:" + str(uuid4()),
                scene_id=scene,
                actor=actor,
                controller=actual.controller,
                proposer=viewer.user_id,
                expected_version=expected_version,
                profile=portrayal,
                state=proposed_state,
                personnel=projected_personnel,
                binding=self._binding(c, scene, actor),
                pilot_origin=pilot_origin,
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
                **({"pilot_origin": pilot_origin.model_dump(mode="json")} if pilot_origin else {}),
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
            used_pilots = self._used_pilots(canon)
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
                    current = (
                        proposal.pilot_origin not in used_pilots
                        and proposal.binding == self._binding(c, scene, proposal.actor)
                    )
                except WorkflowError:
                    # Recovery metadata must remain usable when an old source needs retirement.
                    current = False
                result.append(
                    {
                        "id": identity,
                        "actor": proposal.actor.model_dump(mode="json"),
                        "controller": proposal.controller,
                        "expected_version": proposal.expected_version,
                        **({"generated_pilot": True} if proposal.pilot_origin else {}),
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
            if proposal.pilot_origin is not None:
                self._approved_pilot(c, viewer, actual, proposal.pilot_origin)
            canon = load_state(c, self.store.campaign_id)
            history = self._records(canon, proposal.actor)
            return self._commit(c, viewer, key, canon, proposal, history[-1] if history else None)

        return self.store._write(
            viewer,
            key,
            "director.dossier_confirm",
            {"scene": scene, "proposal": identity},
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def _commit(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        canon: GameState,
        proposal: DossierProposal,
        head: DossierRecord | None,
    ) -> dict[str, Any]:
        event = str(uuid4())
        record = DossierRecord(
            id="dossier:" + str(uuid4()),
            actor=proposal.actor,
            controller=viewer.user_id,
            version=head.version + 1 if head else 1,
            supersedes=head.id if head else None,
            profile=proposal.profile,
            state=proposal.state,
            personnel=proposal.personnel,
            scene_id=proposal.scene_id,
            proposal_id=proposal.id,
            source_event=event,
            pilot_origin=proposal.pilot_origin
            or (head.pilot_origin if head and head.controller == viewer.user_id else None),
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

    @staticmethod
    def _scope_handler_portrayal(
        record: DossierRecord, sheet_setup: CharacterSetup | None
    ) -> DossierRecord:
        state = record.state.model_copy(
            update={
                name: tuple(item for item in getattr(record.state, name) if item.knowledge_refs)
                for name in (
                    "pressures",
                    "promises",
                    "beliefs",
                    "obligations",
                    "experiences",
                    "relationships",
                )
            }
        )
        return record.model_copy(
            update={
                "profile": DossierProfile(character_setup=sheet_setup),
                "state": state,
                "personnel": Personnel(),
            }
        )

    def _role_packet(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        *,
        subjects: tuple[ActorRef, ...] | None = None,
        omit_stale_portrayal: bool = False,
        activity_pilot: bool = False,
    ) -> DossierPacket:
        """Internal projection; caller separately establishes actual GM/controller access."""
        actual = self._actor(c, scene, actor)
        canon = load_state(c, self.store.campaign_id)
        history = self._records(canon, actor)
        head = history[-1] if history else None
        entitled = head is not None and head.controller == actual.controller
        context = self._context(c, scene, actor)
        portrayal = head if entitled else None
        profile_visible = portrayal is not None
        if portrayal is not None and actor.kind == "handler":
            # A structured setup confirmed on the private sheet is campaign-wide.
            # Sheet memory writes can copy a raw scene profile into a new revision,
            # so use the original dossier confirmation to identify its scene.
            origin = None
            sheet_setup = None
            for record in reversed(history):
                if record.controller != actual.controller:
                    break
                if origin is None and record.proposal_id.startswith("dossier-proposal:"):
                    origin = record
                if (
                    sheet_setup is None
                    and not record.scene_id
                    and record.proposal_id.startswith("sheet-dossier:")
                    and record.profile.character_setup is not None
                ):
                    sheet_setup = record.profile.character_setup
                if origin is not None and sheet_setup is not None:
                    break
            portrayal_scene = origin.scene_id if origin is not None else portrayal.scene_id
            if portrayal_scene != scene:
                portrayal = self._scope_handler_portrayal(portrayal, sheet_setup)
                profile_visible = sheet_setup is not None
        continuity: tuple[DossierContinuity, ...] = ()
        if portrayal is not None and portrayal.state.continuity:
            continuity = self._visible_continuity(
                c, scene, actor, actual.controller, portrayal.state.continuity
            )
            portrayal = portrayal.model_copy(
                update={"state": portrayal.state.model_copy(update={"continuity": continuity})}
            )
        if portrayal is not None and (activity_pilot or actor.kind == "handler"):
            memory = self._pilot_memory(
                c, scene, actor, actual.controller, context, portrayal.state
            )
            if actor.kind == "handler" and subjects is not None:
                memory = memory.model_copy(
                    update={
                        "terms": tuple(term for term in memory.terms if term.subject in subjects)
                    }
                )
            portrayal = portrayal.model_copy(update={"state": memory})
        elif portrayal is not None:
            seen = self._reference_ids(context)
            visible = tuple(
                entry for entry in portrayal.state.experiences if set(entry.knowledge_refs) <= seen
            )
            if visible != portrayal.state.experiences:
                portrayal = portrayal.model_copy(
                    update={"state": portrayal.state.model_copy(update={"experiences": visible})}
                )
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
            **(
                {"continuity": [entry.model_dump(mode="json") for entry in continuity]}
                if portrayal is None and continuity
                else {}
            ),
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
            profile=portrayal.profile if portrayal and profile_visible else None,
            state=(
                portrayal.state
                if portrayal
                else DossierState(continuity=continuity)
                if continuity
                else None
            ),
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
