"""Actual Strain source, first successful native refusal and original Girl ownership."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_control_ritual as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prove(game: "GameService", c: Connection, value: rules.Ritual) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    source = (
        next(
            (x for x in rules.rituals(GameState.model_validate_json(raw)) if x.id == value.id), None
        )
        if raw
        else None
    )
    if (
        row is None
        or row["kind"] != "m3.strain_effect_applied"
        or source is None
        or json.loads(row["payload_json"]).get("rule_id") != rules.RULE
        or json.loads(row["payload_json"]).get("work_id") != value.source_work
        or any(
            getattr(source, k) != getattr(value, k)
            for k in ("source_work", "source_event", "period", "people", "account")
        )
    ):
        raise WorkflowError("Recover the actual original Control Ritual Strain source")
    if value.actor:
        assert value.action is not None
        action = game.action(c, value.action)
        if (
            action["actor_id"] != value.actor.entity
            or action["data"].get("play") != "disobey_orders"
            or action["data"].get("character_ids", {}).get(value.actor.entity)
            != value.actor.incarnation
            or not action["data"]["result"].get("can_disobey")
            or not action["data"].get("receipt")
            or value.id not in action["data"].get("control_rituals", ())
        ):
            raise WorkflowError("Recover the actual original successful refusal")


def offer(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    actor = current_ref(state, int(action["actor_id"]))
    for value in rules.rituals(state):
        if value.actor is None and actor in value.people:
            prove(game, c, value)
            rules.put(state, value.model_copy(update=dict(actor=actor, action=action["id"])))
            action["data"].setdefault("control_rituals", []).append(value.id)
            game.request(
                c, action, int(actor.entity), "control_ritual_create", dict(ritual=value.id)
            )


def choose(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    body: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = next(x for x in rules.rituals(state) if x.id == body["ritual"])
    prove(game, c, value)
    if (
        value.action != action["id"]
        or value.declined
        or value.tag
        or answer.options
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.member is not None
        or answer.flag is None
    ):
        raise WorkflowError("The original successful Girl chooses whether to develop her Ritual")
    if answer.flag and not 1 <= len(answer.text.strip()) <= 120:
        raise WorkflowError("Describe your Control Ritual in 1–120 characters")
    rules.put(
        state,
        value.model_copy(
            update=dict(
                declined=not answer.flag,
                tag=TagState(
                    id=value.id,
                    label=answer.text.strip(),
                    giver=int(value.actor.entity),
                    giver_character=value.actor.incarnation,
                    observers=(int(value.actor.entity),),
                )
                if answer.flag and value.actor
                else None,
                creation_event=action["data"]["response_event"],
            )
        ),
    )


def candidates(state: GameState, action: dict[str, Any], owner: int) -> list[TagState]:
    return (
        rules.tags(state, owner)
        if action["data"]["play"] == "disobey_orders" and action["actor_id"] == str(owner)
        else []
    )


def self_tag(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    tag: TagState,
) -> bool:
    if str(owner) != action["actor_id"] or tag.id not in {
        x.id for x in candidates(state, action, owner)
    }:
        return False
    value = next(x for x in rules.owned(state, owner) if x.tag and x.tag.id == tag.id)
    prove(game, c, value)
    return True
