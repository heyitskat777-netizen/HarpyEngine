"""Actual NPC-issued Orders and genuine Pilot refusal use the existing shared protocol."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_orders as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_alpha import RULE
from girlframe.engine.m3_alpha_state import Broken
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_enforcement_initiative import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(game: GameService, c: Connection, event: str) -> GameState:
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if body is None:
        raise WorkflowError("Recover the actual original NPC order source history")
    return GameState.model_validate_json(body)


def _condition(
    game: GameService, c: Connection, state: GameState, issuer: ActorRef, target: ActorRef
) -> Broken:
    try:
        found = rules.authority(state, issuer, target)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    original = next(
        (x for x in _history(game, c, found.source_event).alpha_broken if x.id == found.id), None
    )
    if original != found:
        raise WorkflowError("Recover the actual original source of this NPC's Broken condition")
    return found


def _access(
    game: GameService, c: Connection, viewer: GuildViewer, origin_kind: rules.Origin = "broken"
) -> None:
    access = Access(game.store)
    access.authorize(c, viewer, "plays", director_response=True)
    assert access.registry is not None
    rule = {
        "broken": RULE,
        "am_secret": "girl.am.scrutinized",
        "secretary": "handler-advancement.handler-advancement.secretary",
        "npc_flirt": "play.basic.flirt",
    }[origin_kind]
    access.registry.require_available(rule)


def source(
    game: GameService,
    c: Connection,
    state: GameState,
    value: rules.Order,
    *,
    removal_action: str | None = None,
) -> None:
    approval = game.store.policy.m3_approval
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.event,
        )
    ).first()
    original = _history(game, c, value.event)
    recorded = next(
        (
            x
            for x in original.facts
            if x.get("kind")
            == {
                "broken": "npc_broken_order",
                "am_secret": "npc_am_secret_order",
                "secretary": "npc_secretary_order",
                "npc_flirt": "npc_flirt_order",
            }[value.origin_kind]
            and x.get("id") == value.id
        ),
        None,
    )
    actual = resolve(state, value.issuer, profiles(c, game.store.campaign_id))
    recipient = resolve(state, value.target, profiles(c, game.store.campaign_id))
    if value.origin_kind == "npc_flirt":
        from girlframe.services.m3_npc_flirt import cannot_refuse

        condition_invalid = (
            cannot_refuse(game, c, original, value.target, value.issuer) != value.condition
        )
    elif value.origin_kind == "secretary":
        from girlframe.services.m3_secretary import prove_order

        prove_order(game, c, state, value)
        condition_invalid = False
    elif value.origin_kind == "am_secret":
        from girlframe.services.m3_am_scrutinized import prove_order_grant

        prove_order_grant(game, c, state, value)
        condition_invalid = False
    else:
        condition = next((x for x in state.alpha_broken if x.id == value.condition), None)
        birth = _condition(game, c, original, value.issuer, value.target)
        condition_invalid = (
            birth.id != value.condition
            or condition is None
            or condition.subject != value.target
            or condition.inflictor != value.issuer
            or condition.source_event != birth.source_event
            or condition.removed_event is not None
            and (removal_action is None or condition.removed_action != removal_action)
        )
    if (
        approval is None
        or value.registry != approval.registry_sha256
        or audit is None
        or audit.kind != "m3.npc_order_issued"
        or audit.actor_id != str(value.controller)
        or recorded is None
        or rules.Order.model_validate_json(recorded["body"]) != value
        or value.origin_kind != "secretary"
        and actual.controller != value.controller
        or recipient.controller != int(value.target.entity)
        or fingerprint(_cast(game, c, state, value.cast.channel)) != fingerprint(value.cast)
        or condition_invalid
    ):
        raise WorkflowError("Recover this original NPC, recipient, cast and Broken-source order")


def order(game: GameService, c: Connection, action: dict[str, Any]) -> rules.Order:
    identity = action["data"].get("order_id") or action["data"].get("prepared", {}).get("order_id")
    raw = c.scalar(
        sa.select(t.m2["m2_orders"].c.body_json).where(
            t.m2["m2_orders"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_orders"].c.id == identity,
        )
    )
    body = json.loads(raw) if raw else {}
    if not body.get("npc_order"):
        raise WorkflowError("Recover the actual NPC source order")
    value = rules.Order.model_validate_json(json.dumps(body["npc_order"]))
    if (
        action["data"].get("npc_order") != value.model_dump(mode="json")
        or body.get("text") != value.instruction
        or action["actor_id"] != value.target.entity
        or int(action["channel_id"]) != value.cast.channel
        or action["scene_id"] != value.cast.id
        or action["data"]["play"] == "receive_orders"
        and (action["id"] != value.action or action["data"].get("order_text") != value.instruction)
        or action["data"]["play"] != "receive_orders"
        and (action["data"]["play"] != "disobey_orders" or action["parent_id"] != value.action)
    ):
        raise WorkflowError("The actual original NPC Order binding changed")
    return value


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    value = order(game, c, action)
    _access(game, c, viewer, value.origin_kind)
    if viewer.user_id not in action["data"]["participants"]:
        raise WorkflowError("Only the original source table owns this NPC Order response")
    source(game, c, load_state(c, game.store.campaign_id), value, removal_action=action["id"])


def prepare(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    channel: int,
    prepared: PlayInput,
) -> dict[str, Any] | None:
    if prepared.play != "disobey_orders" or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    if not parent["data"].get("npc_order"):
        return None
    authorize(game, c, viewer, parent)
    value = order(game, c, parent)
    if value.target.entity != str(viewer.user_id) or prepared.order_id != value.id:
        raise WorkflowError("Only this original Pilot may refuse this exact NPC order")
    if channel != value.cast.channel:
        raise WorkflowError("Use the actual original NPC Order scene")
    _allow_refusal(game, c, state, value)
    return value.model_dump(mode="json")


def _allow_refusal(game: GameService, c: Connection, state: GameState, value: rules.Order) -> None:
    if value.origin_kind == "npc_flirt":
        from girlframe.services.m3_npc_flirt import cannot_refuse

        if cannot_refuse(game, c, state, value.target, value.issuer) is not None:
            raise WorkflowError("Resolve the actual NPC-given Tag before refusing this NPC")


def valid_order(
    game: GameService,
    c: Connection,
    state: GameState,
    owner: int,
    channel: int,
    row: dict[str, Any],
) -> bool:
    body = json.loads(row["body_json"])
    if not body.get("npc_order"):
        return False
    value = rules.Order.model_validate_json(json.dumps(body["npc_order"]))
    source(game, c, state, value)
    if (
        row["issuer_id"] != value.issuer.entity
        or row["target_id"] != str(owner)
        or value.target.entity != str(owner)
        or row["id"] != value.id
        or row["state"] != "disobey"
        or channel != value.cast.channel
    ):
        raise WorkflowError("Use only this original recipient's actual refused NPC Order")
    _allow_refusal(game, c, state, value)
    parent = game.action(c, value.action)
    if parent["data"].get("npc_order") != value.model_dump(mode="json"):
        raise WorkflowError("Recover the original NPC Order action")
    return True


def removable(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> tuple[ActorRef, ActorRef]:
    value = order(game, c, action)
    source(game, c, state, value)
    if action["data"]["play"] != "disobey_orders" or action["parent_id"] != value.action:
        raise WorkflowError("Only the genuine original Disobey may remove this NPC-source Broken")
    return value.target, value.issuer


class NpcOrderService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def preview(
        self,
        viewer: GuildViewer,
        channel: int,
        target: int,
        *,
        origin_kind: rules.Origin = "broken",
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, origin_kind)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            if str(target) not in state.sheets:
                return dict(revision=state.revision, issuers=[])
            recipient = ActorRef(
                kind="pilot", entity=str(target), incarnation=state.sheets[str(target)].character_id
            )
            issuers = []
            for role in cast.roles:
                if role.actor.kind != "npc" or role.controller != viewer.user_id:
                    continue
                try:
                    if origin_kind == "npc_flirt":
                        from girlframe.services.m3_npc_flirt import cannot_refuse

                        condition_id = cannot_refuse(self.game, c, state, recipient, role.actor)
                        if condition_id is None:
                            continue
                    else:
                        condition_id = _condition(self.game, c, state, role.actor, recipient).id
                except (ValueError, WorkflowError):
                    continue
                if not any(x.actor == recipient for x in cast.roles):
                    continue
                issuers.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        label=resolve(state, role.actor, ()).label,
                        condition=condition_id,
                    )
                )
            return dict(revision=state.revision, issuers=issuers)

    def issue(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        issuer: ActorRef,
        target: int,
        expected: int,
        text: str,
        *,
        origin_kind: rules.Origin = "broken",
    ) -> dict[str, Any]:
        if origin_kind not in ("broken", "am_secret", "secretary", "npc_flirt"):
            raise WorkflowError("Use only an implemented actual NPC order source")
        if not text.strip() or len(text) > 1200:
            raise WorkflowError("State the actual direct order in 1–1200 characters")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            scene = self.game.scene(c, channel)
            cast = _cast(self.game, c, state, channel)
            if str(target) not in state.sheets:
                raise WorkflowError("Choose the actual active original Pilot receiving this order")
            recipient = ActorRef(
                kind="pilot", entity=str(target), incarnation=state.sheets[str(target)].character_id
            )
            principal = None
            if origin_kind == "npc_flirt":
                from girlframe.services.m3_npc_flirt import cannot_refuse

                condition_id = cannot_refuse(self.game, c, state, recipient, issuer)
                if condition_id is None:
                    raise WorkflowError("Use the actual NPC-given unresolved Tag source")
            elif origin_kind == "secretary":
                from girlframe.services.m3_secretary import order_authority

                authority = order_authority(self.game, c, state, issuer, recipient, viewer.user_id)
                condition_id = authority.id
                principal = authority.handler
            elif origin_kind == "am_secret":
                from girlframe.services.m3_am_scrutinized import secret_authority

                condition_id = secret_authority(self.game, c, state, issuer, recipient).id
            else:
                condition_id = _condition(self.game, c, state, issuer, recipient).id
            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or not any(
                    x.actor == issuer
                    and (origin_kind == "secretary" or x.controller == viewer.user_id)
                    for x in cast.roles
                )
                or not any(x.actor == recipient and x.controller == target for x in cast.roles)
            ):
                raise WorkflowError("STALE_NPC_ORDER: reopen the original NPC and Broken recipient")
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("SCENE_BUSY: finish the actual pending Play")
            event, action, identity = str(uuid4()), str(uuid4()), str(uuid4())
            assert self.store.policy.m3_approval is not None
            value = rules.Order(
                id=identity,
                action=action,
                issuer=issuer,
                target=recipient,
                controller=viewer.user_id,
                condition=condition_id,
                origin_kind=origin_kind,
                event=event,
                cast=cast,
                registry=self.store.policy.m3_approval.registry_sha256,
                instruction=text,
                principal=principal,
            )
            c.execute(
                t.m2["m2_orders"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    issuer_id=issuer.entity,
                    target_id=str(target),
                    channel_id=str(channel),
                    state="awaiting_response",
                    body_json=json.dumps(dict(text=text, npc_order=value.model_dump(mode="json"))),
                )
            )
            table = sorted(
                {x.controller for x in cast.roles}
                | ({cast.facilitator} if cast.facilitator is not None else set())
            )
            handler = active_handler(state)
            data = dict(
                play="receive_orders",
                order_id=identity,
                order_text=text,
                npc_order=value.model_dump(mode="json"),
                participants=table,
                character_ids={
                    str(x.controller): x.actor.incarnation
                    for x in cast.roles
                    if x.actor.kind == "pilot"
                },
                handler=state.handler,
                depth=0,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
                tag_context=dict(
                    actor=recipient.model_dump(mode="json"),
                    handler=handler.model_dump(mode="json") if handler else None,
                    gm_controller=state.handler,
                    table=table,
                    cast=cast.model_dump(mode="json"),
                    cast_sha256=fingerprint(cast),
                ),
            )
            from girlframe.services.m3_recovery import enable

            enable(self.game, c, viewer, data)
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=action,
                    actor_id=str(target),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            values = dict(
                action_id=action, state="acquiring", body_json="{}", lease_until=0, claim_token=None
            )
            locks = t.m2["m2_locks"]
            if lock:
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            state.facts.append(
                dict(
                    kind={
                        "broken": "npc_broken_order",
                        "am_secret": "npc_am_secret_order",
                        "secretary": "npc_secretary_order",
                        "npc_flirt": "npc_flirt_order",
                    }[origin_kind],
                    id=identity,
                    body=value.model_dump_json(),
                )
            )
            if origin_kind == "secretary":
                from girlframe.services.m3_secretary import record_authority

                record_authority(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_order_issued",
                state,
                event_id=event,
                action_id=action,
                order_id=identity,
            )
            return dict(action_id=action, order_id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.npc_order_issued",
            dict(
                channel=channel,
                issuer=issuer.model_dump(mode="json"),
                target=target,
                expected=expected,
                text=text,
            )
            | (dict(origin_kind=origin_kind) if origin_kind != "broken" else {}),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer, origin_kind),
        )
