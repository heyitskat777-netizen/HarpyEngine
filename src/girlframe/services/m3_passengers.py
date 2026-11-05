"""Source-owned passenger exit, actual Frame consent and physical extraction."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_passengers as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import frame_position, owned_refs, resolve
from girlframe.engine.m3_passenger_state import Passenger
from girlframe.engine.m3_physical import cockpit_lock
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_mockingbird_communion import CallService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class PassengerService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _source(self, c: Connection, state: GameState, identity: str) -> Passenger:
        value = next((x for x in state.passengers if x.id == identity), None)
        if value is None:
            raise WorkflowError("Recover the original actual Call passenger")
        session, _ = CallService(self.game)._source(c, state, identity)
        if (
            session.passenger != identity
            or session.guest != value.actor
            or session.actor != value.carrier
        ):
            raise WorkflowError(
                "SOURCE_PASSENGER_MISSING: actual paired source invitation required"
            )
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        boarded = (
            next((x for x in original.passengers if x.id == value.id), None) if original else None
        )
        if (
            boarded is None
            or any(
                getattr(boarded, key) != getattr(value, key)
                for key in (
                    "id",
                    "actor",
                    "controller",
                    "carrier",
                    "frame",
                    "source_action",
                    "step",
                    "source_event",
                    "position_sha256",
                    "carrier_sha256",
                    "accepted_event",
                )
            )
            or original is None
            or not any(
                x.get("kind") == "call_guest_boarded"
                and x.get("passenger") == value.id
                and x.get("event") == value.source_event
                for x in original.facts
            )
        ):
            raise WorkflowError(
                "Prove the original actual guest, paired boarding and exact Frame instance"
            )
        return value

    def _view(
        self, c: Connection, viewer: GuildViewer, state: GameState, value: Passenger
    ) -> dict[str, Any]:
        bound = profiles(c, self.store.campaign_id)
        try:
            voice = rules.frame_controller(state, value)
        except ValueError:
            voice = None
        cell = frame_position(state, value.carrier, value.frame, fallback=value.cell)
        actors = []
        for ref in owned_refs(state, viewer.user_id, bound):
            try:
                actual = resolve(state, ref, bound, require_current_profile=False)
            except ValueError:
                continue
            if actual.offstage_source:
                continue
            at_cockpit = actual.cell is not None and cell is not None and actual.cell == cell
            own_cockpit = (
                ref == value.carrier
                and actual.inside_frame is True
                and actual.occupied_frame_instance in (None, value.frame)
            )
            if rules.same_body(state, ref, value.actor) or at_cockpit or own_cockpit:
                actors.append(
                    dict(ref=ref.model_dump(mode="json"), token=ref.token, label=actual.label)
                )
        if (
            not actors
            and voice != viewer.user_id
            and value.controller != viewer.user_id
            and value.medical_judge != viewer.user_id
        ):
            raise WorkflowError(
                "Only actual source body/Frame humans and present extractors review this body"
            )
        boarded = rules.passenger_view(state, value.actor) == value
        session, _ = CallService(self.game)._source(c, state, value.id)
        return dict(
            id=value.id,
            revision=value.revision,
            state=value.state,
            boarded=boarded,
            subsumed=value.subsumed,
            vitals_active=value.vitals_active,
            actors=actors,
            patient=value.actor.model_dump(mode="json"),
            patient_owner=value.controller == viewer.user_id,
            can_consent=boarded
            and voice == viewer.user_id
            and cockpit_lock(state, value.carrier, value.frame) is not None,
            can_move=boarded and session.phase == "complete",
            frame_voice_required=voice is None,
            consent=bool(cockpit_lock(state, value.carrier, value.frame)),
            cell=cell,
            can_request_medical=value.state == "left"
            and not value.vitals_active
            and value.controller == viewer.user_id,
            can_review_medical=value.state == "left"
            and value.medical_proposal_event is not None
            and value.medical_recovery_event is None
            and value.medical_judge == viewer.user_id,
            medical_account=value.medical_account
            if viewer.user_id in (value.controller, value.medical_judge)
            else "",
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return self._view(c, viewer, state, self._source(c, state, identity))

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        operation: str,
        account: str,
        *,
        actor: ActorRef | None = None,
        allowed: bool | None = None,
    ) -> dict[str, Any]:
        def write(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._source(c, state, identity)
            view = self._view(c, viewer, state, value)
            if value.revision != revision or not account.strip() or len(account) > 1200:
                raise WorkflowError("Reopen this actual original body's current physical controls")
            event = str(uuid4())
            try:
                if operation == "consent":
                    if not view["can_consent"] or type(allowed) is not bool or actor is not None:
                        raise WorkflowError(
                            "Only the actual current Frame voice owns this response"
                        )
                    state = rules.consent(state, identity, viewer.user_id, allowed, event, account)
                elif operation in ("leave", "extract"):
                    if (
                        not view["can_move"]
                        or actor is None
                        or allowed is not None
                        or not any(
                            x["ref"] == actor.model_dump(mode="json") for x in view["actors"]
                        )
                    ):
                        raise WorkflowError(
                            "Choose your actual present body for this completed source guest"
                        )
                    state = rules.leave(
                        state,
                        profiles(c, self.store.campaign_id),
                        identity,
                        actor,
                        event,
                        account,
                        extraction=operation == "extract",
                    )
                elif operation == "medical_request":
                    if not view["can_request_medical"] or actor is not None or allowed is not None:
                        raise WorkflowError(
                            "Only the actual living original patient reports completed medical help"
                        )
                    resolve(
                        state,
                        value.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    from girlframe.services.m3_medical import MedicalService

                    judge, appointment = MedicalService(self.store)._handler(c)
                    state.passengers = [
                        x.model_copy(
                            update=dict(
                                medical_proposal_event=event,
                                medical_account=account,
                                medical_judge=judge,
                                medical_appointment=appointment,
                                revision=x.revision + 1,
                            )
                        )
                        if x.id == identity
                        else x
                        for x in state.passengers
                    ]
                elif operation == "medical_confirm":
                    if not view["can_review_medical"] or actor is not None or allowed is not None:
                        raise WorkflowError(
                            "The actual source medical reviewer confirms completed help"
                        )
                    from girlframe.services.m3_medical import MedicalService

                    judge, appointment = MedicalService(self.store)._handler(c)
                    if judge != viewer.user_id or appointment != value.medical_appointment:
                        raise WorkflowError("Recover the actual factual medical review appointment")
                    resolve(
                        state,
                        value.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    )
                    if value.actor.kind == "pilot":
                        state.placements = [
                            x.model_copy(
                                update=dict(
                                    vitals_active=True,
                                    incapacitated=False,
                                    source_event=event,
                                    account=account,
                                )
                            )
                            if x.actor == value.actor
                            else x
                            for x in state.placements
                        ]
                    elif value.actor.kind == "external_pilot":
                        from girlframe.engine.m3_harpy_defeat import update

                        state = update(
                            state, value.actor, vitals_active=True, physical_source_event=event
                        )
                    state.passengers = [
                        x.model_copy(
                            update=dict(
                                vitals_active=True,
                                medical_recovery_event=event,
                                revision=x.revision + 1,
                            )
                        )
                        if x.id == identity
                        else x
                        for x in state.passengers
                    ]
                    if state.external_poses or state.leviathan_arrivals:
                        from girlframe.engine.m3_leviathan_arrival import (
                            record_existing_body_position,
                        )

                        state = record_existing_body_position(
                            state, value.actor, value.cell, event, account
                        )
                else:
                    raise WorkflowError("Use an actual source physical operation")
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.passenger_physical",
                state,
                event_id=event,
                passenger_id=identity,
                operation=operation,
                acting_ref=actor.model_dump(mode="json") if actor else None,
            )
            return self._view(
                c, viewer, state, next(x for x in state.passengers if x.id == identity)
            )

        return self.store._write(
            viewer,
            key,
            "m3.passenger_physical",
            dict(
                id=identity,
                revision=revision,
                operation=operation,
                account=account,
                actor=actor.model_dump(mode="json") if actor else None,
                allowed=allowed,
            ),
            write,
            auto_audit=False,
            authorize=lambda c: Access(self.store).authorize(
                c, viewer, "plays", director_response=True
            ),
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in state.passengers:
            if not (
                value.state == "boarded"
                and rules.passenger_view(state, value.actor) is not None
                or value.state == "left"
                and not value.vitals_active
            ):
                continue
            try:
                view = self._view(c, viewer, state, self._source(c, state, value.id))
            except (WorkflowError, ValueError):
                continue
            result.append(
                dict(
                    id=value.id,
                    state="subsumed" if value.subsumed else "boarded",
                    actionable=bool(
                        view["can_consent"]
                        or view["can_move"]
                        or view["can_request_medical"]
                        or view["can_review_medical"]
                    ),
                )
            )
        return result
