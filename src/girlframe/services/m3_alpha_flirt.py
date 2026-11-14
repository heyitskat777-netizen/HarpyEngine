"""The original failed-Brutalize target's actual basic Flirt, not a generic child grant."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_alpha_sex import asleep
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def counter(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    prepared: PlayInput,
    channel: int,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from girlframe.services.m3_dose_up import _cast, _native

    if prepared.play != "flirt" or prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    meta = parent["data"].get("alpha")
    if meta is None:
        return None
    attacker = ActorRef.model_validate(meta["actor"])
    target = ActorRef.model_validate(meta["target"])
    row = next(
        (x for x in game.pending(c, parent["id"]) if x["kind"] == "alpha_counter_play"), None
    )
    if (
        actor != target
        or actor.kind != "pilot"
        or attacker.kind != "pilot"
        or current_ref(state, int(actor.entity)) != actor
        or current_ref(state, int(attacker.entity)) != attacker
        or meta.get("phase") != "counter"
        or parent["data"].get("result", {}).get("tier") != "low"
        or row is None
        or row["actor_id"] != actor.entity
        or prepared.target != int(attacker.entity)
        or prepared.target_actor is not None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or not prepared.trigger_confirmed
        or int(parent["channel_id"]) != channel
        or fingerprint(_cast(game, c, state, channel)) != meta["cast_sha256"]
        or is_helpless(state, actor)
        or asleep(state, actor)
        or asleep(state, attacker)
    ):
        raise WorkflowError(
            "Flirt as this original target with the actual Alpha in this opportunity"
        )
    for person, owner in ((actor, meta["target_controller"]), (attacker, meta["actor_controller"])):
        actual = _native(game, c, state, person)
        if not actual.alive or actual.controller != owner or str(owner) != person.entity:
            raise WorkflowError("Keep the actual living original Girls and their own controllers")
    responses, choices, receipts = (t.m2[x] for x in ("m2_responses", "m2_choices", "m2_receipts"))
    selected = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.choice_id == meta.get("selection_choice"),
            responses.c.event_id == meta.get("counter_selected_event"),
            responses.c.actor_id == actor.entity,
            choices.c.action_id == parent["id"],
            choices.c.kind == "alpha_low",
        )
    )
    receipt = c.scalar(
        sa.select(receipts.c.body_json).where(
            receipts.c.campaign_id == game.store.campaign_id,
            receipts.c.action_id == parent["id"],
        )
    )
    expected = "counter_broken" if meta["retaliate"] else "counter_only"
    if (
        selected is None
        or ChoiceAnswer.model_validate_json(selected).options != (expected,)
        or receipt is None
        or json.loads(receipt) != parent["data"].get("receipt")
    ):
        raise WorkflowError("Recover the actual low receipt and original owned counter selection")
    source = dict(
        choice=row["id"], actor=meta["target"], attacker=meta["actor"], parent=parent["id"]
    )
    if action is not None and (
        action["data"].get("alpha_counter_source") != source
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
        or any(
            action["data"].get(key)
            for key in ("princess_child", "actor_basic", "npc_flirt", "learned_play")
        )
    ):
        raise WorkflowError("Preserve this exact native Flirt counter and its original owner")
    return source


def pre_roll(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    source = action["data"]["alpha_counter_source"]
    if (
        counter(
            game,
            c,
            state,
            ActorRef.model_validate(source["actor"]),
            PlayInput.model_validate(action["data"]["prepared"]),
            int(action["channel_id"]),
            action,
        )
        != source
    ):
        raise WorkflowError("Recover the real Flirt opportunity before spending or rolling")


def completed(
    game: "GameService", c: Connection, state: GameState, child: dict[str, Any], event: str
) -> bool:
    from girlframe.services.m3_dose_up import _response, _roll_source
    from girlframe.services.m3_handler_advancements import _history

    roll, total = _roll_source(game, c, child)
    pre_roll(game, c, _history(c, game, roll), child)
    source = child["data"]["alpha_counter_source"]
    owner = int(source["actor"]["entity"])
    other = int(source["attacker"]["entity"])
    result = child["data"]["result"]
    if (
        child["state"] != "complete"
        or game.pending(c, child["id"])
        or result.get("total") != total
        or child["data"]["character_ids"].get(str(other)) != source["attacker"]["incarnation"]
    ):
        raise WorkflowError("Complete the original Flirt result, not just its counter declaration")
    kinds = {
        "actor_flirt": owner,
        "target_flirt": other,
        "actor_flirt_answer": owner,
        "flirt_escape": other,
        "flirt_owe_tag": other,
    }
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    rows = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == child["id"],
                choices.c.kind.in_(kinds),
            )
        )
        .mappings()
        .all()
    )
    answers: dict[str, ChoiceAnswer] = {}
    for row in rows:
        human = kinds[row["kind"]]
        if row["state"] != "answered" or row["actor_id"] != str(human):
            raise WorkflowError("Preserve each real Flirt result's independent chooser")
        response_event = c.scalar(
            sa.select(responses.c.event_id).where(
                responses.c.campaign_id == game.store.campaign_id,
                responses.c.choice_id == row["id"],
            )
        )
        if response_event is None:
            audit = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                    )
                )
                .mappings()
                .one()
            )
            payload = json.loads(audit["payload_json"])
            if (
                audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
                or audit["actor_id"] != str(human)
                or payload.get("action_id") != child["id"]
                or payload.get("choice_id") != row["id"]
            ):
                raise WorkflowError("Recover the exact current Flirt answer before completion")
            # Game.event precedes the immutable response insert; only this exact
            # incoming answer may wait for the post-response callback.
            return False
        answers[row["kind"]] = _response(
            game, c, child["id"], row["id"], response_event, human, row["kind"]
        )
    target = answers.get("target_flirt")
    if target is None or not target.text.strip() or target.text != result.get("target_answer"):
        raise WorkflowError("Keep the original Alpha's independently authored private answer")
    if total <= 7:
        returned = answers.get("actor_flirt_answer")
        if target.options and (
            target.options != (result.get("return_question"),)
            or returned is None
            or not returned.text.strip()
            or returned.text != result.get("actor_answer")
        ):
            raise WorkflowError("Finish the original counter-player's actual return answer")
    else:
        actor = answers.get("actor_flirt")
        if actor is None or actor.options != (result.get("question"),):
            raise WorkflowError("Keep the original Flirt player's actual question")
        if not any(
            x.kind == "flirt_followthrough"
            and x.action == child["id"]
            and x.owner == owner
            and x.target == other
            and x.details.get("wanted") == target.text
            for x in state.obligations
        ):
            raise WorkflowError(
                "Retain the actual conditional follow-through, without inventing it"
            )
        if total >= 11 and (
            actor.fields.get("extra") != result.get("extra")
            or actor.text != result.get("too_far")
            or result.get("extra") not in ("escape", "handler", "owe")
            or result["extra"] == "escape"
            and "flirt_escape" not in answers
            or result["extra"] == "owe"
            and "flirt_owe_tag" not in answers
        ):
            raise WorkflowError("Finish the actual chosen high Flirt consequence first")
    return True
