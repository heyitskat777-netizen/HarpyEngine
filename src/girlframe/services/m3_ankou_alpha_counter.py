"""Original native counters retain their actual parents through mandatory Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.services.m3_dose_up import _response, _roll_source
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.engine.m3_ankou_feedback import Feedback
    from girlframe.services.m2_game import GameService
    from girlframe.services.read_only_bot import GuildViewer


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Prove immutable low receipt and owned opportunity, including after its completion."""
    from girlframe.services.m3_ankou_alpha import source_binding as alpha_binding

    prepared = PlayInput.model_validate(action["data"]["prepared"])
    scope = action["data"].get("alpha_counter_source")
    recipe = {
        "brutalize": "alpha",
        "unassuming_doll": "vatgrown",
        "easy_target": "easy_target",
        "old_dog_new_pups": "oldgen",
        "dose_up": "dose_up",
        "keep_your_head": "keep",
        "flirt": "flirt",
        "put_someone_beneath_you": "beneath",
    }.get(prepared.play)
    child_meta = action["data"].get(recipe, {}) if recipe is not None else {}
    if (
        not scope
        or recipe is None
        or not prepared.parent
        or prepared.parent != action.get("parent_id")
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
    ):
        raise WorkflowError("SOURCE_ANKOU_ALPHA_COUNTER_REQUIRED: preserve this native counter")
    parent = game.action(c, prepared.parent)
    meta = parent["data"].get("alpha", {})
    original_play = PlayInput.model_validate(parent["data"]["prepared"])
    if (
        parent.get("parent_id") is not None
        or original_play.parent is not None
        or original_play.source_work is not None
        or parent["data"].get("ankou_feedback")
        or parent["channel_id"] != action["channel_id"]
        or parent["scene_id"] != action["scene_id"]
        or meta.get("actor", {}).get("kind") != "pilot"
        or meta.get("target", {}).get("kind") != "pilot"
        or recipe not in ("oldgen", "flirt", "beneath")
        and prepared.target is not None
        or recipe == "oldgen"
        and (
            prepared.target != int(meta["actor"]["entity"])
            or prepared.target_actor is not None
            or child_meta.get("target") != meta["actor"]
            or child_meta.get("caster") != meta["target_controller"]
            or child_meta.get("counterpart") != meta["actor_controller"]
        )
        or recipe in ("flirt", "beneath")
        and (prepared.target != int(meta["actor"]["entity"]) or prepared.target_actor is not None)
        or recipe == "easy_target"
        and (
            prepared.target_actor is not None
            or child_meta.get("caster") != meta["target_controller"]
        )
        or recipe == "dose_up"
        and (
            prepared.target_actor not in (None, ActorRef.model_validate(meta["target"]))
            or child_meta.get("target") != meta["target"]
            or child_meta.get("caster") != meta["target_controller"]
            or child_meta.get("target_controller") != meta["target_controller"]
            or child_meta.get("chooser") != meta["target_controller"]
            or child_meta.get("contact") is not None
            or child_meta.get("order") is not None
        )
        or recipe not in ("easy_target", "oldgen", "dose_up", "keep", "flirt", "beneath")
        and (
            prepared.target_actor != ActorRef.model_validate(meta["actor"])
            or child_meta.get("target") != meta["actor"]
        )
        or recipe not in ("keep", "flirt")
        and child_meta.get("actor") != meta["target"]
        or recipe == "beneath"
        and (
            child_meta.get("target") != meta["actor"] or child_meta.get("special_girl") is not None
        )
        or action["actor_id"] != str(meta["target_controller"])
    ):
        raise WorkflowError("Preserve this original ordinary Alpha and her native target counter")
    if recipe in ("keep", "flirt", "beneath") and (
        prepared.target_actor is not None
        or action["data"].get("play") != prepared.play
        or action["data"].get("character_ids", {}).get(meta["target"]["entity"])
        != meta["target"]["incarnation"]
        or recipe in ("flirt", "beneath")
        and action["data"].get("character_ids", {}).get(meta["actor"]["entity"])
        != meta["actor"]["incarnation"]
        or any(
            action["data"].get(key)
            for key in (
                "learned_play",
                "princess_child",
                "actor_basic",
                "m3",
                "janus",
                "void_keep",
                "nightmare_core",
                "dampener",
                "easy_target_child",
                "ankou_effect_child",
                "consume_child",
                "wyvern_child",
                "red_queen_child",
                "changeling_child",
                "secretary_response",
                "alpha_sex_counter_source",
                "npc_flirt",
            )
        )
    ):
        raise WorkflowError("Preserve this original native basic counter and its actual body")
    declaration = alpha_binding(
        game,
        c,
        state,
        parent,
        original_cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
    )
    roll, total = _roll_source(game, c, parent)
    if total >= 8 or parent["data"]["result"].get("tier") != "low":
        raise WorkflowError("Prove the original genuine low Brutalize result")
    selection = _response(
        game,
        c,
        parent["id"],
        meta["selection_choice"],
        meta["counter_selected_event"],
        int(action["actor_id"]),
        "alpha_low",
    )
    expected = "counter_broken" if meta["retaliate"] else "counter_only"
    if selection.options != (expected,):
        raise WorkflowError("Preserve the original target's independently owned opportunity")
    choices = t.m2["m2_choices"]
    request = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == scope.get("choice"),
                choices.c.action_id == parent["id"],
                choices.c.actor_id == action["actor_id"],
                choices.c.kind == "alpha_counter_play",
            )
        )
        .mappings()
        .one_or_none()
    )
    wanted = dict(actor=meta["target"], attacker=meta["actor"])
    if (
        request is None
        or json.loads(request["body_json"]) != wanted
        or scope != dict(wanted, choice=request["id"], parent=parent["id"])
    ):
        raise WorkflowError("Preserve the original actual counter requirement and source binding")
    return hashlib.sha256(
        json.dumps(
            dict(
                parent=parent["id"],
                declaration=declaration,
                roll=roll,
                receipt=parent["data"]["receipt"]["id"],
                total=total,
                choice=meta["selection_choice"],
                selected=meta["counter_selected_event"],
                scope=scope,
                **(
                    {recipe: prepared.model_dump(mode="json")}
                    if recipe in ("keep", "flirt", "beneath")
                    else {}
                ),
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def validate_keep_pending(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Require the exact live native Keep opportunity, not a reusable child permit."""
    from girlframe.engine import m3_ankou_feedback as feedback
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.m3_alpha import validate_counter_child
    from girlframe.services.m3_dose_up import _cast

    prepared = PlayInput.model_validate(action["data"]["prepared"])
    binding = source_binding(game, c, state, action)
    if prepared.play != "keep_your_head" or not prepared.parent:
        raise WorkflowError("Recover this original unrolled native Keep counter")
    parent = game.action(c, prepared.parent)
    scope = validate_counter_child(
        game, c, parent, current_ref(state, int(action["actor_id"])), prepared
    )
    cast = _cast(game, c, state, int(action["channel_id"]))
    if (
        parent["state"] != "awaiting_choices"
        or scope != action["data"].get("alpha_counter_source")
        or SceneCast.model_validate_json(json.dumps(parent["data"]["alpha"]["cast"])) != cast
        or action["data"].get("receipt") is not None
    ):
        raise WorkflowError("Recover the original unrolled Keep, pending counter and scene")
    identity = action["data"].get("ankou_feedback")
    if identity:
        value = feedback.get(state, identity)
        if value.keep_counter_source != binding or value.cast != cast:
            raise WorkflowError("Preserve this actual Keep counter through its Feedback")
    return binding


def validate_flirt_pending(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Keep this exact living native Flirt and pending counter across Feedback."""
    from girlframe.engine import m3_ankou_feedback as feedback
    from girlframe.services.m3_alpha_flirt import pre_roll
    from girlframe.services.m3_dose_up import _cast

    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    binding = source_binding(game, c, state, action)
    if prepared.play != "flirt" or not prepared.parent:
        raise WorkflowError("Recover this original unrolled native Flirt counter")
    pre_roll(game, c, state, action)
    parent = game.action(c, prepared.parent)
    cast = _cast(game, c, state, int(action["channel_id"]))
    if (
        parent["state"] != "awaiting_choices"
        or SceneCast.model_validate_json(json.dumps(parent["data"]["alpha"]["cast"])) != cast
        or action["data"].get("receipt") is not None
    ):
        raise WorkflowError("Recover the original unrolled Flirt, pending counter and scene")
    identity = action["data"].get("ankou_feedback")
    if identity:
        value = feedback.get(state, identity)
        if value.flirt_counter_source != binding or value.cast != cast:
            raise WorkflowError("Preserve this actual Flirt counter through its Feedback")
    return binding


def validate_beneath_pending(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Keep this exact native Beneath and pending counter through its last mark."""
    from girlframe.engine import m3_ankou_feedback as feedback
    from girlframe.services.m3_alpha_beneath import pre_roll
    from girlframe.services.m3_dose_up import _cast

    prepared = PlayInput.model_validate_json(json.dumps(action["data"]["prepared"]))
    binding = source_binding(game, c, state, action)
    if prepared.play != "put_someone_beneath_you" or not prepared.parent:
        raise WorkflowError("Recover this original unrolled native Beneath counter")
    pre_roll(game, c, state, action)
    parent = game.action(c, prepared.parent)
    cast = _cast(game, c, state, int(action["channel_id"]))
    if (
        parent["state"] != "awaiting_choices"
        or SceneCast.model_validate_json(json.dumps(parent["data"]["alpha"]["cast"])) != cast
        or action["data"].get("receipt") is not None
    ):
        raise WorkflowError("Recover the original unrolled Beneath, pending counter and scene")
    identity = action["data"].get("ankou_feedback")
    if identity:
        value = feedback.get(state, identity)
        if value.beneath_counter_source != binding or value.cast != cast:
            raise WorkflowError("Preserve this actual Beneath counter through its Feedback")
    return binding


def validate_beneath_pin_response(
    game: "GameService",
    c: Connection,
    viewer: "GuildViewer",
    state: GameState,
    prepared: PlayInput,
    channel: int,
    value: "Feedback",
) -> None:
    """Defer the proved high or reversed low Keep/Flirt pin to ordinary handling."""
    from girlframe.engine.m3_beneath import choices as legal_choices
    from girlframe.services.m3_ankou_pin import _answer
    from girlframe.services.m3_beneath import roles
    from girlframe.services.m3_dose_up import _cast, _native
    from girlframe.services.m3_handler_advancements import _history

    parent = game.action(c, value.action)
    roll, total = _roll_source(game, c, parent)
    level = parent["data"]["result"].get("tier")
    pinner, pinned = roles(parent, level)
    if (
        value.phase != "resolved"
        or value.beneath_counter_source != source_binding(game, c, state, parent)
        or value.rolled_event != roll
        or value.receipt != parent["data"]["receipt"]["id"]
        or not (level == "high" and total >= 11 or level == "low" and total < 8)
        or parent["state"] != "awaiting_choices"
        or prepared.parent != parent["id"]
        or prepared.play not in ("keep_your_head", "flirt")
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.play == "keep_your_head"
        and prepared.target is not None
        or prepared.play == "flirt"
        and (
            prepared.target != int(pinner.entity)
            or prepared.learned_keep_rider is not None
            or prepared.kicked_puppy_basis
            or prepared.prince_exception is not None
        )
        or prepared.target_actor is not None
        or viewer.user_id != int(pinned.entity)
        or (pinned if level == "low" else pinner) != value.actor
        or channel != int(parent["channel_id"])
        or _cast(game, c, state, channel) != value.cast
    ):
        raise WorkflowError(
            "Use this genuine resumed Beneath pin's original owned native Keep or Flirt response"
        )
    for person in (pinner, pinned):
        actual = _native(game, c, state, person)
        if not actual.alive or actual.controller != int(person.entity):
            raise WorkflowError("Preserve the original living native people and controllers")
    selection, selected_event, selected = _answer(
        game, c, parent, int(pinner.entity), "beneath_select"
    )
    legal_choices(level, selected.options)
    if "pin" not in selected.options or parent["data"]["result"].get("beneath_effects") != list(
        selected.options
    ):
        raise WorkflowError(f"Preserve the original actually selected {level} Beneath pin")
    effect_event = selected_event
    if "bond" in selected.options:
        details, effect_event, detail = _answer(
            game, c, parent, int(pinned.entity), "beneath_details"
        )
        if json.loads(details["body_json"]) != dict(
            options=list(selected.options), source_choice=selection["id"]
        ) or set(detail.fields) != {"bond"}:
            raise WorkflowError("Preserve this pin's original private Bond consequence")
    pin = dict(
        kind="physical_pin",
        action=parent["id"],
        owner=pinner.entity,
        owner_character=str(pinner.incarnation),
        target=pinned.entity,
        target_character=str(pinned.incarnation),
        text=selected.text,
    )
    if any(pin not in history.facts for history in (_history(c, game, effect_event), state)):
        raise WorkflowError(f"Preserve this canonical actual {level} Beneath pin")
    response, _, answer = _answer(game, c, parent, int(pinned.entity), "beneath_pin_response")
    body = json.loads(response["body_json"])
    pending = [
        x
        for x in game.pending(c, parent["id"])
        if x["kind"] == "beneath_response_play" and x["actor_id"] == pinned.entity
    ]
    if (
        answer.options != ("play",)
        or body.get("owner") != pinned.model_dump(mode="json")
        or body.get("target") != pinner.model_dump(mode="json")
        or parent["data"]["result"].get("pinned_response_kind") != "play"
        or len(pending) != 1
        or json.loads(pending[0]["body_json"]) != {}
    ):
        raise WorkflowError("Preserve this pinned person's owned and still-required response")


def finish_ended(
    game: "GameService", c: Connection, state: GameState, child: dict[str, Any], event: str
) -> None:
    """End a genuinely unperformed counter without inventing damage or optional Broken."""
    from girlframe.services.m3_alpha import _finish
    from girlframe.services.m3_ankou_feedback import prove

    value = prove(game, c, state, child["data"]["ankou_feedback"])
    recipe = {
        "brutalize": "alpha",
        "unassuming_doll": "vatgrown",
        "easy_target": "easy_target",
        "old_dog_new_pups": "oldgen",
        "dose_up": "dose_up",
        "keep_your_head": "keep",
        "flirt": "flirt",
        "put_someone_beneath_you": "beneath",
    }.get(child["data"].get("play"))
    binding = (
        value.alpha_source
        if recipe == "alpha"
        else value.doll_source
        if recipe == "vatgrown"
        else value.easy_target_source
        if recipe == "easy_target"
        else value.advice_source
        if recipe == "oldgen"
        else value.dose_source
        if recipe == "dose_up"
        else value.keep_counter_source
        if recipe == "keep"
        else value.flirt_counter_source
        if recipe == "flirt"
        else value.beneath_counter_source
        if recipe == "beneath"
        else None
    )
    source = child["data"]["alpha_counter_source"]
    parent = game.action(c, source["parent"])
    if (
        binding is None
        or value.phase != "ended"
        or not value.resolved_event
        or value.rolled_event is not None
        or value.receipt is not None
        or child["state"] != "complete"
        or not child["data"]["result"].get("blocked_before_roll")
        or child["data"].get("receipt") is not None
        or recipe not in ("keep", "flirt", "beneath")
        and child["data"].get(recipe or "", {}).get("phase") != "unrolled"
        or game.pending(c, child["id"])
        or parent["data"]["alpha"]["phase"] != "counter"
    ):
        raise WorkflowError("Prove the actual unrolled Feedback ending before closing its parent")
    incoming = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.resolved_event,
            )
        )
        .mappings()
        .one()
    )
    payload = json.loads(incoming["payload_json"])
    choice_id = payload.get("choice_id")
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == choice_id,
                choices.c.action_id == child["id"],
                choices.c.state == "answered",
                choices.c.kind.in_(("ankou_feedback_purpose", "ankou_feedback_choice")),
                choices.c.actor_id == incoming["actor_id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None or payload.get("action_id") != child["id"]:
        raise WorkflowError("Preserve the actual owned Feedback ending decision")
    response = c.scalar(
        sa.select(responses.c.event_id).where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.choice_id == choice_id,
        )
    )
    if response is None:
        if event != value.resolved_event:
            raise WorkflowError("Recover the actual Feedback ending response before completion")
        # Canonical event precedes immutable response insertion. Its exact
        # post-response Feedback callback retries this same source once durable.
        return
    _response(
        game,
        c,
        child["id"],
        row["id"],
        value.resolved_event,
        int(incoming["actor_id"]),
        row["kind"],
    )
    request = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["id"] == source["choice"] and x["kind"] == "alpha_counter_play"
        ),
        None,
    )
    if request is None:
        raise WorkflowError("Preserve the original still-pending counter opportunity")
    actual = str(uuid4())
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == request["id"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    child["data"]["alpha_counter_completed"] = actual
    parent["data"]["alpha"].update(
        phase="resolved",
        counter_child=child["id"],
        counter_completed_event=actual,
        counter_performed=False,
        counter_feedback=value.id,
    )
    game.save_action(c, child)
    _finish(game, c, state, parent)
    game.event(
        c,
        incoming["actor_id"],
        str(uuid4()),
        "m3.alpha_counter_feedback_ended",
        state,
        event_id=actual,
        action_id=parent["id"],
        child=child["id"],
        source_event=value.resolved_event,
    )
