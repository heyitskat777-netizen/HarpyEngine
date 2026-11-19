"""Lift a spoken Conditioning word only after the original trainer is actually refused."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_conditioning as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def trainer_for_refusal(
    game: "GameService",
    c: Connection,
    state: GameState,
    subject: ActorRef,
    channel: int,
    prepared: PlayInput,
) -> ActorRef | None:
    if (
        prepared.play != "disobey_orders"
        or not prepared.parent
        or not prepared.order_id
        or not rules.active_words(state, subject)
    ):
        return None
    parent = game.action(c, prepared.parent)
    if (
        parent["actor_id"] != subject.entity
        or parent["channel_id"] != str(channel)
        or parent["data"]["play"] != "receive_orders"
        or parent["data"]["order_id"] != prepared.order_id
        or parent["data"]["character_ids"].get(subject.entity) != subject.incarnation
    ):
        return None
    row = game.valid_order(c, state, int(subject.entity), channel, prepared.order_id)
    order_body = json.loads(row["body_json"])
    trainer: ActorRef | None
    if order_body.get("npc_order"):
        from girlframe.services.m3_npc_orders import order

        trainer = order(game, c, parent).issuer
    elif order_body.get("virus_purge") or order_body.get("vatgrown_leaving"):
        return None
    elif row["issuer_id"] == str(state.handler):
        trainer = active_handler(state)
        if parent["data"]["handler"] != state.handler:
            return None
    else:
        trainer = current_ref(state, int(row["issuer_id"]))
        if parent["data"]["character_ids"].get(trainer.entity) != trainer.incarnation:
            return None
    if trainer is not None and rules.active_words(state, subject, trainer):
        return trainer
    return None


def release(state: GameState, action: dict[str, Any]) -> None:
    source = action["data"].get("conditioning_refusal")
    if source is None or not (
        action["data"]["play"] == "disobey_orders" and action["data"]["result"].get("can_disobey")
    ):
        return
    subject = ActorRef.model_validate(source["subject"])
    trainer = ActorRef.model_validate(source["trainer"])
    if subject == current_ref(state, int(action["actor_id"])):
        rules.release(state, subject, trainer, action["data"]["response_event"])
