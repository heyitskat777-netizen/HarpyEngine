"""The original Mistress optionally adjusts an actual Intense Bond refusal."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_access import Access, digest
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.mistress.insidious-conditioning"
CHOICE = "mistress_conditioning"


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any] | None:
    persona = state.handler_persona
    handler = active_handler(state)
    prepared = action["data"].get("prepared", {})
    order_id = prepared.get("order_id")
    if (
        handler is None
        or persona is None
        or persona.draft.playbook != "Mistress"
        or action["data"].get("play") != "disobey_orders"
        or not order_id
        or int(handler.entity) not in action["data"]["participants"]
    ):
        return None
    actor = current_ref(state, int(action["actor_id"]))
    if handler.entity == actor.entity or depth(state, handler, actor) != 2:
        return None
    order = game.valid_order(c, state, int(actor.entity), int(action["channel_id"]), order_id)
    private_order = json.loads(order["body_json"])
    if order["issuer_id"] != handler.entity or private_order.get("npc_order"):
        return None
    proof = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == persona.source_event,
        )
    ).first()
    if proof is None or proof.kind != "m3.handler_activated" or proof.actor_id != handler.entity:
        return None
    return dict(
        handler=handler.model_dump(mode="json"),
        actor=actor.model_dump(mode="json"),
        persona=persona.source_event,
        order=order_id,
        rule=RULE,
    )


def _enabled(game: "GameService") -> bool:
    policy = game.store.policy.m3_approval
    if (
        policy is None
        or "plays" not in policy.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return False
    registry = Access(game.store).registry
    if registry is None or digest(registry) != policy.registry_sha256:
        return False
    entry = registry.entry(RULE)
    return (
        entry.implementation != "unimplemented"
        and entry.module in registry.enabled_modules
        and (policy.scope != "core_complete" or entry.verified)
    )


def offer(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if action["data"].get("play") != "disobey_orders" or state.handler is None:
        return
    source = _source(game, c, state, action)
    if source is not None and _enabled(game):
        game.request(c, action, state.handler, CHOICE, source)


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    proposed = json.loads(request["body_json"])
    owner = int(request["actor_id"])
    if answer.options not in (("apply",), ("pass",)):
        raise WorkflowError("Choose whether to apply Insidious Conditioning")
    if answer.options == ("pass",):
        return
    if not _enabled(game) or state.handler != owner or _source(game, c, state, action) != proposed:
        raise WorkflowError("Recover the original Mistress, actual Intense Bond and direct order")
    action["data"]["modifiers"].append(dict(source=RULE, actor=owner, amount=-2))
