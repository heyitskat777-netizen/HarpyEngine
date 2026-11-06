"""Paid native LEGION extra capacity and original authored Frame Asset."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_modular as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _paid_source(
    game: "GameService", c: Connection, state: GameState, receipt: FrameRuleReceipt
) -> tuple[str, tuple[str, ...]]:
    from girlframe.services.m3_class_retention import proof

    frame, chain = proof(game, c, state, receipt)
    if len(chain) > 1:
        registry = Access(game.store).registry
        if registry is None:
            raise WorkflowError("Recover the actual paid retained Modular source")
        registry.require_available("core.core.frame-requisitions")
    return frame, chain


def entitlement(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> FrameRuleReceipt | None:
    receipt = rules.held(state, actor)
    if receipt is None:
        return None
    gate = Access(game.store)
    if gate.registry is None:
        return None
    try:
        gate.registry.require_available(rules.RULE)
    except ValueError:
        return None
    _paid_source(game, c, state, receipt)
    return receipt


def repair_options(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> list[dict[str, str]]:
    if entitlement(game, c, state, actor) is None:
        return []
    eligible = set(rules.replaceable(state, actor))
    return [
        dict(id=x.id, label=x.name) for x in state.sheets[actor.entity].assets if x.id in eligible
    ]


class ModularService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, actor: ActorRef | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = actor or current_ref(state, viewer.user_id)
            try:
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
                if actor.entity != str(viewer.user_id):
                    raise ValueError("Use only your actual own original role")
                gate = Access(self.store)
                if gate.registry is None:
                    return dict(available=False)
                gate.registry.require_available(rules.RULE)
            except (ValueError, KeyError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
            receipt = entitlement(self.game, c, state, actor)
            paid = next(
                (
                    x
                    for x in state.requisitions
                    if isinstance(x, FrameRuleReceipt)
                    and x.actor == actor
                    and x.rule_id == rules.RULE
                    and grafts.eligible(state, x)
                ),
                None,
            )
            chain = _paid_source(self.game, c, state, paid)[1] if paid else ()
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                permissions=sheet.permissions,
                kind=kind,
                price=price,
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                suspended=any(suspended(state, identity) for identity in chain),
                owned=receipt is not None,
            )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        frame: str,
        account: str,
        name: str,
        description: str,
        donor_frame: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy")
            assert gate.registry is not None
            entry = gate.registry.require_available(rules.RULE)
            if (entry.frame_class, entry.frame_rule) != ("legion", "class_requisition"):
                raise WorkflowError("Recover the actual LEGION Class source")

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
                or not name.strip()
                or not description.strip()
            ):
                raise WorkflowError("Reopen the actual Modular Build acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if current != frame or sheet.permissions < price:
                raise WorkflowError("Use the actual original Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.rule_id == rules.RULE
                and grafts.eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original entitlement instead of buying twice")
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
                    grant="modular:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            from girlframe.engine.m3_core import install

            state.sheets[actor.entity] = install(
                sheet,
                AssetState(
                    id="modular:" + identity,
                    family="frame",
                    name=name.strip(),
                    description=description.strip(),
                ),
                state=state,
            ).sheet
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
            "m3.modular_purchased",
            dict(
                revision=revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                account=account,
                name=name,
                description=description,
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            auto_audit=False,
            authorize=access,
        )
