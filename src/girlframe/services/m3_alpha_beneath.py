"""Actual Beneath counter in one original failed-Brutalize opportunity."""

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

    if prepared.play != "put_someone_beneath_you" or prepared.parent is None:
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
            "Beneath as this original target with the actual Alpha in this opportunity"
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
        or action["data"].get("beneath", {}).get("actor") != meta["target"]
        or action["data"].get("beneath", {}).get("target") != meta["actor"]
        or any(
            action["data"].get(key)
            for key in ("princess_child", "actor_basic", "npc_flirt", "learned_play")
        )
    ):
        raise WorkflowError("Preserve this exact native Beneath counter and its original owner")
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
        raise WorkflowError("Recover the real Beneath opportunity before spending or rolling")


def completed(
    game: "GameService", c: Connection, state: GameState, child: dict[str, Any], event: str
) -> bool:
    from girlframe.engine.m3_beneath import choices as legal_choices
    from girlframe.services.m3_beneath import roles
    from girlframe.services.m3_dose_up import _response, _roll_source
    from girlframe.services.m3_handler_advancements import _history

    roll, total = _roll_source(game, c, child)
    pre_roll(game, c, _history(c, game, roll), child)
    result = child["data"]["result"]
    setter, victim = roles(child, result["tier"])
    source = child["data"]["alpha_counter_source"]
    if (
        child["state"] != "complete"
        or game.pending(c, child["id"])
        or result.get("total") != total
        or child["data"]["character_ids"].get(source["attacker"]["entity"])
        != source["attacker"]["incarnation"]
    ):
        raise WorkflowError("Finish the original Beneath roll and all actual consequences")
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    rows = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == child["id"],
                choices.c.kind.like("beneath_%"),
            )
        )
        .mappings()
        .all()
    )
    answers: dict[str, ChoiceAnswer] = {}
    events: dict[str, str] = {}
    ids: dict[str, str] = {}
    for row in rows:
        kind = row["kind"]
        owner = setter if kind in ("beneath_select", "beneath_punishment") else victim
        if row["actor_id"] != owner.entity or kind in ids:
            raise WorkflowError("Keep each original Beneath choice and its independent owner")
        ids[kind] = row["id"]
        if row["state"] == "completed_by_child" and kind in (
            "beneath_response_play",
            "beneath_defeat",
        ):
            continuation = game.action(c, result.get("response_play"))
            if (
                continuation["parent_id"] != child["id"]
                or continuation["actor_id"] != victim.entity
                or continuation["state"] != "complete"
                or not continuation["data"].get("receipt")
                or game.pending(c, continuation["id"])
                or kind == "beneath_defeat"
                and continuation["data"]["play"] != "defeat"
            ):
                raise WorkflowError("Complete the affected original Girl's actual response Play")
            continue
        if row["state"] == "completed_by_work" and kind == "beneath_punishment":
            from girlframe.services.m3_beneath import discipline_action, work_root

            work = t.m3["m3_required_work"]
            identity = result.get("punishment_work")
            original = (
                c.execute(
                    sa.select(work).where(
                        work.c.campaign_id == game.store.campaign_id, work.c.id == identity
                    )
                )
                .mappings()
                .first()
            )
            if (
                original is None
                or discipline_action(game, c, dict(original), allow_archived=True) != child["id"]
                or json.loads(original["body_json"]).get("continuation") != row["id"]
            ):
                raise WorkflowError("Keep the exact source-owned Punishment and continuation")
            for pending in c.execute(
                sa.select(work).where(
                    work.c.campaign_id == game.store.campaign_id,
                    work.c.scene_id == original["scene_id"],
                    work.c.state != "resolved",
                )
            ).mappings():
                root = work_root(game, c, dict(pending))
                if root is not None and root["id"] == identity:
                    raise WorkflowError("Resolve every actual immediate Punishment consequence")
            continue
        if row["state"] != "answered" or kind not in (
            "beneath_select",
            "beneath_details",
            "beneath_pin_response",
        ):
            raise WorkflowError("Resolve this actual Beneath result through its owned source")
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
                audit["kind"] != "m3.choice_resolved"
                or audit["actor_id"] != owner.entity
                or payload.get("action_id") != child["id"]
                or payload.get("choice_id") != row["id"]
            ):
                raise WorkflowError("Recover the exact current Beneath response before completion")
            # The current event precedes its immutable response insert. Only this
            # exact response may wait for the existing post-response callback.
            return False
        answers[kind] = _response(
            game, c, child["id"], row["id"], response_event, int(owner.entity), kind
        )
        events[kind] = response_event
    selected = answers.get("beneath_select")
    if selected is None or list(selected.options) != result.get("beneath_effects"):
        raise WorkflowError("Preserve the exact actual result owner's Beneath decisions")
    legal_choices(result["tier"], selected.options)
    effect_event = events.get("beneath_details", events["beneath_select"])
    historical = _history(c, game, effect_event)
    expected = dict(
        kind="beneath_choice",
        action=child["id"],
        choice=ids["beneath_select"],
        owner=setter.entity,
        owner_character=str(setter.incarnation),
        target=victim.entity,
        target_character=str(victim.incarnation),
        options=",".join(selected.options),
        text=selected.text,
    )
    if expected not in historical.facts or expected not in state.facts:
        raise WorkflowError("Preserve the canonical effects from the actual owned Beneath choice")
    if set(selected.options) & {"bond", "damage"} and "beneath_details" not in answers:
        raise WorkflowError("Keep the affected Girl's private actual resource selection")
    if "pin" in selected.options:
        answer = answers.get("beneath_pin_response")
        if answer is None:
            raise WorkflowError("The actual pinned Girl must choose her own response")
        if answer.options == ("play",):
            if "beneath_response_play" not in ids:
                raise WorkflowError("Complete the original pinned Girl's actual response Play")
        elif not answer.text.strip() or answer.text != result.get("pinned_response"):
            raise WorkflowError("Keep the original pinned Girl's independently authored response")
    if "punish" in selected.options and "beneath_punishment" not in ids:
        raise WorkflowError("Finish the actual selected Punishment before closing the counter")
    return True
