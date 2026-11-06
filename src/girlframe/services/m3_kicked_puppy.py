"""Source-owned Flirt choice, one real roll and native paid acquisition."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_kicked_puppy as rules
from girlframe.engine.m2 import FLIRT_QUESTIONS, GameState, PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
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


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, state: GameState, prepared: PlayInput
) -> dict[str, Any] | None:
    if prepared.play != "flirt":
        if prepared.kicked_puppy_basis:
            raise WorkflowError("Kicked Puppy's alternative applies only to your actual Flirt")
        return None
    actor = current_ref(state, viewer.user_id)
    receipt = entitlement(game, c, state, actor)
    if receipt is None:
        if prepared.kicked_puppy_basis:
            raise WorkflowError("Acquire the actual Kicked Puppy rule before choosing its basis")
        return None
    Access(game.store).authorize(c, viewer, "plays")
    if prepared.target is None or prepared.target == viewer.user_id:
        raise WorkflowError("Choose another actual original Pilot for this Flirt")
    target = ActorRef(
        kind="pilot",
        entity=str(prepared.target),
        incarnation=game.character_binding(
            c, state, prepared.target, require_current_profile=False
        ),
    )
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    assert game.store.policy.m3_approval is not None
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        frame=receipt.frame_instance,
        purchase=receipt.id,
        use_basis=prepared.kicked_puppy_basis,
        modifier=sum(x.family == "girl" and x.damaged for x in actual.assets),
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
    if actual != action["data"].get("kicked_puppy"):
        raise WorkflowError("Recover the original Kicked Puppy resources, giver and paid source")


def current(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any] | None:
    meta = action["data"].get("kicked_puppy")
    if meta is None or action["data"].get("play") != "flirt":
        return None
    actor = ActorRef.model_validate(meta["actor"])
    receipt = entitlement(game, c, state, actor)
    if receipt is None or receipt.id != meta["purchase"] or receipt.frame_instance != meta["frame"]:
        return None
    return dict(meta)


def self_tag(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    tag: TagState,
) -> bool:
    meta = current(game, c, state, action)
    return bool(
        meta is not None
        and str(owner) == meta["actor"]["entity"]
        and rules.target_gave(tag, ActorRef.model_validate(meta["target"]))
    )


def questions(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[str, ...]:
    return (
        (*FLIRT_QUESTIONS, rules.QUESTION) if current(game, c, state, action) else FLIRT_QUESTIONS
    )


class KickedPuppyService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            try:
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
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
                raise WorkflowError("Reopen the actual Kicked Puppy acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current_frame, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if frame != current_frame or sheet.permissions < price:
                raise WorkflowError("Use the original actual Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.frame_instance == frame
                and x.rule_id == rules.RULE
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
                    grant="kicked-puppy:" + identity,
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
            "m3.kicked_puppy_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            auto_audit=False,
            authorize=access,
        )
