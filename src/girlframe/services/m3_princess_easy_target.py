"""One real Princess-directed Newgirl source; no proxy actor or borrowed entitlement."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection, RowMapping

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine import m3_princess_sex as princess
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_princess_sex import HighDirection
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def controlled(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    prepared: PlayInput,
    channel: int,
    *,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from girlframe.services.m3_princess_sex import child_source, pre_roll_child

    if prepared.play != rules.PLAY or not prepared.source_work:
        return None
    candidate = next((x for x in princess.directions(state) if x.id == prepared.source_work), None)
    if candidate is None:
        return None
    if candidate.play != rules.PLAY:
        raise WorkflowError("Use only the original selected Easy Target directive")
    if action is None:
        return child_source(game, c, viewer, state, prepared, channel)
    value = controlled_source(game, c, state, action)
    if (
        value is None
        or value.id != candidate.id
        or value.completed_event
        or viewer.user_id != value.author_controller
        or channel != princess.get(state, value.session).cast.channel
        or prepared != PlayInput.model_validate(action["data"]["prepared"])
    ):
        raise WorkflowError("Reopen the exact directed Easy Target and original Princess author")
    pre_roll_child(game, c, state, action)
    return dict(action["data"]["princess_child"])


def controlled_source(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> HighDirection | None:
    meta = action["data"].get("easy_target", {})
    if not meta.get("princess_direction"):
        return None
    from girlframe.services.m3_princess_sex import _bound

    value = _bound(game, c, state, action)
    if (
        value is None
        or value.play != rules.PLAY
        or value.id != meta["princess_direction"]
        or value.target is not None
        or meta["actor"] != value.actor.model_dump(mode="json")
        or meta["caster"] != value.actor_controller
    ):
        raise WorkflowError("Prove the original native Newgirl and actual Princess author")
    return value


def injury_response(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    choice: str,
    event: str,
    owner: int,
    kind: str,
) -> ChoiceAnswer:
    from girlframe.services.m3_dose_up import _response
    from girlframe.services.m3_princess_sex import prove_response_author

    direction = controlled_source(game, c, state, action)
    if direction is None:
        return _response(game, c, action["id"], choice, event, owner, kind)
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id, choices.c.id == choice
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(responses).where(
                responses.c.campaign_id == game.store.campaign_id, responses.c.choice_id == choice
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or response is None
        or row["action_id"] != action["id"]
        or row["kind"] != kind
        or row["actor_id"] != str(owner)
        or owner != direction.actor_controller
        or response["event_id"] != event
        or response["actor_id"] != str(direction.author_controller)
        or prove_response_author(game, c, state, action, dict(row), event)
        != direction.author_controller
    ):
        raise WorkflowError("Recover the original Newgirl injury choice and actual author")
    return ChoiceAnswer.model_validate_json(response["answer_json"])


def _completion_author(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    value: HighDirection | None,
    event: str,
) -> int:
    """Only a real source answer, child performance, NPC consequence or Punishment."""
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_princess_sex import _performer_row

    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if audit is None or audit["actor_id"] is None:
        raise WorkflowError("Recover the actual Easy Target completion cause")
    payload = json.loads(audit["payload_json"])
    snapshot = _history(c, game, event)
    reactions = [x for x in rules.records(snapshot, rules.Reaction) if x.session == action["id"]]
    if audit["kind"] in ("m2.choice_resolved", "m3.choice_resolved"):
        choices = t.m2["m2_choices"]
        row = (
            c.execute(
                sa.select(choices).where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == payload.get("choice_id"),
                    choices.c.state == "answered",
                )
            )
            .mappings()
            .first()
        )
        if row is not None and payload.get("action_id") == row["action_id"]:
            if row["action_id"] == action["id"]:
                expected = (
                    str(value.author_controller)
                    if value is not None and _performer_row(value, action, dict(row))
                    else row["actor_id"]
                )
                if audit["actor_id"] == expected and (
                    row["kind"].startswith("easy_target_") or row["kind"] == "battle_target_damage"
                ):
                    return int(audit["actor_id"])
            elif any(
                x.performance_event == event and row["action_id"] in x.children for x in reactions
            ):
                child = game.action(c, row["action_id"])
                if child["parent_id"] == action["id"] and child["state"] == "complete":
                    return int(audit["actor_id"])
    matching = next((x for x in reactions if x.id == payload.get("work")), None)
    if matching is not None:
        if audit["kind"] == "m3.easy_target_performed":
            child = game.action(c, payload.get("child", ""))
            if (
                child["id"] in matching.children
                and child["parent_id"] == action["id"]
                and child["state"] == "complete"
                and child["actor_id"] == audit["actor_id"]
                and matching.consequence_event == event
            ):
                return int(audit["actor_id"])
        elif audit["kind"] == "m3.easy_target_npc_hurt_completed":
            hurt = next(
                (x for x in rules.records(snapshot, rules.NpcHurt) if x.id == payload.get("hurt")),
                None,
            )
            if (
                hurt
                and hurt.reaction == matching.id
                and hurt.completed_event == event
                and str(hurt.controller) == audit["actor_id"]
            ):
                return int(audit["actor_id"])
        elif audit["kind"] == "m3.easy_target_punished":
            case = next(
                (x for x in snapshot.role_punishments if x.id == payload.get("punishment")), None
            )
            if (
                case
                and case.source_kind == "easy_target"
                and case.action == action["id"]
                and case.source_work == matching.id
                and case.completion_event
                and matching.completed_event == case.completion_event
                and str(case.executor_controller) == audit["actor_id"]
            ):
                return int(audit["actor_id"])
    raise WorkflowError("Retain this Easy Target's genuine completed response or consequence")


def complete_directed(
    game: GameService, c: Connection, action: dict[str, Any], trigger: str
) -> None:
    from girlframe.services.m3_princess_sex import complete_child, synchronize

    if (
        action["data"].get("alpha_counter_source")
        and action["data"].get("easy_target")
        and action["state"] == "complete"
    ):
        from girlframe.services.m3_alpha import synchronize_counters

        synchronize_counters(game, c, trigger)
    if (
        not action["data"].get("princess_child")
        or not action["data"].get("easy_target")
        or action["state"] != "complete"
    ):
        return
    state = load_state(c, game.store.campaign_id)
    value = princess.direction(state, action["data"]["princess_child"]["direction"])
    if value.completed_event:
        return
    controlled_source(game, c, state, action)
    source = rules.get(state, rules.Session, action["id"])
    if not rules.settled(state, source) or any(
        x.session == source.id and not x.completed_event
        for x in rules.records(state, rules.Reaction)
    ):
        raise WorkflowError("Complete every real Easy Target reaction and consequence first")
    human = _completion_author(game, c, action, value, trigger)
    event = str(uuid4())
    complete_child(game, c, state, action, event)
    game.event(
        c,
        human,
        str(uuid4()),
        "m3.princess_directed_easy_target_completed",
        state,
        event_id=event,
        action_id=action["id"],
        parent=value.parent,
        direction=value.id,
        trigger_event=trigger,
    )
    synchronize(game, c, action, event)


def prove_completion(
    game: GameService, c: Connection, value: HighDirection, audit: RowMapping
) -> None:
    payload = json.loads(audit["payload_json"])
    child = game.action(c, value.child or "")
    meta = child["data"].get("easy_target", {})
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == child["id"],
        )
    )
    if (
        value.play != rules.PLAY
        or audit["kind"] != "m3.princess_directed_easy_target_completed"
        or payload.get("action_id") != child["id"]
        or payload.get("parent") != value.parent
        or payload.get("direction") != value.id
        or child["parent_id"] != value.parent
        or child["actor_id"] != value.actor.entity
        or child["data"].get("play") != value.play
        or meta.get("princess_direction") != value.id
        or meta.get("actor") != value.actor.model_dump(mode="json")
        or meta.get("caster") != value.actor_controller
        or value.target is not None
        or child["data"].get("princess_child", {}).get("author") != value.author_controller
        or child["state"] != "complete"
        or receipt is None
        or json.loads(receipt) != child["data"].get("receipt")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError("Prove the actual directed Easy Target and immutable receipt")
    if int(audit["actor_id"]) != _completion_author(
        game, c, child, value, payload.get("trigger_event", "")
    ):
        raise WorkflowError("Retain the actual human author of this Easy Target completion")
