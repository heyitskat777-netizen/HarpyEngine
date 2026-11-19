"""Resolve playbook reactions against the original direct Handler order."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m3_access import Access, digest

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def direct_order_source(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    book: str,
    rule: str,
    order_state: str,
) -> dict[str, Any] | None:
    persona = state.handler_persona
    handler = active_handler(state)
    if persona is None or persona.draft.playbook != book or handler is None:
        return None
    policy = game.store.policy.m3_approval
    if (
        policy is None
        or "plays" not in policy.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return None
    registry = Access(game.store).registry
    if registry is None or digest(registry) != policy.registry_sha256:
        return None
    entry = registry.entry(rule)
    if (
        entry.implementation == "unimplemented"
        or entry.module not in registry.enabled_modules
        or (policy.scope == "core_complete" and not entry.verified)
        or HandlerService(game.store).current(c)[1].handler_id != int(handler.entity)
    ):
        return None
    data = action["data"]
    order_id = data.get("order_id") or data.get("prepared", {}).get("order_id")
    if not order_id or not action["actor_id"].isdigit():
        return None
    root = action
    if data.get("play") != "receive_orders":
        if not action["parent_id"]:
            return None
        root = game.action(c, action["parent_id"])
    if (
        root["data"].get("play") != "receive_orders"
        or root["data"].get("order_id") != order_id
        or root["actor_id"] != action["actor_id"]
        or root["scene_id"] != action["scene_id"]
        or int(handler.entity) not in root["data"]["participants"]
    ):
        return None
    table = t.m2["m2_orders"]
    order = c.execute(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == order_id,
            table.c.issuer_id == handler.entity,
            table.c.state == order_state,
            table.c.target_id == action["actor_id"],
            table.c.channel_id == action["channel_id"],
        )
    ).scalar_one_or_none()
    if order is None or json.loads(order).get("npc_order"):
        return None
    events = t.events
    activation = c.scalar(
        sa.select(events.c.seq).where(
            events.c.campaign_id == game.store.campaign_id,
            events.c.id == persona.source_event,
            events.c.kind == "m3.handler_activated",
            events.c.actor_id == handler.entity,
        )
    )
    if activation is None:
        return None
    issued = c.scalars(
        sa.select(events.c.payload_json).where(
            events.c.campaign_id == game.store.campaign_id,
            events.c.seq > activation,
            events.c.kind == "m2.order_issued",
            events.c.actor_id == handler.entity,
            events.c.payload_json.contains(root["id"], autoescape=True),
        )
    )
    if not any(json.loads(payload).get("action_id") == root["id"] for payload in issued):
        return None
    target = current_ref(state, int(action["actor_id"]))
    if target.incarnation != root["data"]["character_ids"].get(target.entity):
        return None
    return dict(
        handler=handler.model_dump(mode="json"),
        actor=target.model_dump(mode="json"),
        persona=persona.source_event,
        order=order_id,
        rule=rule,
    )
