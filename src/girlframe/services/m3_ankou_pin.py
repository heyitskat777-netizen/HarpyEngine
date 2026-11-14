"""The actual Beneath pin response retains its source across mandatory Feedback."""

import hashlib
import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_beneath as social
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_disposable_psyche import _before
from girlframe.services.m3_dose_up import _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.engine.m3_ankou_feedback import Feedback
    from girlframe.services.m2_game import GameService
    from girlframe.services.read_only_bot import GuildViewer


def _answer(
    game: "GameService", c: Connection, parent: dict[str, Any], owner: int, kind: str
) -> tuple[dict[str, Any], str, ChoiceAnswer]:
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(choices, responses.c.event_id)
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
        raise WorkflowError("Recover the original Beneath choice and its own human's response")
    answer = _response(game, c, parent["id"], row["id"], row["event_id"], owner, kind)
    saved = ChoiceAnswer.model_validate_json(
        json.dumps(parent["data"]["choices"].get(f"{kind}:{owner}", {}))
    )
    if answer != saved:
        raise WorkflowError("Preserve the actual original pinner and pinned person's choices")
    return dict(row), row["event_id"], answer


def _resolved_standalone_effect(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: "Feedback",
    *,
    counter_binding: str | None = None,
) -> None:
    """Admit proved purpose, Bond rewrite, or a completed native Girl/NPC/Handler reprisal."""
    from girlframe.engine.m3_actor_bonds import depth

    if value.choice == "purpose" and value.purpose_given is True and value.new_identity:
        return
    if value.choice == "tear":
        from girlframe.services.m3_ankou_feedback import _reprisal_supported, prove_loss_source

        if (
            value.phase != "resolved"
            or not value.choice_event
            or not value.resolved_event
            or value.resolved_event == value.choice_event
            or value.target is None
            or value.target.kind not in ("pilot", "npc", "handler")
            or (value.target.kind != "pilot" and counter_binding is not None)
            or not _reprisal_supported(state, value.target)
            or not value.child
            or not value.child_event
            or not value.lost_asset
            or value.new_identity is not None
            or value.purpose_given is not None
            or value.beneath_counter_source != counter_binding
        ):
            raise WorkflowError("Preserve the actual completed source-bound Girl reprisal")
        prove_loss_source(game, c, state, value.choice_event, value.id, value.actor)
        child = game.action(c, value.child)
        prepared = PlayInput.model_validate(child["data"]["prepared"])
        if (
            child["state"] != "complete"
            or game.pending(c, value.child)
            or child["parent_id"] != value.action
            or child["actor_id"] != value.actor.entity
            or child["data"].get("ankou_feedback_child", {}).get("source") != value.id
            or prepared.play != ("engage" if value.target.kind == "handler" else "flirt")
            or (
                prepared.target != int(value.target.entity) or prepared.target_actor is not None
                if value.target.kind == "pilot"
                else prepared.target is not None or prepared.target_actor != value.target
            )
            or prepared.source_work != value.id
            or any(x.id == value.lost_asset for x in state.sheets[value.actor.entity].assets)
        ):
            raise WorkflowError("Complete the original source-bound reprisal and owned choices")
        if value.target.kind == "handler" and (
            child["data"].get("engage", {}).get("target") != value.target.model_dump(mode="json")
            or child["data"].get("npc_flirt")
            or child["data"].get("actor_basic")
        ):
            raise WorkflowError("Preserve the actual Handler Engage reprisal")
        _roll_source(game, c, child)
        return
    if (
        value.choice != "bond"
        or value.target is None
        or not value.choice_event
        or value.resolved_event != value.choice_event
        or value.new_identity is not None
        or value.purpose_given is not None
    ):
        raise WorkflowError("Preserve the actual resolved purpose or Bond-rewrite Feedback")
    before = _before(game, c, value.choice_event)
    committed = _history(c, game, value.choice_event)
    asset = next(
        (x for x in committed.sheets[value.actor.entity].assets if x.id == value.id + ":bond"),
        None,
    )
    if (
        depth(before, value.actor, value.target) < 1
        or depth(committed, value.actor, value.target) != 0
        or asset is None
        or asset.family != "girl"
        or asset not in state.sheets[value.actor.entity].assets
    ):
        raise WorkflowError("Preserve the genuine cut Bond and its installed psychological Asset")


