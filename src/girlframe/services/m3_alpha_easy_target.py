"""Actual native Newgirl mistake in her original low-Brutalize opportunity."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_alpha_sex import asleep
from girlframe.engine.m3_girl_runtime_state import has_rule
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
    from girlframe.services.m3_access import load_registry
    from girlframe.services.m3_dose_up import _cast, _native

    if prepared.play != rules.PLAY or prepared.parent is None:
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
        or target.kind != "pilot"
        or attacker.kind != "pilot"
        or current_ref(state, int(target.entity)) != target
        or current_ref(state, int(attacker.entity)) != attacker
        or state.sheets[actor.entity].girl != "NEWGIRL"
        or not has_rule(state.sheets[actor.entity], rules.RULE, "NEWGIRL")
        or meta.get("phase") != "counter"
        or parent["data"].get("result", {}).get("tier") != "low"
        or row is None
        or row["actor_id"] != actor.entity
        or prepared.target_actor is not None
        or prepared.target is not None
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
        raise WorkflowError("Use the original native Newgirl's actual mistake in this opportunity")
    for person in (actor, attacker):
        _native(game, c, state, person)
    load_registry().require_available(rules.RULE)
    responses, choices, receipts = (t.m2[x] for x in ("m2_responses", "m2_choices", "m2_receipts"))
    selection = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                responses.c.campaign_id == choices.c.campaign_id,
                responses.c.choice_id == choices.c.id,
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
        selection is None
        or ChoiceAnswer.model_validate_json(selection).options != (expected,)
        or receipt is None
        or json.loads(receipt) != parent["data"].get("receipt")
    ):
        raise WorkflowError(
            "Recover the original low receipt and Newgirl's owned counter selection"
        )
    scope = dict(
        choice=row["id"], actor=meta["target"], attacker=meta["actor"], parent=parent["id"]
    )
    if action is not None and (
        action["data"].get("alpha_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
        or action["data"].get("easy_target", {}).get("actor") != meta["target"]
        or action["data"].get("easy_target", {}).get("caster") != meta["target_controller"]
    ):
        raise WorkflowError("Recover the exact original Easy Target before spending or rolling")
    return scope


def completed(
    game: "GameService", c: Connection, state: GameState, child: dict[str, Any], event: str
) -> bool:
    """Prove the real source and effects; defer only the response currently being saved."""
    from girlframe.services.m3_easy_target import _session, prove
    from girlframe.services.m3_princess_easy_target import _completion_author

    meta = child["data"]["easy_target"]
    source = child["data"]["alpha_counter_source"]
    parent = game.action(c, source["parent"])
    original = parent["data"]["alpha"]
    session = _session(game, c, state, child)
    reactions = [x for x in rules.records(state, rules.Reaction) if x.session == child["id"]]
    prepared = PlayInput.model_validate(child["data"]["prepared"])
    if (
        meta.get("phase") != "complete"
        or session.actor.model_dump(mode="json") != original["target"]
        or session.caster != original["target_controller"]
        or session.cast.model_dump(mode="json") != original["cast"]
        or child["data"].get("learned_play")
        or meta.get("princess_direction")
        or not rules.settled(state, session)
        or not reactions
        or any(not x.completed_event for x in reactions)
        or prepared.parent != parent["id"]
        or prepared.play != rules.PLAY
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.target is not None
        or prepared.target_actor is not None
        or not prepared.trigger_confirmed
        or source["actor"] != original["target"]
        or source["attacker"] != original["actor"]
    ):
        raise WorkflowError("Complete the original Newgirl's real reactions and consequences first")
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
    if audit["kind"] in ("m2.choice_resolved", "m3.choice_resolved"):
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == payload.get("choice_id"),
                    choices.c.action_id == child["id"],
                    choices.c.state == "answered",
                    choices.c.actor_id == audit["actor_id"],
                )
            )
            .mappings()
            .first()
        )
        if row is not None and payload.get("action_id") == child["id"]:
            response = c.scalar(
                sa.select(responses.c.event_id).where(
                    responses.c.campaign_id == game.store.campaign_id,
                    responses.c.choice_id == row["id"],
                    responses.c.actor_id == row["actor_id"],
                )
            )
            if response is None:
                return False
            if response != event:
                raise WorkflowError("Recover the exact final owned Easy Target response")
    for reaction in reactions:
        prove(game, c, state, reaction.id)
    if audit["kind"] == "m3.easy_target_failure":
        failure_reaction = next((x for x in reactions if x.id == payload.get("work")), None)
        if (
            failure_reaction is None
            or failure_reaction.completed_event != event
            or failure_reaction.consequence not in ("failure-tag", "failure-declined")
            or audit["actor_id"] != str(session.caster)
        ):
            raise WorkflowError(
                "Preserve the Newgirl's actual owned protection-failure consequence"
            )
    else:
        _completion_author(game, c, child, None, event)
    return True
