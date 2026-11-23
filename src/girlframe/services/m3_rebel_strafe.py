"""Source-owned cockpit setup and ordinary physical movement for Low Rebellion."""

import json
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_rebel_strafe as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_leviathan_arrival import external_pose, install_external_pose
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world_state import Cell
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_movement import _apply_context, proposal_context
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

Action = Literal["propose", "approve", "perform"]


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    event: str,
    pilot_id: str | None,
    base_id: str | None,
    account: str,
) -> None:
    pilot, base = rules.source(state, pilot_id, base_id)
    handler = active_handler(state)
    if (
        handler is None
        or not in_responsibility(state, base.cell)
        or not HandlerService(strain.store)._member(c, pilot.controller)
        or any(x.id == row["id"] for x in rules.passes(state))
    ):
        raise WorkflowError("Bind the actual local base and original Rebel controller")
    rules.save(
        state,
        rules.Pass(
            id=row["id"],
            source=event,
            period=row["off_duty_id"],
            actor=ActorRef(kind="external_pilot", entity=pilot.id),
            controller=pilot.controller,
            handler=handler,
            base=base.id,
            account=account,
        ),
    )


class StrafeService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store

    def _owned(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Pass:
        case = next((x for x in rules.passes(state) if x.id == identity), None)
        if case is None or viewer.user_id not in (case.controller, int(case.handler.entity)):
            raise WorkflowError("Only the original Rebel controller and Handler have this pass")
        return case

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(state, viewer, identity)
            if case.performance:
                return dict(
                    revision=state.revision,
                    mode=None,
                    account=case.action_account,
                    done=True,
                    positions=(),
                    assets=(),
                )
            pilot, base = rules.source(state, case.actor.entity, case.base)
            pose = external_pose(state, case.actor)
            mode = None
            if pilot.controller == case.controller and same_handler_body(state, case.handler):
                if pose is None and not case.pose_event and viewer.user_id == case.controller:
                    mode = "propose"
                elif (
                    pose is None and case.pose_event and viewer.user_id == int(case.handler.entity)
                ):
                    mode = "approve"
                elif pose is not None and viewer.user_id == case.controller:
                    mode = "perform"
            return dict(
                revision=state.revision,
                mode=mode,
                account=case.pose_account if mode == "approve" else case.account,
                done=False,
                base=base.name,
                positions=rules.destinations(state, case.actor, base) if mode == "perform" else (),
                assets=tuple(
                    (x.id, x.name) for x in pilot.assets if x.family == "frame" and not x.damaged
                )
                if mode == "perform"
                else (),
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: Action,
        account: str,
        *,
        channel: int | None = None,
        destination: Cell | None = None,
        asset: str | None = None,
    ) -> dict[str, Any]:
        if (
            action not in ("propose", "approve", "perform")
            or not 0 < len(account.strip()) <= 1200
            or (action == "perform")
            != (channel is not None and destination is not None and asset is not None)
            or (action != "perform" and any(x is not None for x in (channel, destination, asset)))
        ):
            raise WorkflowError("Record the actual cockpit facts or physical pass")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._owned(state, viewer, identity)
            owner = int(case.handler.entity) if action == "approve" else case.controller
            if owner != viewer.user_id or not same_handler_body(state, case.handler):
                raise WorkflowError("Only the original owner makes this cockpit or pass decision")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, expected)
            case = self._owned(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                row["state"] != "pending"
                or row["off_duty_id"] != case.period
                or body.get("strafe_requested") != case.source
                or body["rule_id"] != rules.RULE
                or self.strain.periods._get(c, case.period).phase != "preparing"
                or case.performance
            ):
                raise WorkflowError("Recover the original pending Rebel pass")
            pilot, base = rules.source(state, case.actor.entity, case.base)
            if pilot.controller != case.controller:
                raise WorkflowError("Recover the original Rebel controller")
            event = str(uuid4())
            pose = external_pose(state, case.actor)
            if action == "propose":
                if pose is not None or case.pose_event:
                    raise WorkflowError("Keep the existing original cockpit facts")
                case = case.model_copy(
                    update=dict(
                        pose_event=event, pose_account=account.strip(), pose_cell=pilot.cell
                    )
                )
            elif action == "approve":
                if (
                    pose is not None
                    or not case.pose_event
                    or not case.pose_account
                    or case.pose_cell != pilot.cell
                    or case.pose_review
                ):
                    raise WorkflowError("Review the original still-current occupied-cockpit facts")
                state = install_external_pose(
                    state,
                    case.actor,
                    pilot.cell,
                    pilot.cell,
                    "piloting",
                    event,
                    case.pose_account,
                    owner=case.controller,
                    judge=viewer.user_id,
                )
                case = case.model_copy(update={"pose_review": event})
            else:
                assert destination is not None and channel is not None
                if destination not in rules.destinations(state, case.actor, base) or not any(
                    x.id == asset and x.family == "frame" and not x.damaged for x in pilot.assets
                ):
                    raise WorkflowError(
                        "Use a functional original Frame Asset on a real pass beside this base"
                    )
                context = proposal_context(
                    self.game,
                    c,
                    viewer,
                    state,
                    channel,
                    case.actor,
                    destination,
                    True,
                    account.strip(),
                )
                _apply_context(state, context, event)
                case = case.model_copy(
                    update=dict(
                        performance=event,
                        scene=context["scene"],
                        origin=tuple(context["origin"]),
                        destination=destination,
                        asset=asset,
                        action_account=account.strip(),
                    )
                )
            rules.save(state, case)
            self.game.event(
                c, viewer.user_id, key, "m3.rebel_strafe", state, event_id=event, work_id=identity
            )
            if case.performance:
                self.strain._save(c, row, event, body | {"strafe_performed": event}, resolved=True)
            return dict(id=identity, state="resolved" if case.performance else "pending")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.rebel_strafe",
            dict(
                id=identity,
                expected=expected,
                action=action,
                account=account,
                channel=channel,
                destination=destination,
                asset=asset,
            ),
            operation,
            authorize,
        )
