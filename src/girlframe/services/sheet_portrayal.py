"""Owner revisions of the existing portrayal dossier from an Activity sheet."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.contracts import Contract
from girlframe.ai.director_dossiers import (
    DossierPerspective,
    DossierProfile,
    DossierProposal,
    DossierRecord,
    DossierState,
    Personnel,
)
from girlframe.database import tables as t
from girlframe.engine.campaign_opening import PlannedAIPilot
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import owned_refs
from girlframe.engine.m3_handler_character import PROFILES
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.pilot_portrayal import PilotPortrayal
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
    kind: Literal["portrayal", "experience"]


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
                pending_portrayal = draft.proposal.profile.pilot_portrayal if draft else None
                sheets.append(
                    {
                        "actor": actor.model_dump(mode="json"),
                        "token": actor.token,
                        "label": actual.label,
                        "version": version,
                        "approved": approved.version if approved else None,
                        "portrayal": portrayal.model_dump(mode="json") if portrayal else None,
                        "pending": {
                            "id": draft.proposal.id,
                            "kind": draft.kind,
                            "scene": draft.proposal.scene_id,
                            "stale": draft.proposal.expected_version != version,
                            "portrayal": pending_portrayal.model_dump(mode="json")
                            if draft.kind == "portrayal" and pending_portrayal
                            else None,
                        }
                        if pending and draft
                        else None,
                    }
                )
            return {"sheets": sheets}

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
            packet = self.dossiers._role_packet(c, scene, actor, omit_stale_portrayal=True)
            data = packet.model_dump(mode="json")
            draft = self._latest(c, viewer, actor)
            if (
                draft
                and draft.kind == "experience"
                and draft.proposal.scene_id == scene
                and draft.proposal.expected_version == packet.dossier_version
                and draft.proposal.binding == self.dossiers._binding(c, scene, actor)
            ):
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
        scene: str = "",
        experience: DossierPerspective | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._own(c, viewer, load_state(c, self.store.campaign_id), actor)
            if experience is not None:
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
            if experience is not None:
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
                if experience
                else (head.id if head else ""),
            )
            draft = SheetDraft(
                proposal=proposal,
                kind="experience" if experience else "portrayal",
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
            if draft.kind == "experience":
                scene = proposal.scene_id
                self.dossiers._scope(c, viewer, scene)
                if proposal.binding != self.dossiers._binding(c, scene, actor):
                    raise WorkflowError("STALE_DOSSIER: review the current scene and source.")
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
