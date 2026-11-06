"""Exact paid Sup acquisition and original-owner growth source validation."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_sup as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_privileges import purchase_proof
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
    purchase_proof(c, game.store, receipt)
    return receipt


def offer(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> dict[str, Any] | None:
    return rules.offers(state, actor) if entitlement(game, c, state, actor) else None


def parse(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef, fields: dict[str, str]
) -> rules.Growth | None:
    if not any(x.startswith("sup_") for x in fields):
        return None
    if (
        set(fields) != {"sup_name", "sup_family", "sup_replace"}
        or entitlement(game, c, state, actor) is None
    ):
        raise WorkflowError(
            "Use this actual owner/Frame's paid Sup growth instead of rewrite/storage"
        )
    return rules.Growth.model_validate(
        dict(
            name=fields["sup_name"],
            family=fields["sup_family"],
            replace=fields["sup_replace"] or None,
        )
    )


def prove_growth(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef, event: str
) -> rules.Grown | None:
    values = [x for x in rules.growths(state) if x.actor == actor and x.event == event]
    if not values:
        return None
    if len(values) != 1:
        raise WorkflowError("Recover the single actual source-owned Sup growth")
    fact = values[0]
    receipt = entitlement(game, c, state, actor)
    asset = next((x for x in state.sheets[actor.entity].assets if x.id == fact.asset), None)
    if (
        receipt is None
        or receipt.id != fact.purchase
        or receipt.frame_instance != fact.frame
        or asset is None
        or not asset.void
        or asset.family != fact.choice.family
        or asset.name != fact.choice.name.strip()
        or asset.description != fact.description
    ):
        raise WorkflowError("Recover the actual paid Sup receipt and new already-Void Asset")
    return fact


class SupService:
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
                permissions=sheet.permissions,
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
            if entry.frame_class != "priestess" or entry.frame_rule != "class_requisition":
                raise WorkflowError("Recover the actual printed Priestess Class Requisition source")

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
            if current != frame or sheet.permissions < price:
                raise WorkflowError("Use the original current Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.frame_instance == frame
                and x.rule_id == rules.RULE
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original paid entitlement instead of buying twice")
            identity, event = str(uuid4()), str(uuid4())
            sheet.permissions -= price
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
                    grant="sup:" + identity,
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
            "m3.sup_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            authorize=access,
            auto_audit=False,
        )
