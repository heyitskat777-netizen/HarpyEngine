"""Genuine paid Succubus sources and controller-owned ordinary NPC Order responses."""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_succubus as rules
from girlframe.engine.m2 import GameState, higher
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.engine.m3_role_punishment_state import RolePunishment
    from girlframe.services.m2_game import GameService


def _registry(game: "GameService") -> str:
    registry = Access(game.store).registry
    approval = game.store.policy.m3_approval
    if (
        registry is None
        or approval is None
        or digest(registry) != approval.registry_sha256
        or "plays" not in approval.subsystems
        or game.store.policy.owner_m3_rulings is None
        or approval.scope == "core_complete"
        and registry.coverage != "RULES_COMPLETE"
    ):
        raise WorkflowError("M3_REVIEW_PENDING: review this actual Succubus Order source")
    registry.require_available(rules.RULE)
    return approval.registry_sha256


def _paid_source(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> tuple[str, ...]:
    from girlframe.services.m3_class_retention import proof

    _, chain = proof(game, c, state, paid)
    _registry(game)
    if len(chain) > 1:
        registry = Access(game.store).registry
        assert registry is not None
        registry.require_available("core.core.frame-requisitions")
    return chain


def _proof(game: "GameService", c: Connection, state: GameState, value: rules.Authority) -> None:
    if rules.authority(state, value.issuer, value.target) != value:
        raise WorkflowError(
            "Restore the exact original Succubus receipt, Frame and qualifying Bond"
        )
    paid = rules.held(state, value.issuer)
    assert paid is not None
    _paid_source(game, c, state, paid)


def issue_authority(
    game: "GameService", c: Connection, state: GameState, issuer: int, target: int
) -> dict[str, Any] | None:
    if higher(state, issuer, target):
        return None
    value = rules.authority(state, current_ref(state, issuer), current_ref(state, target))
    _proof(game, c, state, value)
    return value.model_dump(mode="json")


def valid_order(game: "GameService", c: Connection, state: GameState, row: dict[str, Any]) -> bool:
    raw = json.loads(row["body_json"]).get("succubus")
    if not raw:
        return False
    value = rules.Authority.model_validate(raw)
    if (value.issuer, value.target) != (
        current_ref(state, int(row["issuer_id"])),
        current_ref(state, int(row["target_id"])),
    ):
        raise WorkflowError("Recover the actual original issuer and exact Girl recipient")
    _proof(game, c, state, value)
    return True


def _history(game: "GameService", c: Connection, event: str) -> GameState:
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if body is None:
        raise WorkflowError("Recover the original immutable NPC Order source")
    return GameState.model_validate_json(body)


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], *, active: bool
) -> rules.Order:
    value = rules.Order.model_validate_json(json.dumps(action["data"]["succubus_npc_order"]))
    original = _history(game, c, value.event)
    fact = next(
        (
            x
            for x in original.facts
            if x.get("kind") == "succubus_npc_order" and x.get("id") == value.id
        ),
        None,
    )
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    bindings = profiles(c, game.store.campaign_id)
    issuer, recipient = (
        resolve(state, ref, bindings, require_current_profile=False)
        for ref in (value.issuer, value.target)
    )
    row = (
        c.execute(
            sa.select(t.m2["m2_orders"]).where(
                t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_orders"].c.id == value.id,
            )
        )
        .mappings()
        .first()
    )
    if (
        fact is None
        or rules.Order.model_validate_json(fact["body"]) != value
        or audit is None
        or audit.kind != "m3.succubus_npc_order_issued"
        or audit.actor_id != value.issuer.entity
        or value.registry != _registry(game)
        or value.action != action["id"]
        or str(value.controller) != action["actor_id"]
        or value.cast.id != action["scene_id"]
        or str(value.cast.channel) != action["channel_id"]
        or recipient.controller != value.controller
        or recipient.rules != "npc"
        or issuer.ref != current_ref(state, int(value.issuer.entity))
        or fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast)
        or row is None
        or row["target_id"] != "npc:" + value.target.entity
        or row["issuer_id"] != value.issuer.entity
        or json.loads(row["body_json"]).get("succubus_npc_order") != value.model_dump(mode="json")
        or value.handler != active_handler(state)
        or HandlerService(game.store).current(c)[1].handler_id != int(value.handler.entity)
    ):
        raise WorkflowError(
            "Recover the original real NPC, controller, table and Handler Order source"
        )
    rules.npc(state, value.target)
    for loss in rules.rank_losses(state, value.target):
        birth = _history(game, c, loss.event)
        if loss not in rules.rank_losses(birth, value.target):
            raise WorkflowError("Recover the actual original NPC Status-loss source")
    if active:
        if value.authority is not None:
            _proof(game, c, state, value.authority)
        elif not rules.ordinary_higher(state, value.issuer, value.target):
            raise WorkflowError(
                "This actual Order no longer has ordinary expanded Status authority"
            )
    return value


