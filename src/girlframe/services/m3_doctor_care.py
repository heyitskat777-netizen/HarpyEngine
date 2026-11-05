"""Actual patient-attested care for Cute Nurse and Metal Angel, never invented dialogue."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_doctor import owned
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class CareService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Care]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        value = next(
            (x for x in rules.values(state, "doctor_care", rules.Care) if x.id == identity), None
        )
        if value is None or viewer.user_id not in (
            int(value.doctor.entity),
            value.patient_controller,
        ):
            raise WorkflowError("This actual care belongs to its original people")
        prove(self.game, c, value)
        return state, value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value = self._source(c, viewer, identity)
            return dict(
                id=identity,
                revision=state.revision,
                care=value.model_dump(mode="json"),
                can_confirm=value.phase == "proposal"
                and viewer.user_id == value.patient_controller,
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        patient: ActorRef,
        account: str,
        *,
        angel: bool = False,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if state.revision != revision or not account.strip() or self.game.pending_actions(c):
                raise WorkflowError("Refresh the actual care scene before declaring care")
            if not owned(self.game, c, state, actor, rules.ANGEL if angel else rules.NURSE):
                raise WorkflowError("Acquire the actual medical Requisition first")
            if actor == patient or patient.kind != "pilot":
                raise WorkflowError("Record care for another actual original Pilot")
            cast = _cast(self.game, c, state, channel)
            target = resolve(state, patient, profiles(c, self.store.campaign_id))
            giver = resolve(state, actor, profiles(c, self.store.campaign_id))
            if not {actor, patient} <= {x.actor for x in cast.roles} or (
                giver.cell is not None and target.cell is not None and giver.cell != target.cell
            ):
                raise WorkflowError(
                    "Actual care needs both original bodies together in the source scene"
                )
            judge, _ = MedicalService(self.store)._handler(c)
            identity, event = str(uuid4()), str(uuid4())
            value = rules.Care(
                id=identity,
                doctor=actor,
                frame=rules.frame_id(state, actor),
                patient=patient,
                patient_controller=target.controller,
                judge=judge,
                source_event=event,
                account=account,
                angel=angel,
            )
            rules.put(state, "doctor_care", value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.doctor_care_proposed",
                state,
                event_id=event,
                care=identity,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_care_proposed",
            dict(
                revision=revision,
                channel=channel,
                patient=patient.model_dump(mode="json"),
                account=account,
                angel=angel,
            ),
            change,
            auto_audit=False,
            authorize=access,
        )

    def confirm(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks", director_response=True)
            self._source(c, viewer, identity)

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._source(c, viewer, identity)
            if (
                state.revision != revision
                or value.phase != "proposal"
                or not account.strip()
                or viewer.user_id != value.patient_controller
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Only the original patient confirms actual performed care")
            if not owned(
                self.game, c, state, value.doctor, rules.ANGEL if value.angel else rules.NURSE
            ):
                raise WorkflowError("Recover the actual care provider and current source ability")
            resolve(state, value.patient, profiles(c, self.store.campaign_id))
            if rules.frame_id(state, value.doctor) != value.frame:
                raise WorkflowError("This care belongs to the original Doctor Frame")
            event = str(uuid4())
            state = rules.nurse(state, value.doctor, value.patient, event)
            value = value.model_copy(
                update={"phase": "active" if value.angel else "complete", "care_event": event}
            )
            rules.put(state, "doctor_care", value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.doctor_care_confirmed",
                state,
                event_id=event,
                care=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_care_confirmed",
            dict(id=identity, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=access,
        )

    def recover(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "off_duty", director_response=True)
            self._source(c, viewer, identity)

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._source(c, viewer, identity)
            if (
                state.revision != revision
                or value.phase != "recovery"
                or not account.strip()
                or viewer.user_id in value.confirmations
            ):
                raise WorkflowError("Confirm your own actual next Off-Duty care once")
            from girlframe.engine.m3_off_duty import Period

            body = c.scalar(
                sa.select(t.m3["m3_off_duty"].c.body_json).where(
                    t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                    t.m3["m3_off_duty"].c.id == value.period,
                )
            )
            period = Period.model_validate_json(body) if body else None
            if period is None or period.phase != "active":
                raise WorkflowError("Use the actual active next Off-Duty care period")
            if not owned(self.game, c, state, value.doctor, rules.ANGEL):
                raise WorkflowError("The actual source Doctor must still provide this care")
            event = str(uuid4())
            confirmations = (*value.confirmations, viewer.user_id)
            complete = set(confirmations) == {int(value.doctor.entity), value.patient_controller}
            if complete:
                work = t.m3["m3_required_work"]
                for body_json in c.scalars(
                    sa.select(work.c.body_json).where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.kind == "defeat_medical_wake",
                        work.c.state == "pending",
                        work.c.subject_id == value.patient.entity,
                    )
                ):
                    pending = json.loads(body_json)
                    if (
                        pending.get("owner") == value.patient.model_dump(mode="json")
                        and pending.get("stage") != "choose_play"
                    ):
                        raise WorkflowError(
                            "Finish the original medical waking before completing this recovery"
                        )
                patient = state.sheets.get(value.patient.entity)
                if patient is None or patient.character_id != value.patient.incarnation:
                    raise WorkflowError("Care cannot resurrect an already ended original person")
                placement = next((x for x in state.placements if x.actor == value.patient), None)
                if placement and placement.subsumed:
                    raise WorkflowError(
                        "Resolve actual locked-cockpit extraction before biological recovery"
                    )
                patient.medical_state = "fit"
                patient.revision += 1
                if placement:
                    state.placements = [
                        x.model_copy(
                            update=dict(
                                incapacitated=False,
                                vitals_active=True,
                                source_event=event,
                                account=account,
                            )
                        )
                        if x.actor == value.patient
                        else x
                        for x in state.placements
                    ]
                from girlframe.engine.m3_actor_bonds import clear_helpless, is_helpless

                if is_helpless(state, value.patient):
                    state = clear_helpless(state, value.patient, event)
            value = value.model_copy(
                update=dict(
                    confirmations=confirmations,
                    phase="complete" if complete else "recovery",
                    completion_event=event if complete else None,
                )
            )
            rules.put(state, "doctor_care", value)
            self.game.event(
                c, viewer.user_id, key, "m3.doctor_care_recovery", state, event_id=event
            )
            return dict(id=identity, phase=value.phase)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_care_recovery",
            dict(id=identity, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=access,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                phase=x.phase,
                actionable=(x.phase == "proposal" and viewer.user_id == x.patient_controller)
                or (x.phase == "recovery" and viewer.user_id not in x.confirmations),
            )
            for x in rules.values(state, "doctor_care", rules.Care)
            if x.phase in ("proposal", "active", "recovery")
            and viewer.user_id in (int(x.doctor.entity), x.patient_controller)
        ]


def prove(game: "GameService", c: Connection, value: rules.Care) -> None:
    history = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    source = GameState.model_validate_json(history) if history else None
    original = (
        next((x for x in rules.values(source, "doctor_care", rules.Care) if x.id == value.id), None)
        if source
        else None
    )
    if original is None or (original.doctor, original.frame, original.patient, original.angel) != (
        value.doctor,
        value.frame,
        value.patient,
        value.angel,
    ):
        raise WorkflowError("Recover the actual original care declaration and source bodies")
    if value.care_event:
        confirmed = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.care_event,
            )
        )
        proof = GameState.model_validate_json(confirmed) if confirmed else None
        if proof is None or not any(
            x.id == value.id
            and x.care_event == value.care_event
            and x.phase in ("active", "complete")
            for x in rules.values(proof, "doctor_care", rules.Care)
        ):
            raise WorkflowError("Recover the actual patient's performed-care confirmation")
