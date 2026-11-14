"""Actual native Vatgrown background Play in her original low-Brutalize opportunity."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown as rules
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
        (x for x in game.pending(c, parent["id"]) if x["kind"] == "alpha_counter_play"),
        None,
    )
    if (
        actor != target
        or target.kind != "pilot"
        or attacker.kind != "pilot"
        or current_ref(state, int(target.entity)) != target
        or current_ref(state, int(attacker.entity)) != attacker
        or state.sheets[actor.entity].girl != "VATGROWN"
        or not has_rule(state.sheets[actor.entity], rules.RULE, "VATGROWN")
        or meta.get("phase") != "counter"
        or parent["data"].get("result", {}).get("tier") != "low"
        or row is None
        or row["actor_id"] != actor.entity
        or prepared.target_actor != attacker
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
        raise WorkflowError(
            "Use the original native Vatgrown's actual background Play in this opportunity"
        )
    for person in (actor, attacker):
        _native(game, c, state, person)
    from girlframe.services.m3_vatgrown import _context

    # Availability/proof must not retain a new cast in the caller's snapshot.
    # Actual Doll preparation establishes it in its canonical operation state.
    _context(game, c, state.model_copy(deep=True), actor, attacker, channel)
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
            "Recover the original low receipt and Vatgrown's owned counter selection"
        )
    scope = dict(
        choice=row["id"],
        actor=meta["target"],
        attacker=meta["actor"],
        parent=parent["id"],
    )
    if action is not None and (
        action["data"].get("alpha_counter_source") != scope
        or action["parent_id"] != parent["id"]
        or action["actor_id"] != actor.entity
        or action["data"]["prepared"] != prepared.model_dump(mode="json")
        or action["data"].get("vatgrown", {}).get("actor") != meta["target"]
        or action["data"].get("vatgrown", {}).get("caster") != meta["target_controller"]
        or action["data"].get("vatgrown", {}).get("target") != meta["actor"]
        or action["data"].get("vatgrown", {}).get("counterpart") != meta["actor_controller"]
    ):
        raise WorkflowError("Recover the exact original Unassuming Doll before spending or rolling")
    return scope


def completed(
    game: "GameService",
    c: Connection,
    state: GameState,
    child: dict[str, Any],
    event: str,
) -> bool:
    """Finish only the original Doll effects and actual final owned response."""
    from girlframe.services.m3_dose_up import _response
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_vatgrown import prove, prove_effect

    source = child["data"]["alpha_counter_source"]
    parent = game.action(c, source["parent"])
    original = parent["data"]["alpha"]
    meta = child["data"].get("vatgrown", {})
    value = rules.source(state, child["id"])
    prepared = PlayInput.model_validate(child["data"]["prepared"])
    if (
        not value.complete
        or value.completed_event != event
        or meta.get("phase") != "complete"
        or value.actor.model_dump(mode="json") != original["target"]
        or value.target.model_dump(mode="json") != original["actor"]
        or value.caster != original["target_controller"]
        or value.counterpart != original["actor_controller"]
        or value.cast.model_dump(mode="json") != original["cast"]
        or child["data"].get("learned_play")
        or meta.get("princess_direction")
        or prepared.play != rules.PLAY
        or prepared.parent != parent["id"]
        or prepared.target_actor != value.target
        or prepared.target is not None
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or not prepared.trigger_confirmed
    ):
        raise WorkflowError("Finish the actual original Vatgrown's Doll before its counter closes")
    info = next(
        (x for x in rules.records(state, rules.Information) if x.action == child["id"]),
        None,
    )
    if "information" in value.benefits:
        if (
            info is None
            or info.choice is None
            or info.event != event
            or not info.answer
            or info.giver != value.target
            or info.controller != value.counterpart
            or info.recipient != value.actor
            or info.recipient_controller != value.caster
            or info.cast != value.cast
            or info.requested_event != value.benefit_event
        ):
            raise WorkflowError("Retain the original Alpha's actual answer or offered secret")
        choice, owner, kind = info.choice, value.counterpart, "vat_doll_information"
    else:
        if info is not None or value.benefit_event != event or value.benefit_choice is None:
            raise WorkflowError("Finish only the actual original Vatgrown benefit choice")
        choice, owner, kind = value.benefit_choice, value.caster, "vat_doll_benefits"
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
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == choice,
            )
        )
        .mappings()
        .first()
    )
    if (
        audit["kind"] != "m3.choice_resolved"
        or audit["actor_id"] != str(owner)
        or payload.get("action_id") != child["id"]
        or payload.get("choice_id") != choice
        or row is None
        or row["action_id"] != child["id"]
        or row["kind"] != kind
        or row["actor_id"] != str(owner)
        or row["state"] != "answered"
    ):
        raise WorkflowError("Recover the exact original Doll completion and independent chooser")
    response = c.scalar(
        sa.select(t.m2["m2_responses"].c.event_id).where(
            t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_responses"].c.choice_id == choice,
        )
    )
    if response is None:
        # event() persists the canonical state before respond() inserts this exact row.
        return False
    if response != event:
        raise WorkflowError("Retain the actual original Doll completion response")
    answer = _response(game, c, child["id"], choice, event, owner, kind)
    if info is not None and (
        info.answer != answer.text
        or info not in rules.records(_history(c, game, event), rules.Information)
    ):
        raise WorkflowError("Prove the actual Alpha's independently authored private information")
    prove(game, c, state, child["id"])
    for benefit in (*value.benefits, *(("object",) if value.total >= 11 else ())):
        prove_effect(game, c, state, "vat-doll-effect:" + child["id"] + ":" + benefit)
    return True
