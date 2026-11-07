"""Source-paid native Untouchable acquisition and exact Engage substitution entitlement."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_untouchable as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def entitlement(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> FrameRuleReceipt | None:
    receipt = rules.held(state, actor)
    if receipt is None:
        return None
    access = Access(game.store)
    if access.registry is None:
        return None
    try:
        access.registry.require_available(rules.RULE)
    except ValueError:
        return None
    from girlframe.services.m3_class_retention import proof

    _, chain = proof(game, c, state, receipt)
    if len(chain) > 1:
        try:
            access.registry.require_available("core.core.frame-requisitions")
        except ValueError:
            return None
    return receipt


def tags(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> list[dict[str, str]]:
    if entitlement(game, c, state, actor) is None:
        return []
    return [dict(id=x.id, label=x.label) for x in state.sheets[actor.entity].tags if not x.marked]


class UntouchableService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            try:
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
                access = Access(self.store)
                if access.registry is None:
                    raise ValueError("No reviewed rule source")
                access.registry.require_available(rules.RULE)
            except (ValueError, KeyError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
            receipt = entitlement(self.game, c, state, actor)
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                permissions=available(state, actor),
                kind=kind,
                price=price,
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                suspended=any(
                    isinstance(x, FrameRuleReceipt)
                    and x.actor == actor
                    and x.rule_id == rules.RULE
                    and grafts.eligible(state, x)
                    and suspended(state, x.id)
                    for x in state.requisitions
                ),
                owned=receipt is not None,
                receipt=receipt.id if receipt else None,
            )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        frame: str,
        account: str,
        donor_frame: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy")
            assert gate.registry is not None
            entry = gate.registry.require_available(rules.RULE)
            if entry.frame_class != "autocrat" or entry.frame_rule != "class_requisition":
                raise WorkflowError("Recover the actual printed Autocrat Class Requisition source")

        def change(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_requisitions import RequisitionService

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if (
                state.revision != revision
                or actor != current_ref(state, viewer.user_id)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual original Class acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if current != frame or available(state, actor) < price:
                raise WorkflowError("Use the original current Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.rule_id == rules.RULE
                and grafts.eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original paid entitlement instead of buying twice")
            identity, event = str(uuid4()), str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rules.RULE, price, donor)
            debit(state, actor, price, event=event, source=identity, payment=payment)
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind=kind,
                    actor=actor,
                    frame_instance=frame,
                    frame=sheet.frame,
                    donor_frame=donor,
                    rule_id=rules.RULE,
                    grant="untouchable:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rules.RULE,
                cost=price,
            )
            return dict(id=identity, cost=price)

        return self.store._write(
            viewer,
            key,
            "m3.untouchable_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            authorize=access,
            auto_audit=False,
        )
