"""Actual Matrix acquisition, factual scene context and owned one-mark timeline effects."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_appearance_matrix as rules
from girlframe.engine import m3_class_grafts as grafts
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
) -> tuple[str, tuple[str, ...]]:
    from girlframe.services.m3_class_retention import proof

    frame, chain = proof(game, c, state, paid)
    if len(chain) > 1:
        registry = Access(game.store).registry
        if registry is None:
            raise WorkflowError("Recover the actual paid retained Matrix source")
        registry.require_available("core.core.frame-requisitions")
    return frame, chain


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
    _paid_source(game, c, state, receipt)
    return receipt


def history(game: "GameService", c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual original Matrix source history")
    return GameState.model_validate_json(raw)


def _historical_source(
    game: "GameService", c: Connection, state: GameState, purchase: str, actor: ActorRef
) -> tuple[FrameRuleReceipt, str]:
    from girlframe.services.m3_class_retention import proof

    paid = next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt)
            and x.id == purchase
            and x.rule_id == rules.RULE
            and x.actor == actor
        ),
        None,
    )
    if paid is None or not grafts.eligible(state, paid):
        raise WorkflowError("Recover the original event's actual Matrix Frame and source")
    return paid, proof(game, c, state, paid)[0]


def prove_use(game: "GameService", c: Connection, state: GameState, value: rules.Use) -> int:
    original = history(game, c, value.event)
    source = next((x for x in rules.uses(original) if x.id == value.id), None)
    event = c.execute(
        sa.select(t.events.c.seq, t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    if (
        source != value.model_copy(update=dict(returned_event=None))
        or event is None
        or event.kind != "m3.matrix_used"
        or event.actor_id != value.actor.entity
    ):
        raise WorkflowError("Recover the original actual owner-marked Matrix event")
    _, frame = _historical_source(game, c, original, value.purchase, value.actor)
    if value.frame != frame or value.origin.frame_instance != frame:
        raise WorkflowError("Recover this actual Matrix use's historical Frame binding")
    if value.returned_event:
        returned = history(game, c, value.returned_event)
        if value not in rules.uses(returned):
            raise WorkflowError("Recover the original physical Matrix return source")
    return int(event.seq)


def prove_mark(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> None:
    value = rules.mark(state, paid)
    own_uses = [x for x in rules.uses(state) if x.purchase == paid.id]
    use_events = [(prove_use(game, c, state, x), True, x.id) for x in own_uses]
    events = list(use_events)
    periods = []
    for fact in state.facts:
        if fact.get("kind") != "matrix_reset":
            continue
        reset = rules.Reset.model_validate_json(fact["body"])
        if reset.purchase != paid.id:
            continue
        action = game.action(c, reset.action)
        event = c.execute(
            sa.select(t.events.c.seq, t.events.c.id, t.events.c.payload_json)
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m3.play_confirmed",
                t.events.c.actor_id == paid.actor.entity,
            )
            .order_by(t.events.c.seq.desc())
        ).all()
        matched = next(
            (x for x in event if json.loads(x.payload_json).get("action_id") == reset.action), None
        )
        # Require the actual action/period, not merely a client-supplied period label.
        if (
            reset.actor != paid.actor
            or reset.frame != paid.frame_instance
            or action["actor_id"] != paid.actor.entity
            or action["data"].get("play") not in ("go_off_duty", "void_observation")
            or action["data"].get("m3", {}).get("period_id") != reset.period
            or matched is None
            or not any(
                f.get("kind") == "matrix_reset" and f.get("body") == reset.model_dump_json()
                for f in history(game, c, matched.id).facts
            )
        ):
            raise WorkflowError("Recover the actual original Matrix Go-Off-Duty start")
        historical, _ = _historical_source(
            game, c, history(game, c, matched.id), reset.purchase, reset.actor
        )
        if historical != paid:
            raise WorkflowError("Recover this original Matrix reset's immutable acquisition")
        periods.append(reset.period)
        events.append((int(matched.seq), False, ""))
    expected = max(events, default=(0, False, ""), key=lambda x: x[0])
    latest_use = max(use_events, key=lambda x: x[0])[2] if use_events else None
    if (
        value.actor != paid.actor
        or value.frame != paid.frame_instance
        or value.marked != expected[1]
        or value.use != latest_use
        or set(value.periods) != set(periods)
    ):
        raise WorkflowError("Recover the actual original Matrix mark/reset state")


def prove_damage(game: "GameService", c: Connection, value: rules.Damage) -> None:
    original = history(game, c, value.event)
    if value not in rules.damages(original):
        raise WorkflowError("Recover the original attributed scene damage event")
    if value.action:
        if game.action(c, value.action)["scene_id"] != value.scene:
            raise WorkflowError("Use only this actual source scene's attributed damage")
    elif value.work:
        work = t.m3["m3_required_work"]
        scene = c.scalar(
            sa.select(work.c.scene_id)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == value.work)
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        if scene != value.scene:
            raise WorkflowError("Recover the exact scene-scoped original damage work")
    else:
        raise WorkflowError("Damage requires its actual source Play or scoped work")


def prove_context(
    game: "GameService", c: Connection, state: GameState, identity: str
) -> rules.Context:
    value = next((x for x in rules.contexts(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Record the actual scene/location context first")
    original = history(game, c, value.event)
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    if (
        value not in rules.contexts(original)
        or event is None
        or event.kind != "m3.matrix_scene_recorded"
        or event.actor_id != str(value.gm)
    ):
        raise WorkflowError("Recover the actual source GM's immutable scene location")
    scene = game.scene(c, value.channel)
    place = (
        next((x for x in state.world.locations if x.id == value.location), None)
        if state.world
        else None
    )
    if (
        scene["id"] != value.scene
        or place is None
        or not place.operational
        or place.cell != value.cell
    ):
        raise WorkflowError("Recover this original open scene and surviving actual location")
    return value


class MatrixService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _access(
        self, c: Connection, viewer: GuildViewer, subsystem: Literal["plays", "world"] = "plays"
    ) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, subsystem, director_response=True)
        assert access.registry is not None
        access.registry.require_available(rules.RULE)

    def _idle(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released")
            .limit(1)
        ):
            raise WorkflowError(
                "Finish original pending Plays and restore scene chat before Matrix use"
            )

    def record_context(
        self, viewer: GuildViewer, key: str, channel: int, expected: int, location: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _cast
            from girlframe.services.m3_medical import MedicalService

            self.game.unpaused(c)
            self._idle(c)
            state = load_state(c, self.store.campaign_id)
            gm, appointment = MedicalService(self.store)._handler(c)
            cast = _cast(self.game, c, state, channel)
            place = (
                next((x for x in state.world.locations if x.id == location and x.operational), None)
                if state.world
                else None
            )
            if viewer.user_id != gm or state.revision != expected or place is None:
                raise WorkflowError("The actual source GM records a real open-scene location")
            if any(x.scene == cast.id for x in rules.contexts(state)):
                raise WorkflowError("Recover the scene's original recorded Matrix location")
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Context(
                id=identity,
                scene=cast.id,
                channel=channel,
                location=place.id,
                cell=place.cell,
                gm=gm,
                appointment=appointment,
                event=event,
            )
            rules.put(state, "matrix_scene", identity, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.matrix_scene_recorded",
                state,
                event_id=event,
                scene=cast.id,
                location=place.id,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.matrix_scene_recorded",
            dict(channel=channel, expected=expected, location=location),
            operation,
            authorize=lambda c: self._access(c, viewer, "world"),
            auto_audit=False,
        )

    def view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            context = next((x for x in rules.contexts(state) if x.scene == scene["id"]), None)
            paid = None
            actor = None
            if str(viewer.user_id) in state.sheets and viewer.user_id in state.order:
                actor = current_ref(state, viewer.user_id)
                paid = entitlement(self.game, c, state, actor)
                if paid:
                    prove_mark(self.game, c, state, paid)
            memories = []
            from girlframe.engine.m3_am_memory import can_recall

            if actor:
                for value in rules.uses(state):
                    if actor in value.witnesses:
                        prove_use(self.game, c, state, value)
                        token = "matrix-memory:" + value.id
                        if can_recall(state, actor, token, learned_revision=value.revision + 1):
                            memories.append(
                                dict(
                                    use=value.id,
                                    scene=value.scene,
                                    actor=value.actor.model_dump(mode="json"),
                                    timeline="present all along"
                                    if value.mode == "appear"
                                    else "never present",
                                    prior_memories_preserved=True,
                                )
                            )
            absent = rules.absence(state, actor) if actor else None
            return dict(
                revision=state.revision,
                channel=channel,
                scene=scene["id"],
                gm=state.handler == viewer.user_id,
                context=context.id if context else None,
                locations=[
                    dict(id=x.id, label=x.name) for x in state.world.locations if x.operational
                ]
                if state.world and state.handler == viewer.user_id
                else [],
                owned=paid is not None,
                marked=rules.mark(state, paid).marked if paid else None,
                absent=absent.id if absent else None,
                memories=memories,
            )

    def _preview(
        self, c: Connection, viewer: GuildViewer, state: GameState, identity: str, mode: rules.Mode
    ) -> dict[str, Any]:
        from girlframe.engine.m3_actors import resolve
        from girlframe.services.m3_actors import profiles

        actor = current_ref(state, viewer.user_id)
        self.game.character_binding(c, state, viewer.user_id)
        paid = entitlement(self.game, c, state, actor)
        if paid is None:
            raise WorkflowError("Acquire or restore your actual original Matrix source first")
        prove_mark(self.game, c, state, paid)
        context = prove_context(self.game, c, state, identity)
        repairs = rules.eligible_damage(state, actor, context.scene)
        bound = profiles(c, self.store.campaign_id)
        for damage in repairs:
            prove_damage(self.game, c, damage)
            resolve(state, damage.target, bound, require_current_profile=False)
        repair_projection = []
        for damage in repairs:
            actual_asset = rules.asset(state, damage.target, damage.asset)
            if actual_asset is None:
                raise WorkflowError("Recover this actual original damaged Asset")
            repair_projection.append(
                dict(
                    id=damage.id,
                    target=damage.target.model_dump(mode="json"),
                    asset=damage.asset,
                    label=actual_asset.name,
                )
            )
        # Run the genuine reducer on a copy for an exact reviewable proposed result.
        _, prospective = rules.apply(state, bound, actor, context, mode, "matrix-preview")
        return dict(
            revision=state.revision,
            context=context.id,
            mode=mode,
            repaired=repair_projection,
            witnesses=[x.model_dump(mode="json") for x in prospective.witnesses],
            destination=context.cell if mode == "appear" else None,
            travels_frame=prospective.travels_frame,
        )

    def preview(self, viewer: GuildViewer, identity: str, mode: rules.Mode) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            return self._preview(c, viewer, load_state(c, self.store.campaign_id), identity, mode)

    def use(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, mode: rules.Mode
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_actors import profiles

            self.game.unpaused(c)
            self._idle(c)
            state = load_state(c, self.store.campaign_id)
            preview = self._preview(c, viewer, state, identity, mode)
            if state.revision != expected:
                raise WorkflowError("Reopen the exact current Matrix preview")
            actor = current_ref(state, viewer.user_id)
            context = prove_context(self.game, c, state, identity)
            event = str(uuid4())
            changed, value = rules.apply(
                state, profiles(c, self.store.campaign_id), actor, context, mode, event
            )
            # Keep ordinary scene participant projections aligned with the true new cast.
            scenes = t.m2["m2_scenes"]
            for cast in changed.scene_casts:
                old = next((x for x in state.scene_casts if x.id == cast.id), None)
                if old == cast:
                    continue
                people = sorted(
                    {x.controller for x in cast.roles}
                    | ({cast.facilitator} if cast.facilitator else set())
                )
                c.execute(
                    scenes.update()
                    .where(scenes.c.campaign_id == self.store.campaign_id, scenes.c.id == cast.id)
                    .values(participants_json=json.dumps(people))
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.matrix_used",
                changed,
                event_id=event,
                use=value.id,
                scene=value.scene,
                mode=mode,
            )
            return dict(
                id=value.id,
                mode=mode,
                repaired=preview["repaired"],
                destination=preview["destination"],
                absent=mode == "disappear",
            )

        return self.store._write(
            viewer,
            key,
            "m3.matrix_used",
            dict(id=identity, expected=expected, mode=mode),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
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
                    grant="appearance-matrix:" + identity,
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
            "m3.appearance_matrix_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            authorize=access,
            auto_audit=False,
        )
