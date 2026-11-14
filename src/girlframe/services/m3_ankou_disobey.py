"""The original received direct Order survives its receiver's mandatory Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput, higher
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_disposable_psyche import _before
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _command(
    game: "GameService", c: Connection, event: Any, actor: int, kind: str, payload: dict[str, Any]
) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.commands).where(
                t.commands.c.campaign_id == game.store.campaign_id,
                t.commands.c.interaction_key == event["command_key"],
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or event["actor_id"] != str(actor)
        or row["request_hash"] != _sha(dict(actor=actor, kind=kind, payload=payload))
    ):
        raise WorkflowError("Recover the original direct Order and its actual authored response")
    return dict(json.loads(row["outcome_json"]))


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Prove one ordinary Receive Orders child without authorizing other child recipes."""
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    if (
        prepared.play != "disobey_orders"
        or not prepared.parent
        or prepared.parent != action.get("parent_id")
        or prepared.source_work is not None
        or any(
            action["data"].get(x)
            for x in (
                "prince_demand_attempt",
                "bonded_rejection_child",
                "virus_disobey",
                "npc_order",
                "vatgrown_leaving",
                "secretary_response",
                "ankou_effect_child",
            )
        )
    ):
        raise WorkflowError("SOURCE_ANKOU_REFUSAL_PORT_REQUIRED: use the actual direct Order child")
    parent = game.action(c, prepared.parent)
    orders, choices = t.m2["m2_orders"], t.m2["m2_choices"]
    order = (
        c.execute(
            sa.select(orders).where(
                orders.c.campaign_id == game.store.campaign_id,
                orders.c.id == prepared.order_id,
            )
        )
        .mappings()
        .first()
    )
    if (
        order is None
        or set(json.loads(order["body_json"])) != {"text"}
        or parent["parent_id"] is not None
        or parent["data"].get("play") != "receive_orders"
        or parent["data"].get("order_id") != order["id"]
        or parent["data"].get("order_text") != json.loads(order["body_json"])["text"]
        or parent["actor_id"] != action["actor_id"]
        or order["target_id"] != action["actor_id"]
        or order["channel_id"] != action["channel_id"]
        or parent["channel_id"] != action["channel_id"]
        or parent["scene_id"] != action["scene_id"]
    ):
        raise WorkflowError(
            "SOURCE_ANKOU_REFUSAL_PORT_REQUIRED: preserve this exact ordinary Order"
        )
    issue = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.order_issued",
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == parent["id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if issue is None:
        raise WorkflowError("Recover the canonical original direct Order issuance")
    issued = _command(
        game,
        c,
        issue,
        int(order["issuer_id"]),
        "m2.order_issued",
        dict(
            channel=int(order["channel_id"]),
            target=int(order["target_id"]),
            text=json.loads(order["body_json"])["text"],
        ),
    )
    original = _before(game, c, issue["id"])
    actor = current_ref(original, int(action["actor_id"]))
    issuer = (
        active_handler(original)
        if order["issuer_id"] == str(original.handler)
        else current_ref(original, int(order["issuer_id"]))
    )
    current_issuer = (
        active_handler(state)
        if order["issuer_id"] == str(state.handler)
        else current_ref(state, int(order["issuer_id"]))
    )
    if (
        issued != dict(action_id=parent["id"], order_id=order["id"])
        or issuer is None
        or issuer != current_issuer
        or actor != current_ref(state, int(action["actor_id"]))
        or parent["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
        or action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
        or not higher(original, int(order["issuer_id"]), int(actor.entity))
    ):
        raise WorkflowError("Preserve the actual original superior and receiving person")
    response = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == parent["id"],
                choices.c.kind == "order_response",
                choices.c.actor_id == actor.entity,
                choices.c.state == "answered",
            )
        )
        .mappings()
        .one_or_none()
    )
    required = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == parent["id"],
                choices.c.kind == "order_disobey",
                choices.c.actor_id == actor.entity,
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        response is None
        or required is None
        or json.loads(required["body_json"]) != {"order_id": order["id"]}
    ):
        raise WorkflowError("Recover the actual receiver-owned refusal and required response")
    answer = ChoiceAnswer.model_validate_json(
        json.dumps(parent["data"]["choices"].get("order_response:" + actor.entity, {}))
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m2.choice_resolved",
                sa.func.json_extract(t.events.c.payload_json, "$.choice_id") == response["id"],
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == parent["id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if event is None or answer.options != ("disobey",):
        raise WorkflowError("Retain the actual receiver's own decision to disobey")
    _command(
        game,
        c,
        event,
        int(actor.entity),
        "m2.choice_resolved",
        dict(
            choice_id=response["id"],
            revision=response["revision"] - 1,
            answer=answer.model_dump(mode="json"),
        ),
    )
    return _sha(
        dict(
            order=dict(
                id=order["id"],
                issuer=issuer.model_dump(mode="json"),
                actor=actor.model_dump(mode="json"),
                body=json.loads(order["body_json"]),
            ),
            parent=parent["id"],
            scene=parent["scene_id"],
            channel=order["channel_id"],
            issued=issue["id"],
            response=event["id"],
            required=required["id"],
            bonuses=action["data"].get("m3_refusal", []),
        )
    )


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m3_ankou_feedback import prove
    from girlframe.services.m3_battle import _cast

    value = prove(game, c, state, action["data"]["ankou_feedback"])
    if value.refusal_source != source_binding(game, c, state, action):
        raise WorkflowError("Preserve the original Feedback-held direct Order refusal")
    if _cast(game, c, state, int(action["channel_id"])) != value.cast:
        raise WorkflowError("Recover the original Feedback-held Order scene and people")
    validate_pending(game, c, state, action)


def validate_pending(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    game.valid_order(
        c, state, int(action["actor_id"]), int(action["channel_id"]), prepared.order_id
    )
    parent = game.action(c, action["parent_id"])
    pending = [
        x
        for x in game.pending(c, parent["id"])
        if x["kind"] == "order_disobey" and x["actor_id"] == action["actor_id"]
    ]
    if len(pending) != 1 or parent["state"] != "awaiting_choices":
        raise WorkflowError("Preserve the original Receive Orders parent and its pending child")