def validate_resumed_beneath_response(
    game: "GameService",
    c: Connection,
    viewer: "GuildViewer",
    state: GameState,
    prepared: PlayInput,
    channel: int,
    value: "Feedback | None",
    *,
    native_parent: str | None = None,
) -> None:
    """Admit the actual high or reversed low pin's owned Keep/Flirt after Feedback."""
    from girlframe.services.m3_beneath import feedback_source_binding, roles
    from girlframe.services.m3_dose_up import _cast, _native

    if value is not None:
        _resolved_standalone_effect(game, c, state, value)
        parent = game.action(c, value.action)
        expected_cast = value.cast.model_dump(mode="json")
    else:
        if native_parent is None:
            raise WorkflowError("Recover the original native mixed-cast pin")
        parent = game.action(c, native_parent)
        scope = parent["data"].get("beneath_mixed")
        if (
            not scope
            or scope.get("parent") is not None
            or parent["parent_id"] is not None
            or parent["data"].get("ankou_feedback")
        ):
            raise WorkflowError("Use the actual ordinary native mixed-cast pin")
        expected_cast = scope["cast"]
    original = PlayInput.model_validate(parent["data"]["prepared"])
    declaration = feedback_source_binding(parent) if value is not None else None
    roll, total = _roll_source(game, c, parent)
    level = "high" if total >= 11 else "mid" if total >= 8 else "low"
    pinner, pinned = roles(parent, level)
    if (
        (
            value is not None
            and (
                value.phase != "resolved"
                or not value.resolved_event
                or value.beneath_counter_source is not None
                or value.beneath_source != declaration
                or value.rolled_event != roll
                or value.receipt != parent["data"]["receipt"]["id"]
                or (pinned if level == "low" else pinner) != value.actor
            )
        )
        or level == "mid"
        or parent["data"]["result"].get("tier") != level
        or parent["state"] != "awaiting_choices"
        or original.source_work is not None
        or original.order_id is not None
        or original.off_duty_id is not None
        or original.piloting
        or any(
            parent["data"].get(key)
            for key in ("actor_basic", "princess_child", "m3", "alpha_counter_source")
        )
        or prepared.parent != parent["id"]
        or prepared.play not in ("keep_your_head", "flirt")
        or prepared.source_work is not None
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.play == "keep_your_head"
        and prepared.target is not None
        or prepared.play == "flirt"
        and (prepared.target != int(pinner.entity) or prepared.kicked_puppy_basis)
        or prepared.target_actor is not None
        or prepared.piloting
        or prepared.learned_keep_rider is not None
        or prepared.prince_exception is not None
        or viewer.user_id != int(pinned.entity)
        or channel != int(parent["channel_id"])
        or _cast(game, c, state, channel).model_dump(mode="json") != expected_cast
    ):
        raise WorkflowError(
            "Use this standalone accepted Feedback pin's original owned native response"
        )
    before_roll = _before(game, c, roll)
    for person in (pinner, pinned):
        actual = _native(game, c, state, person)
        if (
            not actual.alive
            or actual.controller != int(person.entity)
            or person != current_ref(before_roll, int(person.entity))
            or person != current_ref(state, int(person.entity))
            or parent["data"].get("character_ids", {}).get(person.entity) != person.incarnation
        ):
            raise WorkflowError("Preserve the original living native people and controllers")
    selection, selected_event, selected = _answer(
        game, c, parent, int(pinner.entity), "beneath_select"
    )
    social.choices(level, selected.options)
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
    choice = dict(
        kind="beneath_choice",
        action=parent["id"],
        choice=selection["id"],
        owner=pinner.entity,
        owner_character=str(pinner.incarnation),
        target=pinned.entity,
        target_character=str(pinned.incarnation),
        options=",".join(selected.options),
        text=selected.text,
    )
    if any(
        fact not in history.facts
        for history in (_history(c, game, effect_event), state)
        for fact in (pin, choice)
    ):
        raise WorkflowError(f"Preserve this canonical actual {level} Beneath pin and effects")
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


