"""Paid native or grafted Keep basis with actual owned Void and no Heat spend."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_nightmare as rules
from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
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
    from girlframe.services.m3_class_retention import proof

    _, chain = proof(game, c, state, receipt)
    if len(chain) > 1:
        try:
            gate.registry.require_available("core.core.frame-requisitions")
        except ValueError:
            return None
    return receipt


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, state: GameState, prepared: PlayInput
) -> dict[str, Any] | None:
    if prepared.play != "keep_your_head":
        return None
    actor = current_ref(state, viewer.user_id)
    receipt = entitlement(game, c, state, actor)
    if receipt is None:
        return None
    Access(game.store).authorize(c, viewer, "plays")
    if prepared.heat or prepared.dampener_modifier is not None or prepared.kicked_puppy_basis:
        raise WorkflowError("Nightmare Core Keep uses actual Void Assets instead of spending Heat")
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    from girlframe.engine.m3_class_retention import binding

    frame, _ = binding(state, receipt)
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        frame=frame,
        purchase=receipt.id,
        modifier=sum(x.void for x in actual.assets),
        registry=game.store.policy.m3_approval.registry_sha256,
    )


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    actual = prepare(game, c, viewer, state, PlayInput.model_validate(action["data"]["prepared"]))
    if actual != action["data"].get("nightmare_core"):
        raise WorkflowError(
            "Recover this original Keep's paid Frame and actual effective Void Assets"
        )


def automatic(action: dict[str, Any]) -> frozenset[str]:
    meta = action["data"].get("nightmare_core")
    receipt = action["data"].get("receipt") or {}
    return (
        frozenset({"terrifying"})
        if meta is not None
        and action["data"].get("play") == "keep_your_head"
        and receipt.get("nightmare_purchase") == meta["purchase"]
        else frozenset()
    )


class NightmareService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer, actor: ActorRef | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = actor or current_ref(state, viewer.user_id)
            try:
                sheet, frame = rules.current(state, actor)
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
            acquired = next(
                (
                    x
                    for x in state.requisitions
                    if isinstance(x, FrameRuleReceipt)
                    and x.actor == actor
                    and rules.receipt_eligible(state, x)
                ),
                None,
            )
            native = frame_class(sheet.frame) == "priestess"
            from girlframe.engine.m3_class_retention import binding

            chain = binding(state, acquired)[1] if acquired is not None else ()
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                permissions=sheet.permissions,
                owned=receipt is not None,
                suspended=any(suspended(state, identity) for identity in chain),
                kind="ability_unlock" if native else "frame_grafting",
                price=2 if native else 3,
                donors=list(rules.DONORS) if not native else [],
                modifier=sum(
                    x.void
                    for x in resolve(state, actor, profiles(c, self.store.campaign_id)).assets
                ),
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
            if (entry.frame_class, entry.frame_rule) != ("priestess", "class_requisition"):
                raise WorkflowError("Recover the actual Priestess Class Nightmare Core source")

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
                raise WorkflowError("Reopen the actual Nightmare Core acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current = rules.current(state, actor)
            native = frame_class(sheet.frame) == "priestess"
            price = 2 if native else 3
            donor = sheet.frame if native else donor_frame
            if (
                native
                and donor_frame not in (None, sheet.frame)
                or not native
                and donor not in rules.DONORS
            ):
                raise WorkflowError("Select an actual Priestess donor for this non-Priestess graft")
            assert donor is not None
            if current != frame or sheet.permissions < price:
                raise WorkflowError("Use the actual original Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and rules.receipt_eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original entitlement instead of buying twice")
            identity, event = str(uuid4()), str(uuid4())
            sheet.permissions -= price
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind="ability_unlock" if native else "frame_grafting",
                    actor=actor,
                    frame_instance=frame,
                    frame=sheet.frame,
                    donor_frame=donor,
                    rule_id=rules.RULE,
                    grant="nightmare:" + identity,
                    price=2 if native else 3,
                    account=account,
                    source_event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ability_unlock_purchased" if native else "m3.frame_grafting_purchased",
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
            "m3.nightmare_purchased",
            dict(
                revision=revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                account=account,
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            auto_audit=False,
            authorize=access,
        )
