"""Paid original-frame proof and one real roll, without changing actual Heat spent."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_dampener as rules
from girlframe.engine.m2 import GameState, PlayInput
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
    gate = Access(game.store)
    if gate.registry is None:
        return None
    try:
        gate.registry.require_available(rules.RULE)
    except ValueError:
        return None
    from girlframe.services.m3_class_retention import proof

    _, source_chain = proof(game, c, state, receipt)
    if len(source_chain) > 1:
        try:
            gate.registry.require_available("core.core.frame-requisitions")
        except ValueError:
            return None
    return receipt


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, state: GameState, prepared: PlayInput
) -> dict[str, Any] | None:
    if prepared.dampener_modifier is None:
        return None
    Access(game.store).authorize(c, viewer, "plays")
    from girlframe.services.m3_princess_performer import acting_owner

    owner = acting_owner(game, c, viewer, prepared, state)
    actor = current_ref(state, owner)
    receipt = entitlement(game, c, state, actor)
    if (
        receipt is None
        or prepared.heat < 5
        or prepared.play in ("go_off_duty", "void_observation", "defeat", "living_battery")
    ):
        raise WorkflowError(
            "Dampener requires its paid entitlement and at least five Heat spent on this roll"
        )
    assert game.store.policy.m3_approval is not None
    from girlframe.engine.m3_class_retention import binding

    actual_frame, _ = binding(state, receipt)
    return dict(
        actor=actor.model_dump(mode="json"),
        frame=actual_frame,
        purchase=receipt.id,
        modifier=prepared.dampener_modifier,
        heat=prepared.heat,
        registry=game.store.policy.m3_approval.registry_sha256,
    )


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    meta = action["data"].get("dampener")
    prepared = PlayInput.model_validate(action["data"]["prepared"])
    actual = prepare(game, c, viewer, state, prepared)
    if actual != meta:
        raise WorkflowError("Recover the actual original unrolled Dampener source and owned choice")
    if meta is not None and (
        action["data"].get("m3")
        or action["data"].get("defeat")
        or (action["data"].get("janus") and action["data"]["janus"].get("mode") != "pandora")
    ):
        raise WorkflowError("Dampener cannot replace a non-Heat roll basis")


class DampenerService:
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
                    raise ValueError("Use your actual own original role")
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
            ):
                raise WorkflowError("Reopen the actual Dampener acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if current != frame or available(state, actor) < price:
                raise WorkflowError("Use the original actual Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and (x.frame_instance == frame or grafts.eligible(state, x))
                and x.rule_id == rules.RULE
                for x in state.requisitions
            ):
                raise WorkflowError(
                    "Restore the original Dampener entitlement instead of buying twice"
                )
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
                    grant="dampener:" + identity,
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
            "m3.dampener_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            auto_audit=False,
            authorize=access,
        )