def source_binding(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> str:
    """Bind a native pin Keep/Flirt, including a resolved standalone Feedback parent."""
    from girlframe.services.m3_beneath import feedback_source_binding, roles

    prepared = PlayInput.model_validate(action["data"]["prepared"])
    if (
        prepared.play not in ("keep_your_head", "flirt")
        or not prepared.parent
        or prepared.parent != action.get("parent_id")
        or prepared.source_work is not None
        or prepared.play == "keep_your_head"
        and prepared.target is not None
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
        raise WorkflowError("SOURCE_ANKOU_PIN_PORT_REQUIRED: preserve this specific pin response")
    parent = game.action(c, prepared.parent)
    original_play = PlayInput.model_validate(parent["data"]["prepared"])
    counter_binding = None
    if parent["data"].get("alpha_counter_source"):
        from girlframe.services.m3_ankou_alpha_counter import source_binding as counter_source

        # The counter proof admits only one original parentless native Alpha,
        # never another pin response or Feedback ancestry.
        counter_binding = counter_source(game, c, state, parent)
    declaration = feedback_source_binding(parent, counter_source=counter_binding)
    if (
        original_play.source_work is not None
        or parent["data"].get("play") != social.PLAY
        or parent["scene_id"] != action["scene_id"]
        or parent["channel_id"] != action["channel_id"]
        or any(parent["data"].get(key) for key in ("actor_basic", "princess_child", "m3"))
    ):
        raise WorkflowError(
            "SOURCE_ANKOU_PIN_PORT_REQUIRED: use the actual ordinary Beneath source"
        )
    roll_event, total = _roll_source(game, c, parent)
    level = "high" if total >= 11 else "mid" if total >= 8 else "low"
    if level == "mid" or parent["data"]["result"].get("tier") != level:
        raise WorkflowError("Recover the original Beneath roll that actually permits pinning")
    pinner, actor = roles(parent, level)
    if prepared.play == "flirt" and (
        prepared.target != int(pinner.entity)
        or prepared.order_id is not None
        or prepared.off_duty_id is not None
        or prepared.piloting
        or prepared.kicked_puppy_basis
        or prepared.learned_keep_rider is not None
        or prepared.prince_exception is not None
        or action["data"].get("alpha_counter_source")
    ):
        raise WorkflowError(
            "SOURCE_ANKOU_PIN_PORT_REQUIRED: use native Flirt with this original pinner"
        )
    parent_feedback = None
    if identity := parent["data"].get("ankou_feedback"):
        from girlframe.engine import m3_ankou_feedback as feedback
        from girlframe.services.m3_ankou_feedback import prove
        from girlframe.services.m3_dose_up import _cast

        source = feedback.get(state, identity)
        # Check finite ancestry before proof: ordinary parentless Beneath or
        # one proved native Alpha counter. Never a pin or escape cycle.
        if (
            source.action != parent["id"]
            or source.choice not in ("purpose", "bond", "tear")
            or source.prepared.play != social.PLAY
            or (source.prepared.parent is None) != (counter_binding is None)
            or source.beneath_source != declaration
            or source.beneath_counter_source != counter_binding
            or any(
                value is not None
                for key, value in source.model_dump().items()
                if key.endswith("_source")
                and key
                not in (
                    ("beneath_source",)
                    if counter_binding is None
                    else ("beneath_source", "beneath_counter_source")
                )
            )
            or source.phase != "resolved"
            or not source.resolved_event
            or source.rolled_event != roll_event
            or source.receipt != parent["data"]["receipt"]["id"]
            or (actor if level == "low" else pinner) != source.actor
            or source.cast != _cast(game, c, state, int(parent["channel_id"]))
            or original_play.order_id is not None
            or original_play.off_duty_id is not None
            or original_play.piloting
            or prepared.order_id is not None
            or prepared.off_duty_id is not None
            or prepared.piloting
            or prepared.learned_keep_rider is not None
            or prepared.prince_exception is not None
        ):
            raise WorkflowError("Preserve this resolved native Beneath Feedback parent")
        _resolved_standalone_effect(game, c, state, source, counter_binding=counter_binding)
        prove(game, c, state, identity)
        parent_feedback = dict(
            id=source.id,
            mark=source.mark_event,
            resolved=source.resolved_event,
            purpose=source.purpose_event,
            new_identity=source.new_identity,
        )
        if source.choice in ("bond", "tear"):
            parent_feedback.update(
                choice=source.choice,
                choice_event=source.choice_event,
                target=source.target.token if source.target else None,
            )
        if source.choice == "tear":
            parent_feedback.update(
                lost_asset=source.lost_asset,
                child=source.child,
                child_event=source.child_event,
            )
    original = _before(game, c, roll_event)
    if (
        actor.entity != action["actor_id"]
        or any(
            ref != current_ref(original, int(ref.entity))
            or ref != current_ref(state, int(ref.entity))
            or parent["data"].get("character_ids", {}).get(ref.entity) != ref.incarnation
            for ref in (pinner, actor)
        )
        or action["data"].get("character_ids", {}).get(actor.entity) != actor.incarnation
    ):
        raise WorkflowError("Retain the actual original pinner and pinned Pilot")
    selection, chosen_event, chosen = _answer(game, c, parent, int(pinner.entity), "beneath_select")
    social.choices(level, chosen.options)
    if "pin" not in chosen.options or parent["data"]["result"].get("beneath_effects") != list(
        chosen.options
    ):
        raise WorkflowError("Retain the actual selected and applied physical pin")
    effect_event = chosen_event
    if "bond" in chosen.options:
        details, effect_event, detail = _answer(
            game, c, parent, int(actor.entity), "beneath_details"
        )
        if json.loads(details["body_json"]) != dict(
            options=list(chosen.options), source_choice=selection["id"]
        ) or set(detail.fields) != {"bond"}:
            raise WorkflowError("Preserve the pinned Pilot's actual private Bond selection")
    expected_pin = dict(
        kind="physical_pin",
        action=parent["id"],
        owner=pinner.entity,
        owner_character=str(pinner.incarnation),
        target=actor.entity,
        target_character=str(actor.incarnation),
        text=chosen.text,
    )
    expected_choice = dict(
        kind="beneath_choice",
        action=parent["id"],
        choice=selection["id"],
        owner=pinner.entity,
        owner_character=str(pinner.incarnation),
        target=actor.entity,
        target_character=str(actor.incarnation),
        options=",".join(chosen.options),
        text=chosen.text,
    )
    applied = _history(c, game, effect_event)
    if any(
        expected not in history.facts
        for history in (applied, state)
        for expected in (expected_pin, expected_choice)
    ):
        raise WorkflowError("Prove the canonical original physical pin and printed effects")
    response, response_event, response_answer = _answer(
        game, c, parent, int(actor.entity), "beneath_pin_response"
    )
    body = json.loads(response["body_json"])
    if (
        response_answer.options != ("play",)
        or body.get("owner") != actor.model_dump(mode="json")
        or body.get("target") != pinner.model_dump(mode="json")
        or parent["data"]["result"].get("pinned_response_kind") != "play"
    ):
        raise WorkflowError("Preserve the pinned person's own actual response-Play decision")
    choices = t.m2["m2_choices"]
    required = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == parent["id"],
                choices.c.kind == "beneath_response_play",
                choices.c.actor_id == actor.entity,
            )
        )
        .mappings()
        .one_or_none()
    )
    if required is None or json.loads(required["body_json"]) != {}:
        raise WorkflowError("Recover this original pin's actual target-owned response requirement")
    return hashlib.sha256(
        json.dumps(
            dict(
                parent=parent["id"],
                scene=parent["scene_id"],
                channel=parent["channel_id"],
                actor=actor.model_dump(mode="json"),
                pinner=pinner.model_dump(mode="json"),
                declaration=declaration,
                roll=roll_event,
                receipt=parent["data"]["receipt"]["id"],
                total=total,
                selected=chosen_event,
                effect=effect_event,
                response=response_event,
                required=required["id"],
                **({"response_play": "flirt"} if prepared.play == "flirt" else {}),
                **({"parent_feedback": parent_feedback} if parent_feedback is not None else {}),
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
        if x["kind"] == "beneath_response_play" and x["actor_id"] == action["actor_id"]
    ]
    if len(pending) != 1 or parent["state"] != "awaiting_choices":
        raise WorkflowError("Preserve the original Beneath pin and still-required response")
    if action["data"].get("ankou_feedback"):
        from girlframe.engine import m3_ankou_feedback as feedback
        from girlframe.services.m3_battle import _cast

        value = feedback.get(state, action["data"]["ankou_feedback"])
        if value.pin_source != source_binding(game, c, state, action) or value.cast != _cast(
            game, c, state, int(action["channel_id"])
        ):
            raise WorkflowError("Recover the original Feedback-held pin response and scene people")


def finish_parent(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    parent: dict[str, Any],
) -> None:
    """Record real performance or its mandatory ending without inventing an escape."""
    from girlframe.engine import m3_ankou_feedback as feedback

    if not action["data"].get("ankou_feedback"):
        return
    value = feedback.get(state, action["data"]["ankou_feedback"])
    if value.pin_source is None:
        return
    if (
        value.action != action["id"]
        or value.prepared.parent != parent["id"]
        or value.pin_source != source_binding(game, c, _before(game, c, value.mark_event), action)
    ):
        raise WorkflowError("Preserve this original Feedback-held pin response completion")
    performed = not action["data"]["result"].get("blocked_before_roll", False)
    if (performed and (value.receipt is None or not value.rolled_event)) or (
        not performed and (value.phase != "ended" or action["data"].get("receipt") is not None)
    ):
        raise WorkflowError("Prove the real response receipt or its unrolled Feedback ending")
    parent["data"]["result"]["pinned_response_performed"] = performed
    parent["data"]["result"]["pinned_response_feedback"] = value.id
