"""Owned private Home installation and source-proved real cockpit effects."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_home as rules
from girlframe.engine import m3_home_objects as hardware
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_tag_permissions import PermissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prove_prepared(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> hardware.PreparedHome:
    from girlframe.services.m3_class_retention import proof

    HomeService(game)._source(c, state, paid)
    _, chain = proof(game, c, state, paid)
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    if len(chain) > 1:
        gate.registry.require_available("core.core.frame-requisitions")
    result = hardware.prepared(state, paid)
    history = t.m2["m2_state_history"]
    for change in hardware.transfers(state, paid):
        source = c.execute(
            sa.select(t.events.c.seq, t.events.c.kind, t.events.c.actor_id, history.c.body_json)
            .join(history, history.c.event_id == t.events.c.id)
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                history.c.campaign_id == game.store.campaign_id,
                t.events.c.id == change.event,
            )
        ).first()
        if source is None or (source.kind, source.actor_id) != (
            "m3.frame_swap_purchased",
            paid.actor.entity,
        ):
            raise WorkflowError("Recover the actual paid Home preparation source")
        saved = GameState.model_validate_json(source.body_json)
        if change not in hardware.transfers(saved, paid):
            raise WorkflowError("Recover the original same-object Home preparation snapshot")
        previous = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < source.seq)
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if previous is None:
            raise WorkflowError("Recover the actual Home before reinstallation")
        from girlframe.engine.m3_frame_swap_state import SwapReceipt

        swap = next(x for x in saved.requisitions if x.id == change.swap)
        if not isinstance(swap, SwapReceipt):
            raise WorkflowError("Recover this actual Home's paid exchange receipt")
        replay = saved.model_copy(deep=True)
        replay.facts = [
            x
            for x in replay.facts
            if not (x.get("kind") == hardware.KIND and x.get("body") == change.model_dump_json())
        ]
        hardware.transfer(
            GameState.model_validate_json(previous), replay, paid, swap, confirmed=change.confirmed
        )
        if replay != saved:
            raise WorkflowError("Recover the same possessions and prepared replacement comforts")
    return result


def prepare_transfer(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> GameState:
    if paid.rule_id != rules.RULE or rules.held(state, paid.actor) != paid:
        raise WorkflowError("Transfer only the actual original held Home source")
    prove_prepared(game, c, state, paid)
    hardware.accessible(state, paid)
    return state.model_copy(deep=True)


class HomeService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _source(
        self, c: Connection, state: GameState, receipt: FrameRuleReceipt
    ) -> rules.Installation:
        purchase_proof(c, self.store, receipt)
        value = rules.installed(state, receipt)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == receipt.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        if original is None or rules.installed(original, receipt) != value:
            raise WorkflowError("Recover the original source-bound secret installation")
        return value

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy")
        assert gate.registry is not None
        entry = gate.registry.require_available(rules.RULE)
        if (entry.scope, entry.frame_class, entry.frame_rule) != (
            "frame",
            "legion",
            "class_requisition",
        ):
            raise WorkflowError("Recover the printed LEGION Home source")

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            try:
                actor = current_ref(state, viewer.user_id)
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
                gate = Access(self.store)
                if gate.registry is None:
                    return dict(available=False)
                gate.registry.require_available(rules.RULE)
            except (ValueError, KeyError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
            receipt = next(
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
            installation = self._source(c, state, receipt) if receipt else None
            from girlframe.engine.m3_class_retention import binding

            chain = binding(state, receipt)[1] if receipt is not None else ()
            active = receipt is not None and rules.held(state, actor) == receipt
            prepared = hardware.prepared(state, receipt) if receipt is not None else None
            others = []
            if active:
                bindings = profiles(c, self.store.campaign_id)
                for candidate in state.sheets.values():
                    if candidate.character_id is None or candidate.owner == viewer.user_id:
                        continue
                    other = current_ref(state, candidate.owner)
                    try:
                        physical = rules.together(state, actor, other, bindings)
                    except (ValueError, KeyError):
                        continue
                    others.append(
                        dict(
                            actor=other.model_dump(mode="json"),
                            label=candidate.callsign,
                            physical=physical,
                            depth=depth(state, actor, other),
                        )
                    )
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                kind=kind,
                price=price,
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                permissions=sheet.permissions,
                owned=receipt is not None,
                suspended=any(suspended(state, identity) for identity in chain),
                items=list(installation.items) if installation else [],
                prepared=prepared.model_dump(mode="json") if prepared else None,
                others=others,
                tags=[
                    dict(id=x.id, label=x.label)
                    for x in rules.own_tags(state, actor)
                    if rules.rejectable(state, actor, x)
                ]
                if active
                else [],
            )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        frame: str,
        items: tuple[str, ...],
        account: str,
        donor_frame: str | None = None,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if (
                state.revision != revision
                or actor != current_ref(state, viewer.user_id)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual original Home acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if current != frame or sheet.permissions < price:
                raise WorkflowError("Use the actual current Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.rule_id == rules.RULE
                and grafts.eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError(
                    "Restore the original secret installation instead of buying twice"
                )
            identity, event = str(uuid4()), str(uuid4())
            installation = rules.Installation(
                purchase=identity, actor=actor, frame=frame, items=items, event=event
            )
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
                    grant="home:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            state.facts.append(
                dict(
                    kind="home_installation", purchase=identity, body=installation.model_dump_json()
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
            "m3.home_purchased",
            dict(
                revision=revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                items=items,
                account=account,
                donor_frame=donor_frame,
            ),
            change,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )

    def use(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        other: ActorRef,
        physical: str,
        *,
        operation: Literal["bond", "reject"],
        account: str,
        item: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            self.game.character_binding(c, state, viewer.user_id)
            if other.kind != "pilot" or other == actor:
                raise WorkflowError("Use another actual original Pilot in this exact Frame")
            self.game.character_binding(c, state, int(other.entity), require_current_profile=False)
            receipt = rules.held(state, actor)
            if receipt is None:
                raise WorkflowError("Restore your original paid Home source before using it")
            self._source(c, state, receipt)
            current_home = prove_prepared(self.game, c, state, receipt)
            if (
                state.revision != revision
                or not account.strip()
                or len(account) > 1200
                or rules.together(state, actor, other, profiles(c, self.store.campaign_id))
                != physical
            ):
                raise WorkflowError(
                    "Refresh the actual same-Frame occupants and original Home source"
                )
            event = str(uuid4())
            if operation == "bond" and item is not None and tag is None:
                state = rules.deepen(
                    state, actor, other, item, event, profiles(c, self.store.campaign_id)
                )
            elif operation == "reject" and tag is not None and item is None:
                chosen = next((x for x in rules.own_tags(state, actor) if x.id == tag), None)
                if chosen is None:
                    raise WorkflowError("Choose your actual own Tag")
                ChoiceEngine(self.game).prove_tag_setter(c, state, viewer.user_id, chosen)
                PermissionService(self.store).authorize_rejection(c, viewer, state, actor, tag)
                rules.reject(state, actor, other, tag, profiles(c, self.store.campaign_id))
                ChoiceEngine(self.game).tag_resolved(state, viewer.user_id, tag)
            else:
                raise WorkflowError("Choose the actual Bond item or owned Tag rejection")
            state.facts.append(
                dict(
                    kind="home_used",
                    purchase=receipt.id,
                    actor=actor.model_dump_json(),
                    other=other.model_dump_json(),
                    physical=physical,
                    operation=operation,
                    item=item or "",
                    object_ids=json.dumps(
                        tuple(x.id for x in current_home.objects if x.choice == item)
                    ),
                    realization_ids=json.dumps(
                        tuple(x.id for x in current_home.realizations if x.choice == item)
                    ),
                    tag=tag or "",
                    account=account,
                    event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.home_used",
                state,
                event_id=event,
                operation=operation,
                requisition_id=receipt.id,
            )
            return dict(purchase=receipt.id, operation=operation)

        return self.store._write(
            viewer,
            key,
            "m3.home_used",
            dict(
                revision=revision,
                other=other.model_dump(mode="json"),
                physical=physical,
                operation=operation,
                account=account,
                item=item,
                tag=tag,
            ),
            change,
            auto_audit=False,
            authorize=lambda c: self._authorize(c, viewer),
        )
