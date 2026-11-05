"""Native Doctor acquisitions pay once, grant once and unmark one track box."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_doctor import owned
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

IMPLEMENTED = rules.REQUISITIONS


def options(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> tuple[list[Any], list[str]]:
    available, held = [], []
    for rule in IMPLEMENTED:
        try:
            if owned(game, c, state, actor, rule):
                held.append(rule)
            else:
                available.append(dict(id=rule, label=rules.TITLES[rule]))
        except (WorkflowError, ValueError):
            pass
    return available, held


class DoctorRequisitionService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def buy(
        self, viewer: GuildViewer, key: str, revision: int, rule: str, account: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy")
            assert gate.registry is not None
            entry = gate.registry.require_available(rule)
            if (
                rule not in IMPLEMENTED
                or entry.frame_playbook != rules.BOOK
                or entry.frame_rule != "requisition"
            ):
                raise WorkflowError("Choose a reviewed native Doctor Requisition with its consumer")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            sheet = rules.sheet(state, actor)
            if (
                state.revision != revision
                or not account.strip()
                or self.game.pending_actions(c)
                or self.game.immediate_work(c, viewer.user_id)
                or sheet.permissions < 2
            ):
                raise WorkflowError("Refresh the actual Doctor acquisition and its two Permissions")
            frame = rules.frame_id(state, actor)
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.frame_instance == frame
                and x.rule_id == rule
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original entitlement instead of buying twice")
            identity, event = str(uuid4()), str(uuid4())
            sheet.permissions -= 2
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind="ability_unlock",
                    actor=actor,
                    frame_instance=frame,
                    frame=sheet.frame,
                    donor_frame=rules.BOOK,
                    rule_id=rule,
                    grant="doctor:" + identity,
                    price=2,
                    account=account,
                    source_event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ability_unlock_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rule,
                cost=2,
            )
            return dict(
                id=identity, rule=rule, cost=2, track=state.sheets[actor.entity].obsolescence_marked
            )

        return self.store._write(
            viewer,
            key,
            "m3.doctor_requisition_purchased",
            dict(rule=rule, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=access,
        )
