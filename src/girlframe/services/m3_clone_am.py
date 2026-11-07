"""Actual original Clone AM acquisition and source-owned private resources."""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_clone_am as rules
from girlframe.engine import m3_clone_residency as residency
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


def _paid_source(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> None:
    from girlframe.services.m3_class_retention import proof

    _, chain = proof(game, c, state, paid)
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    if len(chain) > 1:
        gate.registry.require_available("core.core.frame-requisitions")


def _prove_residence(game: "GameService", c: Connection, state: GameState, ref: ActorRef) -> None:
    history = t.m2["m2_state_history"]
    for change in residency.transfers(state, ref):
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
            change.original.entity,
        ):
            raise WorkflowError("Recover the copy's actual paid residency event")
        saved = GameState.model_validate_json(source.body_json)
        if change not in residency.transfers(saved, ref):
            raise WorkflowError("Recover the original same-copy residence snapshot")
        previous = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == game.store.campaign_id,
                t.events.c.seq < source.seq,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if previous is None:
            raise WorkflowError("Recover the actual copy before carrier transfer")
        from girlframe.engine.m3_frame_swap_state import SwapReceipt

        paid = next(x for x in saved.requisitions if x.id == change.purchase)
        swap = next(x for x in saved.requisitions if x.id == change.swap)
        if not isinstance(paid, FrameRuleReceipt) or not isinstance(swap, SwapReceipt):
            raise WorkflowError("Recover the exact copy's paid transfer receipts")
        replay = saved.model_copy(deep=True)
        replay.facts = [
            x
            for x in replay.facts
            if not (x.get("kind") == residency.KIND and x.get("body") == change.model_dump_json())
        ]
        residency.transfer(GameState.model_validate_json(previous), replay, paid, swap)
        if replay != saved:
            raise WorkflowError("Recover the actual unchanged copy and delivered carrier")


def prove_copy(game: "GameService", c: Connection, state: GameState, ref: ActorRef) -> None:
    value = rules.current(state, ref)
    receipt = grafts.held(state, value.original, rules.RULE)
    if receipt is None:
        raise WorkflowError("Restore the copy's original paid source")
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    _paid_source(game, c, state, receipt)
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual original copy birth event")
    born = rules.find(GameState.model_validate_json(raw), ref)
    if (
        born is None
        or (born.original, born.frame, born.receipt, born.source_event)
        != (value.original, value.frame, value.receipt, value.source_event)
        or born.identity.name != "Perfect Copy"
        or born.identity.marked
        or born.tags
    ):
        raise WorkflowError("Recover the actual original one-Identity artificial copy")
    latest = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
        .where(t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if latest is None or rules.find(GameState.model_validate_json(latest), ref) != value:
        raise WorkflowError("Recover the copy's actual saved Identity, marks and Tags")
    _prove_residence(game, c, state, ref)


def prepare_transfer(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> GameState:
    if paid.rule_id != rules.RULE or grafts.held(state, paid.actor, rules.RULE) != paid:
        raise WorkflowError("Transfer only the actual held original Clone AM source")
    copies = tuple(x for x in rules.copies(state) if x.receipt == paid.id)
    if len(copies) != 1:
        raise WorkflowError("Recover the one actual existing copy before transfer")
    prove_copy(game, c, state, copies[0].ref)
    return state.model_copy(deep=True)


def prove_additional(
    game: "GameService", c: Connection, state: GameState, owner: int, entry: str | None = None
) -> None:
    available = {x.id for x in rules.additional_identities(state, owner)}
    for value in rules.copies(state):
        if value.original.entity == str(owner) and (entry is None or entry == value.identity.id):
            if entry is not None or value.identity.id in available:
                prove_copy(game, c, state, value.ref)


def entitlement(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> FrameRuleReceipt | None:
    receipt = grafts.held(state, actor, rules.RULE)
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


class CloneService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def fulfill_followthrough(
        self, viewer: GuildViewer, key: str, obligation_id: str, account: str, *, channel: int
    ) -> dict[str, Any]:
        from girlframe.engine.m2 import PlayInput
        from girlframe.services.m3_actor_plays import ActorPlayService

        own = self.view(viewer)
        if not own["owned"]:
            raise WorkflowError("Use your actual copy's owed source")
        ref = ActorRef.model_validate(own["actor"])
        source = ActorPlayService(self.game)
        data = source.preview(viewer, channel, ref)
        return source.begin(
            viewer,
            key,
            channel,
            ref,
            data["actor"]["source_sha256"],
            ActorRef.model_validate(data["adjudicator"]["ref"])
            if data["adjudicator"]["ref"]
            else None,
            data["cast_revision"],
            PlayInput(
                play="clone_followthrough",
                context=account,
                heat=0,
                trigger_confirmed=True,
                source_work=obligation_id,
            ),
        )

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            original = current_ref(state, viewer.user_id)
            paid = entitlement(self.game, c, state, original)
            value = next(
                (
                    x
                    for x in rules.copies(state)
                    if x.original == original and paid is not None and x.receipt == paid.id
                ),
                None,
            )
            if value is None:
                return dict(owned=False)
            prove_copy(self.game, c, state, value.ref)
            from girlframe.engine.m3_actor_bonds import depth
            from girlframe.engine.m3_actors import resolve
            from girlframe.services.m3_actors import profiles

            actual = resolve(state, value.ref, profiles(c, self.store.campaign_id))
            return dict(
                owned=True,
                actor=value.ref.model_dump(mode="json"),
                heat=actual.heat,
                identity=value.identity.model_dump(mode="json"),
                tags=[x.model_dump(mode="json") for x in value.tags],
                bonds=[
                    dict(
                        other=(x.second if x.first == value.ref else x.first).model_dump(
                            mode="json"
                        ),
                        depth=depth(state, x.first, x.second),
                    )
                    for x in state.actor_bonds
                    if value.ref in (x.first, x.second)
                ],
                frame=residency.residence(state, value.ref),
                birth_frame=value.frame,
                cell=actual.cell,
            )

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
            acquired = next(
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
            from girlframe.engine.m3_class_retention import binding

            chain = binding(state, acquired)[1] if acquired is not None else ()
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                permissions=available(state, actor),
                kind=kind,
                price=price,
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                suspended=any(suspended(state, identity) for identity in chain),
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
                    grant="clone-am:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            receipt = next(
                x
                for x in state.requisitions
                if isinstance(x, FrameRuleReceipt) and x.id == identity
            )
            rules.create(state, receipt)
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
            "m3.clone_am_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            authorize=access,
            auto_audit=False,
        )