def validate_role_case(
    c: Connection, game: "GameService", state: GameState, case: "RolePunishment"
) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    offender = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if case.action is None:
        raise WorkflowError("Recover the actual NPC refusal action")
    action = game.action(c, case.action)
    value = _source(game, c, state, action, active=False)
    review = action["data"].get("handler_review", {})
    if (
        case.source_kind != "succubus_npc_disobey"
        or offender != value.target
        or case.executor != value.handler
        or case.chooser != value.handler
        or case.chooser_controller != int(value.handler.entity)
        or case.executor_controller != int(value.handler.entity)
        or case.subject_controller != value.controller
        or case.source_event != review.get("event")
        or action["data"].get("punishment") != case.id
        or not review.get("punish")
        or not action["data"].get("receipt")
    ):
        raise WorkflowError("Recover the genuine Handler-discovered NPC refusal Punishment")


def complete_role_case(
    c: Connection, game: "GameService", case: "RolePunishment", event: str
) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if case.completion_event != event or not case.effect_event:
        raise WorkflowError("Complete the actual NPC Punishment effect first")
    assert case.action is not None
    action = game.action(c, case.action)
    if action["state"] != "complete":
        _finish(game, c, action)


def _finish(game: "GameService", c: Connection, action: dict[str, Any]) -> None:
    action["state"] = "complete"
    action["data"]["phase"] = "complete"
    game.save_action(c, action)
    table = t.m2["m2_orders"]
    c.execute(
        table.update()
        .where(
            table.c.campaign_id == game.store.campaign_id, table.c.id == action["data"]["order_id"]
        )
        .values(state="complete")
    )
    value = rules.Order.model_validate_json(json.dumps(action["data"]["succubus_npc_order"]))
    game.queue(
        c,
        action,
        "outcome",
        dict(
            play="receive_orders",
            callsign="NPC Order response",
            result=action["data"]["result"],
            npc_recipient=value.target.entity,
        ),
    )


