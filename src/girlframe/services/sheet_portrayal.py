"""Owner revisions of the existing portrayal dossier from an Activity sheet."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import Field
from sqlalchemy import Connection

from girlframe.ai.contracts import Contract
from girlframe.ai.director_dossiers import (
    CharacterSetup,
    DossierContinuityEdit,
    DossierMemoryEdit,
    DossierMemorySource,
    DossierPerspective,
    DossierPressure,
    DossierProfile,
    DossierProposal,
    DossierRecord,
    DossierState,
    Personnel,
    RelationshipPerspective,
    RelationshipTerm,
)
from girlframe.database import tables as t
from girlframe.engine.campaign_opening import PlannedAIPilot
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import owned_refs
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.pilot_portrayal import PilotPortrayal
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.campaign_difficulty import opening
from girlframe.services.director_closeout import handler_reports
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "director.sheet_portrayal_draft"


class SheetDraft(Contract):
    proposal: DossierProposal
    kind: Literal["portrayal", "character_setup", "experience", "memory", "continuity"]
    memory: DossierMemoryEdit | None = Field(default=None, exclude_if=lambda value: value is None)
    continuity: tuple[DossierContinuityEdit, ...] = Field(
        default=(), max_length=3, exclude_if=lambda value: not value
    )


class SheetPortrayalService:
    def __init__(self, dossiers: DirectorDossierService):
        self.dossiers, self.store, self.game = dossiers, dossiers.store, dossiers.game

    def _own(
        self, c: Connection, viewer: GuildViewer, canon: GameState, actor: ActorRef
    ) -> ActorView:
        if actor.kind not in ("pilot", "npc", "handler"):
            raise WorkflowError("PORTRAYAL_ACTOR: select an owned Pilot, NPC or Handler sheet.")
        if actor.kind == "handler" and actor != active_handler(canon):
            raise WorkflowError("PORTRAYAL_ACTOR: select the active Handler's sheet.")
        return self.dossiers.actors._actor(c, viewer, canon, actor)

    def _latest(self, c: Connection, viewer: GuildViewer, actor: ActorRef) -> SheetDraft | None:
        body = c.scalar(
            sa.select(t.events.c.payload_json)
            .where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == EVENT,
                t.events.c.actor_id == str(viewer.user_id),
                sa.func.json_extract(t.events.c.payload_json, "$.actor_token") == actor.token,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        return (
            SheetDraft.model_validate_json(json.dumps(json.loads(body)["draft"])) if body else None
        )

    def _generated_pilot(self, c: Connection, head: DossierRecord) -> PlannedAIPilot | None:
        origin = head.pilot_origin
        if origin:
            record = opening(c, self.store.campaign_id)
            if record and record.seats and record.plan == origin.plan:
                for pilot in record.seats.ai_pilots:
                    if pilot.callsign == origin.callsign:
                        return pilot
        return None

    def _portrayal(self, c: Connection, head: DossierRecord | None) -> PilotPortrayal | None:
        if head is None or head.profile.pilot_portrayal is not None:
            return head.profile.pilot_portrayal if head else None
        if head.version == 1 and (pilot := self._generated_pilot(c, head)) and pilot.portrayal:
            return pilot.portrayal
        profile = head.profile
        return PilotPortrayal(
            voice=profile.voice,
            approach=profile.behavior,
            pressure=profile.reaction_tendencies[0] if profile.reaction_tendencies else "",
            value=profile.values[0] if profile.values else "",
            fear=profile.fears[0] if profile.fears else "",
            contradiction=profile.contradictions[0] if profile.contradictions else "",
        )

    def _edit_profile(
        self,
        c: Connection,
        head: DossierRecord | None,
        profile: DossierProfile,
        portrayal: PilotPortrayal,
    ) -> DossierProfile:
        background = profile.background
        if head and (pilot := self._generated_pilot(c, head)):
            if background == self.dossiers._pilot_profile(pilot).background:
                background = pilot.concept.strip()

        previous = profile.pilot_portrayal

        def replace_first(value: str, prior: tuple[str, ...], old: str | None) -> tuple[str, ...]:
            rest = prior[1:] if old is None or (prior and prior[0] == old) else prior
            return (value, *rest) if value and len(rest) < 10 else rest

        return profile.model_copy(
            update={
                "pilot_portrayal": portrayal,
                "background": background,
                "voice": portrayal.voice,
                "behavior": portrayal.approach,
                "reaction_tendencies": replace_first(
                    portrayal.pressure,
                    profile.reaction_tendencies,
                    previous.pressure if previous else None,
                ),
                "values": replace_first(
                    portrayal.value, profile.values, previous.value if previous else None
                ),
                "fears": replace_first(
                    portrayal.fear, profile.fears, previous.fear if previous else None
                ),
                "contradictions": replace_first(
                    portrayal.contradiction,
                    profile.contradictions,
                    previous.contradiction if previous else None,
                ),
            }
        )

    @staticmethod
    def _edit_pressure(
        state: DossierState,
        memory: DossierMemoryEdit,
        refs: tuple[str, ...],
        memory_sources: tuple[DossierMemorySource, ...],
    ) -> DossierState:
        plan = memory.pressure
        assert plan is not None
        pressures = state.pressures
        previous = next(
            (
                item
                for item in pressures
                if isinstance(item, DossierPressure) and item.pressure_id == memory.pressure_id
            ),
            None,
        )
        if memory.pressure_id is not None and previous is None:
            raise WorkflowError("PRESSURE_UNAVAILABLE: choose a pressure on this actor's sheet.")
        if previous is None:
            if plan.status != "open":
                raise WorkflowError("PRESSURE_UNAVAILABLE: start with an open pressure.")
            if plan.consequence and not refs:
                raise WorkflowError("PRESSURE_EVIDENCE: cite a witnessed source for a consequence.")
            if len(pressures) >= 10:
                closed = next(
                    (
                        item
                        for item in pressures
                        if isinstance(item, DossierPressure)
                        and item.pressure.status in ("resolved", "withdrawn")
                    ),
                    None,
                )
                if closed is None:
                    raise WorkflowError("PRESSURE_LIMIT: revise an existing pressure.")
                # Earlier approved dossier versions retain the completed pressure.
                pressures = tuple(item for item in pressures if item != closed)
        elif previous.pressure.status in ("resolved", "withdrawn"):
            raise WorkflowError("PRESSURE_FINAL: a finished pressure remains in history.")
        elif not set(refs) - set(previous.knowledge_refs):
            if plan != previous.pressure or memory.text != previous.text:
                raise WorkflowError(
                    "PRESSURE_EVIDENCE: cite a new witnessed source for the change."
                )
            raise WorkflowError("PRESSURE_NO_CHANGE: this plan is already on the sheet.")
        sources = tuple(dict.fromkeys((*(previous.knowledge_refs if previous else ()), *refs)))
        if len(sources) > 10:
            raise WorkflowError("PRESSURE_EVIDENCE_LIMIT: start a follow-on pressure.")
        entry = DossierPressure(
            pressure_id=previous.pressure_id if previous else str(uuid4()),
            text=memory.text,
            pressure=plan,
            knowledge_refs=sources,
            memory_sources=tuple(
                dict.fromkeys((*(previous.memory_sources if previous else ()), *memory_sources))
            ),
        )
        entries = (
            tuple(entry if item == previous else item for item in pressures)
            if previous
            else (*pressures, entry)
        )
        return state.model_copy(update={"pressures": entries})

    def _memory_allowed(self, c: Connection, scene: str, actor: ActorRef) -> bool:
        return actor.kind == "handler" or actor in self.dossiers.activity_pilots(c, scene)

    def _pressure_available(
        self,
        c: Connection,
        scene: str,
        actor: ActorRef,
        controller: int,
        state: DossierState,
        pressure_id: str,
        references: set[str],
    ) -> None:
        entry = next(
            (
                item
                for item in state.pressures
                if isinstance(item, DossierPressure) and item.pressure_id == pressure_id
            ),
            None,
        )
        if entry is None or not set(entry.knowledge_refs) <= (
            (references - {source.reference_id for source in entry.memory_sources})
            | self.dossiers._visible_memory_sources(
                c, scene, actor, controller, entry.memory_sources
            )
        ):
            raise WorkflowError("PRESSURE_UNAVAILABLE: recover its known sources.")

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.game.authorize(c, viewer, game=False)
            canon = load_state(c, self.store.campaign_id)
            sheets = []
            for actor in owned_refs(canon, viewer.user_id, profiles(c, self.store.campaign_id)):
                try:
                    actual = self._own(c, viewer, canon, actor)
                except WorkflowError:
                    continue
                history = self.dossiers._records(canon, actor)
                head = history[-1] if history else None
                approved = head if head and head.controller == viewer.user_id else None
                draft = self._latest(c, viewer, actor)
                pending = draft and not any(r.proposal_id == draft.proposal.id for r in history)
                version = head.version if head else 0
                portrayal = self._portrayal(c, approved)
                setup = approved.profile.character_setup if approved else None
                pending_portrayal = draft.proposal.profile.pilot_portrayal if draft else None
                pending_setup = (
                    draft.proposal.profile.character_setup
                    if pending and draft and draft.kind == "character_setup"
                    else None
                )
                sheets.append(
                    {
                        "actor": actor.model_dump(mode="json"),
                        "token": actor.token,
                        "label": actual.label,
                        "version": version,
                        "approved": approved.version if approved else None,
                        "portrayal": portrayal.model_dump(mode="json") if portrayal else None,
                        "character_setup": setup.model_dump(mode="json") if setup else None,
                        "pending": {
                            "id": draft.proposal.id,
                            "kind": draft.kind,
                            "scene": draft.proposal.scene_id,
                            "stale": draft.proposal.expected_version != version,
                            "portrayal": pending_portrayal.model_dump(mode="json")
                            if draft.kind == "portrayal" and pending_portrayal
                            else None,
                            "character_setup": pending_setup.model_dump(mode="json")
                            if pending_setup
                            else None,
                        }
                        if pending and draft
                        else None,
                    }
                )
            return {"sheets": sheets, "girl_types": GIRL_TYPES, "frame_types": FRAME_TYPES}

    def preview(self, viewer: GuildViewer, scene: str, token: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            c.exec_driver_sql("BEGIN")
            self.dossiers._scope(c, viewer, scene)
            canon = load_state(c, self.store.campaign_id)
            actor = next(
                (
                    r
                    for r in owned_refs(canon, viewer.user_id, profiles(c, self.store.campaign_id))
                    if r.token == token
                ),
                None,
            )
            if actor is None:
                raise WorkflowError("DOSSIER_NOT_OWNED: use your own actual actor.")
            self._own(c, viewer, canon, actor)
            guided_pilot = actor.kind == "npc" or (
                actor.kind == "pilot" and actor in self.dossiers.activity_pilots(c, scene)
            )
            packet = self.dossiers._role_packet(
                c, scene, actor, omit_stale_portrayal=True, activity_pilot=guided_pilot
            )
            data = packet.model_dump(mode="json")
            draft = self._latest(c, viewer, actor)
            row = self.dossiers.observer._scene(c, scene)
            data["continuity_subjects"] = [
                {"actor": item.ref.model_dump(mode="json"), "label": item.label}
                for item in self.dossiers.knowledge._actor_views(c, row)
                if item.ref != actor and self.dossiers._visible_identity(c, actor, item.ref)
            ]
            data["continuity_sources"] = [
                {"id": ref.id, "text": ref.text}
                for ref in self.dossiers._continuity_sources(
                    c, scene, actor, packet.context
                ).values()
            ]
            if self._memory_allowed(c, scene, actor):
                data["memory_subjects"] = data["continuity_subjects"]
            if (
                draft
                and draft.kind in ("experience", "memory", "continuity")
                and draft.proposal.scene_id == scene
                and draft.proposal.expected_version == packet.dossier_version
                and draft.proposal.binding == self.dossiers._binding(c, scene, actor)
            ):
                if draft.continuity:
                    data["pending_continuity"] = {
                        "id": draft.proposal.id,
                        "entries": [entry.model_dump(mode="json") for entry in draft.continuity],
                    }
                elif draft.memory is not None:
                    data["pending_memory"] = {
                        "id": draft.proposal.id,
                        "entry": draft.memory.model_dump(mode="json"),
                    }
                else:
                    data["pending_experience"] = {
                        "id": draft.proposal.id,
                        "entry": draft.proposal.state.experiences[-1].model_dump(mode="json"),
                    }
            if actor.kind == "handler":
                sheet = canon.handler_persona
                notes = HandlerCreationService(self.store).active_notes(c, canon, actor)
                if notes:
                    data["character_notes"] = notes.model_dump(mode="json")
                if sheet and sheet.playbook:
                    data["playbook_profile"] = PROFILES[sheet.playbook].model_dump(mode="json")
                data["closed_scene_reports"] = [
                    ref.model_dump(mode="json")
                    for ref in handler_reports(self.dossiers.context, c, actor)
                ]
            return data

    def draft(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        version: int,
        *,
        portrayal: PilotPortrayal | None = None,
        character_setup: CharacterSetup | None = None,
        scene: str = "",
        experience: DossierPerspective | None = None,
        memory: DossierMemoryEdit | None = None,
        continuity: tuple[DossierContinuityEdit, ...] | None = None,
    ) -> dict[str, Any]:
        edits = (portrayal, character_setup, experience, memory, continuity)
        if sum(value is not None for value in edits) != 1:
            raise WorkflowError("Choose one character setup, portrayal, or memory revision.")
        if continuity is not None and (
            not 1 <= len(continuity) <= 3
            or len(
                {
                    (item.kind, item.subject, item.text if item.kind == "commitment" else None)
                    for item in continuity
                }
            )
            != len(continuity)
        ):
            raise WorkflowError("CONTINUITY_UPDATE: choose one to three distinct updates.")

        kind: Literal["portrayal", "character_setup", "experience", "memory", "continuity"] = (
            "continuity"
            if continuity
            else "memory"
            if memory
            else "experience"
            if experience
            else "character_setup"
            if character_setup is not None
            else "portrayal"
        )
        scene_scoped = kind in ("experience", "memory", "continuity")

        def access(c: Connection) -> None:
            self._own(c, viewer, load_state(c, self.store.campaign_id), actor)
            if scene_scoped:
                self.dossiers._scope(c, viewer, scene)

        def operation(c: Connection) -> dict[str, Any]:
            canon = load_state(c, self.store.campaign_id)
            history = self.dossiers._records(canon, actor)
            head = history[-1] if history else None
            if version != len(history):
                raise WorkflowError("STALE_DOSSIER: reopen the current approved portrayal.")
            owned = head if head and head.controller == viewer.user_id else None
            profile = owned.profile if owned else DossierProfile(presence="recurring")
            state = owned.state if owned else DossierState()
            entry: DossierPerspective
            if continuity is not None:
                updates = self.dossiers._continuity_updates(c, scene, actor, continuity)
                continuity_entries = state.continuity
                for update in updates:
                    if update in continuity_entries:
                        raise WorkflowError("This continuity update is already on the sheet.")
                    continuity_entries = tuple(
                        entry
                        for entry in continuity_entries
                        if (entry.kind, entry.subject) != (update.kind, update.subject)
                        or update.kind == "commitment"
                    ) + (update,)
                state = state.model_copy(update={"continuity": continuity_entries[-12:]})
            elif memory is not None:
                if not self._memory_allowed(c, scene, actor):
                    raise WorkflowError(
                        "AI_PILOT_UNAVAILABLE: choose your approved AI Pilot or active Handler."
                    )
                context = self.dossiers._context(c, scene, actor)
                references = {
                    identity: ref.origin_reference or ref.id
                    for ref in context.references
                    for identity in (ref.id, ref.origin_reference)
                    if identity is not None
                }
                if not set(memory.knowledge_refs) <= references.keys():
                    raise WorkflowError("DOSSIER_UNKNOWN_SOURCE: cite an authorized memory.")
                refs = tuple(dict.fromkeys(references[ref] for ref in memory.knowledge_refs))
                if memory.pressure is not None:
                    if memory.pressure_id:
                        self._pressure_available(
                            c,
                            scene,
                            actor,
                            viewer.user_id,
                            state,
                            memory.pressure_id,
                            set(references),
                        )
                    state = self._edit_pressure(
                        state,
                        memory,
                        refs,
                        self.dossiers._personal_memory_sources(c, scene, context, refs),
                    )
                elif memory.subject is not None and memory.term is not None:
                    term = RelationshipTerm(
                        subject=memory.subject,
                        term=memory.term,
                        text=memory.text,
                        knowledge_refs=refs,
                        memory_sources=self.dossiers._personal_memory_sources(
                            c, scene, context, refs
                        ),
                    )
                    self.dossiers._validate_term(c, scene, actor, term)
                    prior = next(
                        (
                            entry
                            for entry in state.terms
                            if (entry.subject, entry.term) == (term.subject, term.term)
                        ),
                        None,
                    )
                    if prior is not None and not (set(refs) - set(prior.knowledge_refs)):
                        raise WorkflowError("TERM_SOURCE: cite new heard words to revise the term.")
                    state = state.model_copy(
                        update={
                            "terms": (
                                *(entry for entry in state.terms if entry != prior),
                                term,
                            )[-10:]
                        }
                    )
                elif memory.subject is not None:
                    if memory.subject == actor or not self.dossiers._visible_identity(
                        c, actor, memory.subject
                    ):
                        raise WorkflowError("DOSSIER_UNKNOWN_ACTOR: choose a known character.")
                    entries = tuple(
                        prior for prior in state.relationships if prior.subject != memory.subject
                    )
                    entry = RelationshipPerspective(
                        subject=memory.subject, text=memory.text, knowledge_refs=refs
                    )
                    if entry in state.relationships:
                        raise WorkflowError("This memory is already on the sheet.")
                    state = state.model_copy(update={"relationships": (*entries, entry)[-10:]})
                else:
                    entries = getattr(state, memory.kind)
                    entry = DossierPerspective(text=memory.text, knowledge_refs=refs)
                    if entry in entries:
                        raise WorkflowError("This memory is already on the sheet.")
                    if memory.kind == "pressures" and len(entries) >= 10:
                        raise WorkflowError("PRESSURE_LIMIT: revise an existing pressure.")
                    state = state.model_copy(update={memory.kind: (*entries, entry)[-10:]})
            elif experience is not None:
                context = self.dossiers._context(c, scene, actor)
                ref = next(
                    (r for r in context.references if (r.id,) == experience.knowledge_refs), None
                )
                if ref is None:
                    raise WorkflowError("DOSSIER_UNKNOWN_SOURCE: choose an actual known reference.")
                entry = experience.model_copy(
                    update={"knowledge_refs": (ref.origin_reference or ref.id,)}
                )
                if entry in state.experiences:
                    raise WorkflowError("This experience is already on the sheet.")
                state = state.model_copy(update={"experiences": (*state.experiences, entry)[-10:]})
            elif portrayal is not None and actor.kind != "handler":
                profile = self._edit_profile(c, owned, profile, portrayal)
            elif character_setup is not None:
                profile = profile.model_copy(update={"character_setup": character_setup})
            else:
                raise WorkflowError("Use the Handler's own notes to edit Handler portrayal.")
            proposal = DossierProposal(
                id="sheet-dossier:" + str(uuid4()),
                scene_id=scene,
                actor=actor,
                controller=viewer.user_id,
                proposer=viewer.user_id,
                expected_version=version,
                profile=profile,
                state=state,
                personnel=owned.personnel if owned else Personnel(),
                binding=self.dossiers._binding(c, scene, actor)
                if scene_scoped
                else (head.id if head else ""),
            )
            draft = SheetDraft(
                proposal=proposal,
                kind=kind,
                memory=memory,
                continuity=continuity or (),
            )
            self.store._audit(
                c,
                viewer.user_id,
                key,
                EVENT,
                {"actor_token": actor.token, "draft": draft.model_dump(mode="json")},
                ruleset_version="director-dossier-v1",
            )
            return {"id": proposal.id, "status": "awaiting_controller_confirmation"}

        return self.store._write(
            viewer,
            key,
            EVENT,
            {
                "actor": actor.model_dump(mode="json"),
                "version": version,
                "scene": scene,
                "portrayal": portrayal.model_dump(mode="json") if portrayal else None,
                "experience": experience.model_dump(mode="json") if experience else None,
                **(
                    {"character_setup": character_setup.model_dump(mode="json")}
                    if character_setup is not None
                    else {}
                ),
                **({"memory": memory.model_dump(mode="json")} if memory else {}),
                **(
                    {"continuity": [entry.model_dump(mode="json") for entry in continuity]}
                    if continuity
                    else {}
                ),
            },
            operation,
            authorize=access,
            auto_audit=False,
        )

    def confirm(
        self, viewer: GuildViewer, key: str, actor: ActorRef, identity: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._own(c, viewer, load_state(c, self.store.campaign_id), actor)

        def operation(c: Connection) -> dict[str, Any]:
            draft = self._latest(c, viewer, actor)
            if draft is None or draft.proposal.id != identity:
                raise WorkflowError("STALE_DOSSIER: confirm your latest sheet draft.")
            proposal = draft.proposal
            canon = load_state(c, self.store.campaign_id)
            history = self.dossiers._records(canon, actor)
            head = history[-1] if history else None
            if proposal.expected_version != len(history):
                raise WorkflowError("STALE_DOSSIER: reopen the current approved portrayal.")
            if draft.kind in ("experience", "memory", "continuity"):
                scene = proposal.scene_id
                self.dossiers._scope(c, viewer, scene)
                if proposal.binding != self.dossiers._binding(c, scene, actor) or (
                    draft.kind == "memory" and not self._memory_allowed(c, scene, actor)
                ):
                    raise WorkflowError("STALE_DOSSIER: review the current scene and source.")
                if draft.continuity:
                    self.dossiers._continuity_updates(c, scene, actor, draft.continuity)
                if draft.memory and draft.memory.pressure_id and head:
                    self._pressure_available(
                        c,
                        scene,
                        actor,
                        viewer.user_id,
                        head.state,
                        draft.memory.pressure_id,
                        self.dossiers._reference_ids(self.dossiers._context(c, scene, actor)),
                    )
            return self.dossiers._commit(c, viewer, key, canon, proposal, head)

        return self.store._write(
            viewer,
            key,
            "director.sheet_portrayal_confirm",
            {"actor": actor.model_dump(mode="json"), "draft": identity},
            operation,
            authorize=access,
            auto_audit=False,
        )
