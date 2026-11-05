"""Paid native LEGION extra capacity and original authored Frame Asset."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_modular as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
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
    gate = Access(game.store)
    if gate.registry is None:
        return None
    try:
        gate.registry.require_available(rules.RULE)
    except ValueError:
        return None
    purchase_proof(c, game.store, receipt)
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
                sheet, frame = rules.native(state, actor)
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
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                permissions=sheet.permissions,
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
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy")
            assert gate.registry is not None
            entry = gate.registry.require_available(rules.RULE)
            if (entry.frame_class, entry.frame_rule) != ("legion", "class_requisition"):
                raise WorkflowError("Recover the actual native LEGION Class source")

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
                raise WorkflowError("Reopen the actual native Modular Build acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current = rules.native(state, actor)
            if current != frame or sheet.permissions < 2:
                raise WorkflowError("Use the actual original Frame and two Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.frame_instance == frame
                and x.rule_id == rules.RULE
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
                    donor_frame=sheet.frame,
                    rule_id=rules.RULE,
                    grant="modular:" + identity,
                    price=2,
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
                "m3.ability_unlock_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rules.RULE,
                cost=2,
            )
            return dict(id=identity, cost=2)

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
            ),
            change,
            auto_audit=False,
            authorize=access,
        )
