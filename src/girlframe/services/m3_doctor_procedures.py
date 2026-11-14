"""Actual Wings transfers and source-owned call/arrival, with no duplicate Assets."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_doctor import owned
from girlframe.services.m3_doctor_wings import graft
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def wings_thresholds(state: GameState, donor: ActorRef, asset: str) -> None:
    from girlframe.engine.m3_janus_storage import active
    from girlframe.engine.m3_supply_drop import current_asset, live

    # A graft gets a new ID on the Doctor. These sources still expire/return
    # against their original holder and ID, so do not strand their live hardware.
    if any(current_asset(state, use) == asset for use in live(state, donor)):
        raise WorkflowError(
            "SOURCE_PORT_REQUIRED: preserve the actual temporary Supply Drop before Wings transfer"
        )
    if any(
        loan.doctor == donor and loan.asset == asset and loan.phase == "borrowed"
        for loan in rules.values(state, "doctor_loan", rules.Loan)
    ):
        raise WorkflowError(
            "SOURCE_PORT_REQUIRED: return this actual borrowed Wings Asset before lending it again"
        )
    if any(item.asset_owner == donor and item.asset_id == asset for item in state.held_items):
        raise WorkflowError(
            "SOURCE_PORT_REQUIRED: preserve this actual held object's custody before Wings transfer"
        )
    if any(x.asset == asset for x in active(state, donor)):
        raise WorkflowError(
            "Unplug or remove stored Void before transferring its actual host Asset"
        )


class ProcedureService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def call_menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        """Discover actual joined Doctors without exposing their private resources."""
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "playbooks")
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            caller = current_ref(state, viewer.user_id)
            cast = _cast(self.game, c, state, channel)
            if caller not in {x.actor for x in cast.roles}:
                raise WorkflowError("Join the actual call scene first")
            try:
                rules.sheet(state, caller)
                native = True
            except ValueError:
                native = False
            doctors = []
            for role in cast.roles:
                actor = role.actor
                if actor == caller or actor.kind != "pilot":
                    continue
                if not owned(self.game, c, state, actor, rules.RAGGED):
                    continue
                actual = resolve(state, actor, profiles(c, self.store.campaign_id))
                doctors.append(
                    dict(ref=actor.model_dump(mode="json"), token=actor.token, label=actual.label)
                )
            return dict(
                revision=state.revision,
                caller=caller.model_dump(mode="json"),
                native=native,
                doctors=doctors,
            )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        counterpart: ActorRef,
        kind: str,
        account: str,
        *,
        asset: str | None = None,
        heat: int = 0,
        called_doctor: ActorRef | None = None,
        replace: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            initiator = current_ref(state, viewer.user_id)
            actor = called_doctor or initiator
            if called_doctor is not None and (
                kind != "ragged" or counterpart != initiator or actor.kind != "pilot"
            ):
                raise WorkflowError("Call only as the actual caller of Running Ragged")
            if (
                state.revision != revision
                or self.game.pending_actions(c)
                or not account.strip()
                or actor == counterpart
                or counterpart.kind != "pilot"
            ):
                raise WorkflowError("Refresh the two actual original people and performed trigger")
            rule = rules.WINGS if kind == "wings" else rules.RAGGED
            if kind not in ("wings", "ragged") or not owned(self.game, c, state, actor, rule):
                raise WorkflowError("Acquire the actual native source ability first")
            cast = _cast(self.game, c, state, channel)
            if not {actor, counterpart} <= {x.actor for x in cast.roles}:
                raise WorkflowError("Both actual original people must join the source scene")
            target = resolve(state, counterpart, profiles(c, self.store.campaign_id))
            if kind == "wings":
                if self.game.immediate_work(c, target.controller):
                    raise WorkflowError(
                        "Resolve the donor's immediate consequence before tearing off hardware"
                    )
                value = state.sheets[counterpart.entity]
                selected = next((x for x in value.assets if x.id == asset), None)
                own = rules.sheet(state, actor)
                if (
                    selected is None
                    or selected.family != "frame"
                    or not selected.damaged
                    or value.frame_scrapped
                    or heat < 2
                    or heat > own.heat
                ):
                    raise WorkflowError(
                        "Tear off an actual damaged Frame Asset and spend at least two Heat"
                    )
                graft(state, actor, selected, "doctor-loan:preview", replace)
                wings_thresholds(state, counterpart, selected.id)
                giver = resolve(state, actor, profiles(c, self.store.campaign_id))
                if giver.cell is not None and target.cell is not None and giver.cell != target.cell:
                    raise WorkflowError("The actual damaged Frame must be physically reachable")
            elif asset is not None or heat or replace is not None:
                raise WorkflowError(
                    "Running Ragged marks a real owned Tag instead of spending Heat"
                )
            identity, event = str(uuid4()), str(uuid4())
            request = rules.Procedure(
                id=identity,
                kind="wings" if kind == "wings" else "ragged",
                doctor=actor,
                frame=rules.frame_id(state, actor),
                counterpart=counterpart,
                controller=target.controller,
                source_event=event,
                account=account,
                channel=channel,
                asset=asset,
                heat=heat,
                replace=replace,
            )
            rules.put(state, "doctor_procedure", request)
            self.game.event(
                c, viewer.user_id, key, "m3.doctor_procedure_proposed", state, event_id=event
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_procedure_proposed",
            dict(
                revision=revision,
                channel=channel,
                counterpart=counterpart.model_dump(mode="json"),
                kind=kind,
                account=account,
                asset=asset,
                heat=heat,
            )
            | ({"replace": replace} if replace is not None else {})
            | ({"called_doctor": called_doctor.model_dump(mode="json")} if called_doctor else {}),
            change,
            auto_audit=False,
            authorize=access,
        )

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Procedure]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        value = next(
            (
                x
                for x in rules.values(state, "doctor_procedure", rules.Procedure)
                if x.id == identity
            ),
            None,
        )
        if value is None or viewer.user_id not in (int(value.doctor.entity), value.controller):
            raise WorkflowError("Open only your actual original Doctor procedure")
        return state, value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            protection = next(
                (
                    x
                    for x in rules.values(state, "doctor_protection", rules.Protection)
                    if x.id == identity and x.controller == viewer.user_id
                ),
                None,
            )
            if protection:
                self.game.authorize(c, viewer, game=False)
                return dict(
                    id=identity,
                    revision=state.revision,
                    procedure=dict(
                        kind="protection",
                        account="You are protecting Doctor. You may actually stop protecting.",
                    ),
                    tags=[],
                    can_confirm=protection.phase == "protecting",
                )
            state, value = self._source(c, viewer, identity)
            actor = current_ref(state, viewer.user_id)
            return dict(
                id=identity,
                revision=state.revision,
                procedure=value.model_dump(mode="json"),
                tags=[
                    dict(id=x.id, label=x.label)
                    for x in state.sheets[actor.entity].tags
                    if not x.marked
                ],
                can_confirm=value.phase == "proposal"
                and (value.kind == "ragged" or viewer.user_id == value.controller),
            )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
        tag: str | None = None,
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
                or self.game.pending_actions(c)
                or rules.frame_id(state, value.doctor) != value.frame
            ):
                raise WorkflowError("Reopen this actual original pending procedure")
            rule = rules.WINGS if value.kind == "wings" else rules.RAGGED
            if not owned(self.game, c, state, value.doctor, rule):
                raise WorkflowError("Recover the current original Doctor entitlement")
            event = str(uuid4())
            before_transfer = state.model_copy(deep=True)
            if value.kind == "wings":
                if viewer.user_id != value.controller or tag is not None:
                    raise WorkflowError(
                        "The actual donor confirms the performed tearing and transfer"
                    )
                donor = state.sheets[value.counterpart.entity]
                own = rules.sheet(state, value.doctor)
                asset = next(
                    (
                        x
                        for x in donor.assets
                        if x.id == value.asset and x.family == "frame" and x.damaged
                    ),
                    None,
                )
                if asset is None or donor.frame_scrapped or own.heat < value.heat:
                    raise WorkflowError(
                        "Refresh the actual damaged donor Asset, Heat and available slot"
                    )
                wings_thresholds(state, value.counterpart, asset.id)
                updated, received = graft(
                    state, value.doctor, asset, "doctor-loan:" + identity, value.replace
                )
                donor.assets = [x for x in donor.assets if x.id != asset.id]
                updated.heat -= value.heat
                state.sheets[value.doctor.entity] = updated
                donor.revision += 1
                rules.put(
                    state,
                    "doctor_loan",
                    rules.Loan(
                        id=identity,
                        doctor=value.doctor,
                        frame=value.frame,
                        donor=value.counterpart,
                        donor_frame=donor.frame_runtime.id
                        if donor.frame_runtime
                        else "initial:" + str(value.counterpart.incarnation),
                        asset=received.id,
                        source_asset_json=asset.model_dump_json(),
                        source_event=event,
                        account=account,
                    ),
                )
            else:
                actor = current_ref(state, viewer.user_id)
                marker = next(
                    (x for x in state.sheets[actor.entity].tags if x.id == tag and not x.marked),
                    None,
                )
                if marker is None:
                    raise WorkflowError(
                        "Either actual participant must mark their own unmarked Tag"
                    )
                doc = next((x for x in state.placements if x.actor == value.doctor), None)
                caller = resolve(state, value.counterpart, profiles(c, self.store.campaign_id))
                if (
                    doc is None
                    or doc.custody
                    or doc.subsumed
                    or doc.incapacitated
                    or doc.occupied_frame_owner is not None
                    or not doc.vitals_active
                ):
                    raise WorkflowError("Record the actual free Doctor body before this arrival")
                if any(
                    value.doctor in (x.traveler, x.supervisor) and x.active
                    for x in state.escort_journeys
                ):
                    raise WorkflowError("Resolve the original Doctor journey before arrival")
                marker.marked = True
                state.sheets[actor.entity].revision += 1
                update = dict(girl_cell=caller.cell, source_event=event, account=account)
                if doc.mode != "outside_frame":
                    update["frame_cell"] = caller.cell
                state.placements = [
                    x.model_copy(update=update) if x.actor == value.doctor else x
                    for x in state.placements
                ]
            value = value.model_copy(update={"phase": "complete", "completion_event": event})
            rules.put(state, "doctor_procedure", value)
            self.game.event(
                c, viewer.user_id, key, "m3.doctor_procedure_completed", state, event_id=event
            )
            if value.kind == "wings":
                from girlframe.services.m3_asset_loss import create_loss_work

                # Both original participants can cross the full-Void threshold:
                # removing the donor component or replacing the Doctor cap slot.
                for subject in (value.counterpart, value.doctor):
                    create_loss_work(
                        self.game,
                        c,
                        before_transfer,
                        state,
                        scope=dict(campaign_id=self.store.campaign_id, campaign_context=True),
                        actor=subject,
                        event=event,
                        reason="doctor_wings",
                        source_id=identity,
                    )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_procedure_completed",
            dict(id=identity, revision=revision, account=account, tag=tag),
            change,
            auto_audit=False,
            authorize=access,
        )

    def adrenal(self, viewer: GuildViewer, key: str, revision: int, account: str) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            if (
                state.revision != revision
                or not account.strip()
                or not owned(self.game, c, state, actor, rules.ADRENAL)
            ):
                raise WorkflowError("Reopen the actual owned Adrenal procedure")
            event = str(uuid4())
            state = rules.adrenal(state, actor, event)
            self.game.event(
                c, viewer.user_id, key, "m3.doctor_adrenal_applied", state, event_id=event
            )
            return dict(track=state.sheets[actor.entity].obsolescence_marked)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_adrenal_applied",
            dict(revision=revision, account=account),
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
                kind=x.kind,
                actionable=x.kind == "ragged" or viewer.user_id == x.controller,
            )
            for x in rules.values(state, "doctor_procedure", rules.Procedure)
            if x.phase == "proposal" and viewer.user_id in (int(x.doctor.entity), x.controller)
        ] + [
            dict(id=x.id, revision=state.revision, kind="protection", actionable=True)
            for x in rules.values(state, "doctor_protection", rules.Protection)
            if x.phase == "protecting" and x.controller == viewer.user_id
        ]

    def stop_protecting(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = next(
                (
                    x
                    for x in rules.values(state, "doctor_protection", rules.Protection)
                    if x.id == identity
                ),
                None,
            )
            if (
                value is None
                or value.controller != viewer.user_id
                or value.phase != "protecting"
                or state.revision != revision
                or not account.strip()
            ):
                raise WorkflowError("Only the actual original protector ends their protection")
            actual = resolve(state, value.protector, profiles(c, self.store.campaign_id))
            if actual.controller != value.controller:
                raise WorkflowError(
                    "Recover the original protector controller before ending protection"
                )
            event = str(uuid4())
            rules.put(
                state,
                "doctor_protection",
                value.model_copy(update=dict(phase="ended", end_event=event)),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.doctor_protection_ended", state, event_id=event
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.doctor_protection_ended",
            dict(id=identity, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=access,
        )