class SuccubusService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer, subsystem: str = "plays") -> None:
        Access(self.store).authorize(c, viewer, subsystem, director_response=True)
        _registry(self.game)

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            try:
                actor = current_ref(state, viewer.user_id)
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
                _registry(self.game)
            except (ValueError, KeyError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
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
            chain = _paid_source(self.game, c, state, paid) if paid else ()
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                kind=kind,
                price=price,
                permissions=available(state, actor),
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                owned=paid is not None,
                suspended=any(suspended(state, identity) for identity in chain),
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
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._access(c, viewer, "economy")
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if (
                state.revision != revision
                or actor != current_ref(state, viewer.user_id)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual original Succubus acquisition")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if current != frame or available(state, actor) < price:
                raise WorkflowError("Use the actual current Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.rule_id == rules.RULE
                and grafts.eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError("Restore the original Succubus source instead of buying twice")
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
                    grant="succubus:" + identity,
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
            "m3.succubus_purchased",
            dict(
                revision=revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                account=account,
                donor_frame=donor_frame,
            ),
            change,
            authorize=lambda c: self._access(c, viewer, "economy"),
            auto_audit=False,
        )

    def targets(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            cast = _cast(self.game, c, state, channel)
            if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles):
                raise WorkflowError("Your actual original Pilot must be present in this scene")
            candidates = []
            for role in cast.roles:
                if role.actor.kind != "npc":
                    continue
                try:
                    npc = rules.npc(state, role.actor)
                    if not (
                        npc.revealed
                        or npc.controller == viewer.user_id
                        or depth(state, actor, role.actor) > 0
                    ):
                        continue
                    if not rules.ordinary_higher(state, actor, role.actor):
                        _proof(self.game, c, state, rules.authority(state, actor, role.actor))
                    actual = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                except ValueError:
                    continue
                candidates.append(
                    dict(
                        actor=role.actor.model_dump(mode="json"),
                        label=actual.label,
                        token=role.actor.token,
                        controller=role.controller,
                        rank=rules.expanded_status(state, role.actor),
                    )
                )
            return dict(revision=state.revision, cast=fingerprint(cast), targets=candidates)

    def issue_npc(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        target: ActorRef,
        cast_sha: str,
        text: str,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            cast = _cast(self.game, c, state, channel)
            bindings = profiles(c, self.store.campaign_id)
            actual = resolve(state, target, bindings)
            if (
                state.revision != revision
                or fingerprint(cast) != cast_sha
                or not text.strip()
                or len(text) > 1200
                or not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles)
                or not any(
                    x.actor == target and x.controller == actual.controller for x in cast.roles
                )
            ):
                raise WorkflowError("Reopen the real NPC recipient and original scene cast")
            rules.npc(state, target)
            if actual.rules != "npc":
                raise WorkflowError("This recipient needs its own actual rules consumer")
            authority = (
                None
                if rules.ordinary_higher(state, actor, target)
                else rules.authority(state, actor, target)
            )
            if authority:
                _proof(self.game, c, state, authority)
            handler = active_handler(state)
            if handler is None:
                raise WorkflowError("Recover the actual original appointed Handler")
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: resolve the current action first")
            identity, order_id, event = str(uuid4()), str(uuid4()), str(uuid4())
            value = rules.Order(
                id=order_id,
                action=identity,
                issuer=actor,
                target=target,
                controller=actual.controller,
                handler=handler,
                cast=cast,
                authority=authority,
                instruction=text,
                event=event,
                registry=_registry(self.game),
            )
            body = dict(text=text, succubus_npc_order=value.model_dump(mode="json"))
            c.execute(
                t.m2["m2_orders"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=order_id,
                    issuer_id=str(viewer.user_id),
                    target_id="npc:" + target.entity,
                    channel_id=str(channel),
                    body_json=json.dumps(body),
                    state="awaiting_response",
                )
            )
            data = dict(
                play="receive_orders",
                succubus_npc_order=value.model_dump(mode="json"),
                order_id=order_id,
                participants=sorted({x.controller for x in cast.roles} | {int(handler.entity)}),
                phase="response",
                receipt=None,
                result={},
                modifiers=[],
                choices={},
            )
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(actual.controller),
                    channel_id=str(channel),
                    scene_id=cast.id,
                    parent_id=None,
                    revision=1,
                    state="awaiting_choices",
                    body_json=json.dumps(data),
                )
            )
            table = t.m2["m2_locks"]
            values = dict(
                action_id=identity,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
            if lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            state.facts.append(
                dict(kind="succubus_npc_order", id=order_id, body=value.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.succubus_npc_order_issued",
                state,
                event_id=event,
                action_id=identity,
                order_id=order_id,
            )
            return dict(action_id=identity, order_id=order_id)

        return self.store._write(
            viewer,
            key,
            "m3.succubus_npc_order_issued",
            dict(
                channel=channel,
                revision=revision,
                target=target.model_dump(mode="json"),
                cast_sha=cast_sha,
                text=text,
            ),
            change,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def _owner(self, action: dict[str, Any]) -> int:
        value = rules.Order.model_validate_json(json.dumps(action["data"]["succubus_npc_order"]))
        phase = action["data"]["phase"]
        return (
            int(value.handler.entity)
            if phase in ("handler", "punishment")
            else action["data"]["follower_controller"]
            if phase == "follower"
            else value.controller
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        result = []
        for row in c.execute(
            sa.select(t.m2["m2_actions"]).where(
                t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_actions"].c.state != "complete",
            )
        ).mappings():
            data = json.loads(row["body_json"])
            if not data.get("succubus_npc_order") or data["phase"] == "punishment":
                continue
            action = self.game.action(c, row["id"])
            if viewer.user_id == self._owner(action):
                result.append(
                    dict(
                        id=action["id"],
                        revision=action["revision"],
                        phase=data["phase"],
                        label="NPC Order — " + data["phase"],
                        subject=rules.Order.model_validate_json(
                            json.dumps(data["succubus_npc_order"])
                        ).target.entity,
                    )
                )
        return result

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            action = self.game.action(c, identity)
            state = load_state(c, self.store.campaign_id)
            value = _source(self.game, c, state, action, active=False)
            completed_reader = action["data"]["phase"] == "complete" and viewer.user_id in {
                value.controller,
                int(value.issuer.entity),
                int(value.handler.entity),
            }
            if viewer.user_id != self._owner(action) and not completed_reader:
                raise WorkflowError(
                    "The actual original recipient, follower or Handler owns this choice"
                )
            actual = rules.npc(state, value.target)
            return dict(
                id=identity,
                revision=action["revision"],
                phase=action["data"]["phase"],
                target=actual.name,
                instruction=value.instruction,
                receipt=action["data"]["receipt"],
                result=action["data"]["result"],
                tags=[dict(id=x.id, label=x.label) for x in actual.tags if not x.rejection_pending],
                followers=[
                    dict(
                        actor=x.actor.model_dump(mode="json"),
                        token=x.actor.token,
                        controller=x.controller,
                        label=resolve(
                            state,
                            x.actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        ).label,
                    )
                    for x in value.cast.roles
                    if x.actor != value.target
                    and x.actor.kind in ("pilot", "npc", "handler")
                    and (
                        x.actor.kind != "npc"
                        or rules.npc(state, x.actor).revealed
                        or x.controller == viewer.user_id
                        or depth(state, value.target, x.actor) > 0
                    )
                ],
                witnesses=[
                    dict(
                        actor=x.actor.model_dump(mode="json"),
                        token=x.actor.token,
                        label=resolve(
                            state,
                            x.actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        ).label,
                    )
                    for x in value.cast.roles
                    if x.actor != value.target
                    and (
                        x.actor.kind in ("pilot", "handler")
                        or x.actor.kind == "npc"
                        and rules.npc(state, x.actor).employment == "foundation"
                    )
                ],
                rank=rules.expanded_status(state, value.target),
            )

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        option: str,
        account: str,
        *,
        tag: str | None = None,
        selected: ActorRef | None = None,
        flag: bool | None = None,
        knows: bool | None = None,
        punish: bool | None = None,
        heat_gain: int | None = None,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            action = self.game.action(c, identity)
            phase = action["data"]["phase"]
            value = _source(self.game, c, state, action, active=phase in ("response", "roll"))
            lock = self.game.lock(c, action["channel_id"])
            if (
                action["revision"] != revision
                or action["state"] == "complete"
                or viewer.user_id != self._owner(action)
                or not account.strip()
                or len(account) > 1200
                or not lock
                or lock["state"] != "held"
                or lock["action_id"] != identity
            ):
                raise WorkflowError("Reopen this owned real NPC Order after its scene lock is held")
            data = action["data"]
            result = data["result"]
            event = str(uuid4())
            if phase == "response":
                if option not in dict(rules.RESPONSES) and option != "disobey":
                    raise WorkflowError("Choose the NPC's real Receive Orders response")
                result.update(response=option, response_account=account)
                if option == "disobey":
                    data["phase"] = "roll"
                else:
                    _finish(self.game, c, action)
            elif phase == "roll":
                if option != "roll" or data["receipt"] is not None:
                    raise WorkflowError("Confirm this exact actual NPC refusal once")
                faces = self.game.dice.roll()
                if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                    raise WorkflowError("The dice source returned invalid faces")
                receipt = dict(
                    id=str(uuid4()),
                    action_id=identity,
                    faces=list(faces),
                    actor=value.target.model_dump(mode="json"),
                    controller=value.controller,
                    heat=None,
                    heat_spent=0,
                    pre_total=sum(faces),
                    rng_source=self.game.rng_source,
                    rolled_utc=datetime.now(UTC).isoformat(),
                    basis="ordinary_npc_no_heat",
                    rule_id=rules.RULE,
                    source_order=value.id,
                    event=event,
                )
                c.execute(
                    t.m2["m2_receipts"]
                    .insert()
                    .values(
                        campaign_id=self.store.campaign_id,
                        action_id=identity,
                        id=receipt["id"],
                        body_json=json.dumps(receipt),
                    )
                )
                data["receipt"] = receipt
                result.update(
                    tier=rules.tier(sum(faces)),
                    total=sum(faces),
                    can_disobey=sum(faces) >= 8,
                    roll_account=account,
                )
                data["phase"] = "result"
            elif phase == "result":
                level = result["tier"]
                if level == "low":
                    if option not in dict(rules.RESPONSES):
                        raise WorkflowError(
                            "The NPC cannot disobey: choose its actual follow response"
                        )
                    result.update(can_disobey=False, failed_response=option)
                elif level == "high":
                    if option != "act_now" or flag is not True:
                        raise WorkflowError(
                            "High refusal requires actual immediate action without thinking"
                        )
                    result.update(acted_now=True, heat_gain_applied=0, heat_resource=None)
                elif option == "tag_heat":
                    if heat_gain not in (1, 2):
                        raise WorkflowError(
                            "Choose the printed one or two Heat; this NPC has no Heat pool"
                        )
                    rules.tag(state, value.target, str(uuid4()), account)
                    result.update(
                        tag=account,
                        printed_heat_gain=heat_gain,
                        heat_gain_applied=0,
                        heat_resource=None,
                    )
                elif option == "reject_tag":
                    if tag is None:
                        raise WorkflowError("Choose an actual owned NPC Tag")
                    rules.reject(state, value.target, tag)
                    result["rejected_tag"] = tag
                elif option == "follow":
                    role = next(
                        (
                            x
                            for x in value.cast.roles
                            if x.actor == selected
                            and x.actor != value.target
                            and x.actor.kind in ("pilot", "npc", "handler")
                        ),
                        None,
                    )
                    if role is None:
                        raise WorkflowError(
                            "Tell an actual other person in this scene to follow you"
                        )
                    data["follower"] = role.actor.model_dump(mode="json")
                    data["follower_controller"] = role.controller
                    data["phase"] = "follower"
                else:
                    raise WorkflowError("Choose one actual printed mid refusal consequence")
                result["result_account"] = account
                if data["phase"] != "follower":
                    data["phase"] = "handler"
            elif phase == "follower":
                if option != "follow" or flag is None:
                    raise WorkflowError(
                        "The actual other person's controller decides whether to follow immediately"
                    )
                follower = ActorRef.model_validate(data["follower"])
                actual = resolve(
                    state,
                    follower,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if actual.controller != viewer.user_id:
                    raise WorkflowError(
                        "Recover the actual original follower and its current controller"
                    )
                result.update(
                    follower=follower.model_dump(mode="json"),
                    followed=flag,
                    follower_account=account,
                )
                data["phase"] = "handler"
            elif phase == "handler":
                if option != "review" or knows is None:
                    raise WorkflowError(
                        "The actual original Handler must record discovery and actual notice"
                    )
                if selected is not None:
                    role = next((x for x in value.cast.roles if x.actor == selected), None)
                    is_foundation = selected.kind in ("pilot", "handler")
                    if selected.kind == "npc":
                        is_foundation = rules.npc(state, selected).employment == "foundation"
                    if role is None or not is_foundation:
                        raise WorkflowError(
                            "Select an actual Foundation member in this source scene who noticed"
                        )
                    before = rules.expanded_status(state, value.target)
                    rules.lower_status(
                        state,
                        rules.RankLoss(
                            target=value.target,
                            action=identity,
                            witness=selected,
                            handler=value.handler,
                            before=before,
                            after=before + 1,
                            event=event,
                        ),
                    )
                must_punish = knows and result["tier"] != "low"
                if punish is None or must_punish and not punish or punish and not knows:
                    raise WorkflowError(
                        "Discovered successful refusal requires a real Handler Punishment"
                    )
                review = dict(
                    event=event,
                    account=account,
                    knows=knows,
                    punish=punish,
                    witness=selected.model_dump(mode="json") if selected else None,
                )
                data["handler_review"] = review
                result.update(
                    handler_knows=knows, punished=punish, status_lowered=selected is not None
                )
                if punish:
                    from girlframe.services.m3_role_punishments import open_case

                    case_id = str(uuid4())
                    state, _ = open_case(
                        state,
                        profiles(c, self.store.campaign_id),
                        actor=value.handler,
                        target=value.target,
                        chooser=value.handler,
                        source_kind="succubus_npc_disobey",
                        action=identity,
                        source_event=event,
                        identity=case_id,
                    )
                    data["punishment"] = case_id
                    data["phase"] = "punishment"
                else:
                    _finish(self.game, c, action)
            else:
                raise WorkflowError(
                    "Complete the actual Handler-owned Punishment rather than acknowledge it"
                )
            self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.succubus_npc_" + phase,
                state,
                event_id=event,
                action_id=identity,
                order_id=value.id,
            )
            return dict(
                action_id=identity,
                phase=data["phase"],
                receipt=data["receipt"],
                punishment=data.get("punishment"),
            )

        return self.store._write(
            viewer,
            key,
            "m3.succubus_npc_choice",
            dict(
                identity=identity,
                revision=revision,
                option=option,
                account=account,
                tag=tag,
                selected=selected.model_dump(mode="json") if selected else None,
                flag=flag,
                knows=knows,
                punish=punish,
                heat_gain=heat_gain,
            ),
            change,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )
