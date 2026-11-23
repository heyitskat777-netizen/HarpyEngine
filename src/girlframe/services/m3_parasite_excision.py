"""Private consent and verified performance for an original partial infestation."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_parasite_infection as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _visible
from girlframe.services.m3_gorgon_play import GorgonPlayService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ExcisionService:
    def __init__(self, store: OnboardingStore):
        self.store = store
        self.game = GameService(store)

    def _source(
        self,
        c: Connection,
        state: GameState,
        case: rules.Infection,
    ) -> tuple[dict[str, Any], int]:
        action = self.game.action(c, case.action)
        original = GorgonPlayService(self.game).source(c, action)
        gm = original["procedural_gm"]
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == case.resolved,
            )
        )
        proof = rules.get(GameState.model_validate_json(raw), case.action) if raw else None
        sheet = state.sheets.get(case.girl.entity)
        if (
            original["kind"] != rules.PLAY
            or action["state"] != "complete"
            or original["target"] != case.girl.model_dump(mode="json")
            or original["actor"] != case.source.model_dump(mode="json")
            or proof is None
            or not proof.surgery_required
            or proof.roll != case.roll
            or proof.void_event != case.void_event
            or proof.resolved != case.resolved
            or sheet is None
            or sheet.character_id != case.girl.incarnation
        ):
            raise WorkflowError("Recover the original affected Girl and actual partial infestation")
        return action, gm

    def _options(
        self, c: Connection, state: GameState, case: rules.Infection, gm: int
    ) -> dict[str, tuple[str, ActorRef, str]]:
        bound = profiles(c, self.store.campaign_id)
        patient = resolve(state, case.girl, bound, require_current_profile=False)
        if not patient.alive or patient.cell is None or patient.offstage_source is not None:
            return {}
        options: dict[str, tuple[str, ActorRef, str]] = {}
        for scene in state.scene_casts:
            if not scene.open or not any(
                x.actor == case.girl and x.controller == patient.controller for x in scene.roles
            ):
                continue
            for role in scene.roles:
                if (
                    role.actor.kind != "npc"
                    or role.controller != gm
                    or not _visible(state, role.actor, patient.controller)
                ):
                    continue
                doctor = resolve(state, role.actor, bound, require_current_profile=False)
                if (
                    "doctor" in doctor.jobs
                    and doctor.alive
                    and doctor.cell == patient.cell
                    and doctor.controller == gm
                    and doctor.offstage_source is None
                ):
                    options[f"{scene.id}/{doctor.ref.token}"] = (
                        scene.id,
                        doctor.ref,
                        f"{doctor.label} · scene {scene.channel}",
                    )
        return options

    def _consented(self, c: Connection, case: rules.Infection) -> rules.Excision:
        plan = case.excision
        if plan is None or plan.performed_event:
            raise WorkflowError("Recover the original patient's live consent to this surgery")
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == plan.consent_event,
            )
        ).first()
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == plan.consent_event,
            )
        )
        proof = rules.get(GameState.model_validate_json(raw), case.action) if raw else None
        if (
            event is None
            or event.kind != "m3.parasite_excision_consent"
            or event.actor_id != case.girl.entity
            or proof is None
            or proof.excision != plan
        ):
            raise WorkflowError("Recover the original patient's actual recorded consent")
        return plan

    def tasks(self, c: Connection, viewer: GuildViewer, state: GameState) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        rows = []
        for case in rules.records(state):
            if not case.surgery_required or case.resolved is None:
                continue
            sheet = state.sheets.get(case.girl.entity)
            if sheet is None or sheet.character_id != case.girl.incarnation:
                continue
            action = self.game.action(c, case.action)
            gm = action["data"]["gorgon_play"]["procedural_gm"]
            patient = str(viewer.user_id) == case.girl.entity
            if not patient and (viewer.user_id != gm or case.excision is None):
                continue
            try:
                GorgonPlayService(self.game).authorize(c, viewer, action)
            except WorkflowError:
                continue
            self._source(c, state, case)
            rows.append(
                dict(
                    id=case.action,
                    revision=state.revision,
                    label="Choose or withdraw excision" if patient else "Verify performed excision",
                )
            )
        return rows

    def _view(
        self,
        c: Connection,
        viewer: GuildViewer,
        action_id: str,
    ) -> tuple[GameState, rules.Infection, dict[str, Any], int, bool]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        case = rules.get(state, action_id)
        if case is None or not case.surgery_required or case.resolved is None:
            raise WorkflowError("This private surgery is unavailable")
        action, gm = self._source(c, state, case)
        patient = str(viewer.user_id) == case.girl.entity
        if not patient and (viewer.user_id != gm or case.excision is None):
            raise WorkflowError("This private surgery is unavailable")
        GorgonPlayService(self.game).authorize(c, viewer, action)
        return state, case, action, gm, patient

    def get(self, viewer: GuildViewer, action_id: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, case, _, gm, patient = self._view(c, viewer, action_id)
            options = self._options(c, state, case, gm)
            return dict(
                revision=state.revision,
                patient=patient,
                consent=case.excision is not None,
                options={key: value[2] for key, value in options.items()} if patient else {},
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        action_id: str,
        revision: int,
        response: str,
        *,
        doctor: str | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            action = self.game.action(c, action_id)
            GorgonPlayService(self.game).authorize(c, viewer, action)

        def operation(c: Connection) -> dict[str, Any]:
            state, case, _, gm, patient = self._view(c, viewer, action_id)
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            if revision != state.revision:
                raise WorkflowError("STALE_EXCISION: reopen the actual private surgery")
            event = str(uuid4())
            if patient and response == "consent" and doctor and not account:
                chosen = self._options(c, state, case, gm).get(doctor)
                if chosen is None:
                    raise WorkflowError("Choose an actual local doctor in your current scene")
                scene, actor, _ = chosen
                updated = case.model_copy(
                    update=dict(
                        excision=rules.Excision(
                            scene=scene,
                            doctor=actor,
                            consent_event=event,
                        )
                    )
                )
            elif (
                patient and response == "withdraw" and case.excision and not doctor and not account
            ):
                updated = case.model_copy(update=dict(excision=None))
            elif (
                not patient
                and response == "performed"
                and not doctor
                and 0 < len(account.strip()) <= 1200
            ):
                plan = self._consented(c, case)
                if (plan.scene + "/" + plan.doctor.token) not in self._options(c, state, case, gm):
                    raise WorkflowError(
                        "Recover the actual present patient, doctor and consented scene"
                    )
                updated = case.model_copy(
                    update=dict(
                        surgery_required=False,
                        excision=plan.model_copy(
                            update=dict(performed_event=event, account=account.strip())
                        ),
                    )
                )
            else:
                raise WorkflowError("Use the original role's actual excision decision")
            rules.put(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                f"m3.parasite_excision_{response}",
                state,
                event_id=event,
                source_action=action_id,
            )
            return dict(id=action_id, excised=not updated.surgery_required)

        return self.store._write(
            viewer,
            key,
            "m3.parasite_excision_choice",
            dict(
                action=action_id,
                revision=revision,
                response=response,
                doctor=doctor,
                account=account,
            ),
            operation,
            authorize=authorize,
            auto_audit=False,
        )
