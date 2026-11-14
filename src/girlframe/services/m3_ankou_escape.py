"""One real Flirt escape Keep retains its source across mandatory Ankou Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_disposable_psyche import _before
from girlframe.services.m3_dose_up import _response, _roll_source
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _answer(
    game: "GameService", c: Connection, parent: dict[str, Any], owner: int, kind: str
) -> tuple[str, ChoiceAnswer]:
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(choices.c.id, responses.c.event_id)
            .join(
                responses,
                sa.and_(
                    responses.c.campaign_id == choices.c.campaign_id,
                    responses.c.choice_id == choices.c.id,
                ),
            )
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == parent["id"],
                choices.c.actor_id == str(owner),
                choices.c.kind == kind,
                choices.c.state == "answered",
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise WorkflowError("Recover the actual original Flirt and target-owned escape decision")
    answer = _response(game, c, parent["id"], row["id"], row["event_id"], owner, kind)
    saved = ChoiceAnswer.model_validate_json(
        json.dumps(parent["data"]["choices"].get(kind + ":" + str(owner), {}))
    )
    if answer != saved:
        raise WorkflowError("Preserve each original player's actual Flirt and escape answer")
    return row["event_id"], answer


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Admit ordinary player-to-player Flirt escape Keep, not arbitrary child Plays."""
    prepared = PlayInput.model_validate(action["data"]["prepared"])
    if (
        prepared.play != "keep_your_head"
        or not prepared.parent
        or prepared.parent != action.get("parent_id")
        or prepared.source_work is not None
        or prepared.target is not None
        or prepared.target_actor is not None
        or any(
            action["data"].get(key)
            for key in (
                "princess_child",
                "actor_basic",
                "m3",
                "janus",
                "void_keep",
                "nightmare_core",
                "easy_target_child",
                "ankou_effect_child",
                "consume_child",
                "wyvern_child",
                "red_queen_child",
                "changeling_child",
                "wyvern_pin_response",
                "wyvern_replacement",
                "secretary_response",
            )
        )
    ):
        raise WorkflowError("SOURCE_ANKOU_ESCAPE_PORT_REQUIRED: preserve this specific escape Keep")
    parent = game.action(c, prepared.parent)
    original_play = PlayInput.model_validate(parent["data"]["prepared"])
    if (
        parent["parent_id"] is not None
        or parent["data"].get("play") != "flirt"
        or original_play.play != "flirt"
        or original_play.parent is not None
        or original_play.target != int(action["actor_id"])
        or original_play.target_actor is not None
        or parent["actor_id"] == action["actor_id"]
        or parent["scene_id"] != action["scene_id"]
        or parent["channel_id"] != action["channel_id"]
        or any(
            parent["data"].get(key)
            for key in (
                "actor_basic",
                "princess_child",
                "npc_flirt",
                "m3",
                "ankou_feedback",
            )
        )
    ):
        raise WorkflowError(
            "SOURCE_ANKOU_ESCAPE_PORT_REQUIRED: use the actual ordinary Flirt target"
        )
    roll_event, total = _roll_source(game, c, parent)
    original = _before(game, c, roll_event)
    performer = current_ref(original, int(parent["actor_id"]))
    actor = current_ref(original, int(action["actor_id"]))
    if (
        total < 11
        or parent["data"]["result"].get("tier") != "high"
        or current_ref(state, int(actor.entity)) != actor
        or current_ref(state, int(performer.entity)) != performer
        or parent["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
        or parent["data"].get("character_ids", {}).get(performer.entity) != performer.incarnation
        or action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
    ):
        raise WorkflowError("Recover the actual high Flirt receipt and its original two people")
    chosen_event, chosen = _answer(game, c, parent, int(performer.entity), "actor_flirt")
    target_event, target = _answer(game, c, parent, int(actor.entity), "target_flirt")
    escape_event, escape = _answer(game, c, parent, int(actor.entity), "flirt_escape")
    result = parent["data"]["result"]
    if (
        chosen.fields.get("extra") != "escape"
        or len(chosen.options) != 1
        or result.get("question") != chosen.options[0]
        or result.get("extra") != "escape"
        or result.get("too_far") != chosen.text
        or result.get("target_answer") != target.text
        or escape.options != ("play",)
    ):
        raise WorkflowError(
            "Preserve the original too-far Flirt and the target's chosen escape Play"
        )
    choices = t.m2["m2_choices"]
    required = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == parent["id"],
                choices.c.kind == "escape_play",
                choices.c.actor_id == actor.entity,
            )
        )
        .mappings()
        .one_or_none()
    )
    if required is None or json.loads(required["body_json"]) != {}:
        raise WorkflowError("Recover the genuine original target-owned escape requirement")
    return hashlib.sha256(
        json.dumps(
            dict(
                parent=parent["id"],
                scene=parent["scene_id"],
                channel=parent["channel_id"],
                actor=actor.model_dump(mode="json"),
                performer=performer.model_dump(mode="json"),
                prepared=original_play.model_dump(mode="json"),
                roll=roll_event,
                receipt=parent["data"]["receipt"]["id"],
                total=total,
                chosen=chosen_event,
                answer=target_event,
                escape=escape_event,
                required=required["id"],
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def validate_pending(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    parent = game.action(c, action["parent_id"])
    pending = [
        x
        for x in game.pending(c, parent["id"])
        if x["kind"] == "escape_play" and x["actor_id"] == action["actor_id"]
    ]
    if len(pending) != 1 or parent["state"] != "awaiting_choices":
        raise WorkflowError("Preserve the original Flirt and its still-required escape child")
    if action["data"].get("ankou_feedback"):
        from girlframe.engine import m3_ankou_feedback as feedback
        from girlframe.services.m3_battle import _cast

        value = feedback.get(state, action["data"]["ankou_feedback"])
        if value.escape_source != source_binding(game, c, state, action) or value.cast != _cast(
            game, c, state, int(action["channel_id"])
        ):
            raise WorkflowError("Recover the original Feedback-held escape source and scene people")


def finish_blocked(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    parent: dict[str, Any],
) -> None:
    """No performed escape leaves the original Flirt's own Helpless consequence intact."""
    from girlframe.engine import m3_ankou_feedback as feedback
    from girlframe.engine.m3_actor_bonds import make_helpless

    if not action["data"].get("ankou_feedback"):
        return
    value = feedback.get(state, action["data"]["ankou_feedback"])
    if value.escape_source is None:
        return
    original = _before(game, c, value.mark_event)
    if (
        value.phase != "ended"
        or value.action != action["id"]
        or value.prepared.parent != parent["id"]
        or value.escape_source != source_binding(game, c, original, action)
    ):
        raise WorkflowError("Preserve the original unperformed Flirt escape and Feedback ending")
    sheet = state.sheets.get(value.actor.entity)
    if sheet is not None and sheet.character_id == value.actor.incarnation:
        foe = current_ref(original, int(parent["actor_id"]))
        updated = make_helpless(state, value.actor, foe, action["data"]["response_event"])
        for key in GameState.model_fields:
            setattr(state, key, getattr(updated, key))
        parent["data"]["result"]["helpless"] = int(value.actor.entity)
