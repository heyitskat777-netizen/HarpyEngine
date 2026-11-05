"""Exact held original Sex Play consequences, proven from actual committed source events."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

KIND = "mockingbird_handler_void"
GIRL_KIND = "mockingbird_handler_girl_void"


def _stage_handler_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    choice: str,
    event: str,
    *,
    girl_rules: bool,
) -> None:
    meta = action["data"]["mockingbird"]
    from girlframe.engine.m3_mockingbird import SEX as SEX_RULE
    from girlframe.engine.m3_mockingbird import owns
    from girlframe.engine.m3_mockingbird_state import SEX

    actual_choice = (
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
        action["data"]["play"] != SEX
        or meta["play"] != SEX
        or action["data"]["result"]["tier"] != "high"
        or actual_choice is None
        or actual_choice["kind"] != "mockingbird_sex_high_commit"
        or actual_choice["action_id"] != action["id"]
        or actual_choice["actor_id"] != str(action["actor_id"])
        or not owns(state, ActorRef.model_validate(meta["actor"]), SEX_RULE)
    ):
        raise WorkflowError(
            "Use the actual owned high Sex Play effect, never another source action"
        )
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    source_kind = GIRL_KIND if girl_rules else KIND
    if (
        actual.rules not in (("handler_girl",) if girl_rules else ("handler", "director"))
        or not actual.alive
        or target.model_dump(mode="json") != meta["parties"][0]["actor"]
    ):
        raise WorkflowError(
            "Use this actual source interaction's original living Handler counterpart"
        )
    identity = str(
        uuid5(NAMESPACE_URL, "girlframe:" + source_kind + ":" + action["id"] + ":" + choice)
    )
    if any(x["id"] == identity for x in meta.get("followups", ())):
        raise WorkflowError("Resume this actual Handler's existing Void consequence")
    from girlframe.services.m3_medical import MedicalService

    _, appointment = MedicalService(game.store)._handler(c)
    context_source = None
    if girl_rules:
        from girlframe.engine.m3_handler_girl_void import require as require_girl_void

        changed, episode_id = require_girl_void(
            state,
            target,
            work=identity,
            event=event,
            appointment=appointment,
            judge=meta["judge_controller"],
            judge_actor=ActorRef.model_validate(meta["judge"]) if meta["judge"] else None,
            caster=ActorRef.model_validate(meta["actor"]),
            caster_controller=int(action["actor_id"]),
        )
        context_source = next(
            x.context_source for x in changed.handler_girl_void if x.id == episode_id
        )
    else:
        from girlframe.engine.m3_handler_void import require as require_handler_void

        changed, _ = require_handler_void(
            state, target, work=identity, source_event=event, appointment=appointment
        )
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))
    continuation = game.request(c, action, actual.controller, source_kind, dict(work_id=identity))
    body = dict(
        id=identity,
        kind=source_kind,
        controller=actual.controller,
        owner=target.model_dump(mode="json"),
        character=target.incarnation,
        source_action=action["id"],
        source_choice=choice,
        source_event=event,
        source_pdf=19,
        rule_source_pdf=36,
        caster=meta["actor"],
        caster_controller=int(action["actor_id"]),
        context_source=context_source,
        appointment=appointment,
        judge=meta["judge_controller"],
        judge_actor=meta["judge"],
        counterpart=target.model_dump(mode="json"),
        continuation=continuation,
        immediate=True,
    )
    meta.setdefault("followups", []).append(body)
    state.facts.append(
        dict(
            kind=source_kind + "_source",
            id=identity,
            action=action["id"],
            actor=target.model_dump_json(),
            event=event,
            body=json.dumps(body, sort_keys=True),
        )
    )


def stage_handler_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    choice: str,
    event: str,
) -> None:
    _stage_handler_void(game, c, state, action, target, choice, event, girl_rules=False)


def stage_handler_girl_void(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorRef,
    choice: str,
    event: str,
) -> None:
    _stage_handler_void(game, c, state, action, target, choice, event, girl_rules=True)


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    table = t.m3["m3_required_work"]
    for body in action["data"].get("mockingbird", {}).get("followups", ()):
        if body.get("source_pdf") != 19 or body.get("kind") not in (KIND, GIRL_KIND):
            continue
        if c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id, table.c.id == body["id"]
            )
        ):
            continue
        owner = body["controller"]
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            body["id"],
            owner,
            owner,
            body["kind"],
            body,
            body["source_event"],
        )


def _prove_handler_source(
    game: "GameService",
    c: Connection,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
    *,
    source_kind: str,
) -> None:
    action = game.action(c, body["source_action"])
    meta = action["data"]["mockingbird"]
    original = next(x for x in meta["followups"] if x["id"] == row["id"])
    if (
        row["kind"] != source_kind
        or row["revision"] != 1
        or row["event_id"] != body["source_event"]
        or row["owner_id"] != str(body["controller"])
        or row["subject_id"] != str(body["controller"])
        or row["scene_id"] != action["scene_id"]
        or row["campaign_context"]
        or any(original.get(k) != v for k, v in body.items())
        or actor.model_dump(mode="json") != body["owner"]
        or body["character"] != actor.incarnation
        or body["source_pdf"] != 19
        or body["rule_source_pdf"] != 36
    ):
        raise ValueError("Recover this actual original Handler's exact source Void consequence")
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == body["source_event"],
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == body["source_event"],
        )
    )
    saved = GameState.model_validate_json(raw) if raw else None
    fact = dict(
        kind=source_kind + "_source",
        id=row["id"],
        action=action["id"],
        actor=actor.model_dump_json(),
        event=body["source_event"],
        body=json.dumps(body, sort_keys=True),
    )
    if (
        audit is None
        or audit["actor_id"] != str(action["actor_id"])
        or payload.get("action_id") != action["id"]
        or payload.get("choice_id") != body["source_choice"]
        or saved is None
        or fact not in saved.facts
    ):
        raise ValueError(
            "Recover the actual authenticated Mockingbird effect and original Handler body"
        )

    from girlframe.engine.m3_mockingbird import SEX as SEX_RULE
    from girlframe.engine.m3_mockingbird import owns
    from girlframe.engine.m3_mockingbird_state import SEX

    responses, choices = t.m2["m2_responses"], t.m2["m2_choices"]
    response = c.execute(
        sa.select(choices.c.kind, choices.c.actor_id, choices.c.action_id, responses.c.answer_json)
        .join(
            responses,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == body["source_choice"],
            responses.c.event_id == body["source_event"],
        )
    ).first()
    immutable = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    receipt = json.loads(immutable) if immutable else None
    answer = ChoiceAnswer.model_validate_json(response.answer_json) if response else None
    trigger = next((x for x in saved.mockingbird.triggers if x.id == meta["trigger"]), None)
    caster = ActorRef.model_validate(meta["actor"])
    if (
        action["data"]["play"] != SEX
        or meta["play"] != SEX
        or response is None
        or response.kind != "mockingbird_sex_high_commit"
        or response.action_id != action["id"]
        or response.actor_id != audit["actor_id"]
        or response.actor_id != str(action["actor_id"])
        or answer != ChoiceAnswer(flag=True)
        or receipt is None
        or receipt != action["data"]["receipt"]
        or receipt["pre_total"] + sum(x["amount"] for x in action["data"]["modifiers"]) < 11
        or action["data"]["result"]["tier"] != "high"
        or not owns(saved, caster, SEX_RULE)
        or trigger is None
        or trigger.actor != caster
        or trigger.play != SEX
        or trigger.action != action["id"]
        or trigger.parties[0].actor != actor
        or any(x.decision != "accepted" for x in trigger.parties)
    ):
        raise ValueError(
            "Recover the actual immutable high Sex roll, owned trigger and effect response"
        )


def prove_handler_void_source(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    _prove_handler_source(game, c, row, body, actor, source_kind=KIND)


def prove_handler_girl_void_source(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    _prove_handler_source(game, c, row, body, actor, source_kind=GIRL_KIND)


def _complete_handler_void(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
    *,
    girl_rules: bool,
) -> None:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    source_kind = GIRL_KIND if girl_rules else KIND
    if row is None or row["state"] != "resolved" or row["kind"] != source_kind:
        raise WorkflowError("Finish the actual source Handler Void consequence before resuming")
    if girl_rules:
        from girlframe.services.m3_handler_girl_void import completed_effect as girl_completed

        girl_completed(game, c, identity, event)
    else:
        from girlframe.services.m3_handler_void import completed_effect

        completed_effect(game, c, identity, event)
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    actual = next(
        (x for x in action["data"]["mockingbird"]["followups"] if x["id"] == identity), None
    )
    if actual is None or actual["continuation"] != body["continuation"]:
        raise WorkflowError("Recover the original source continuation")
    choices = t.m2["m2_choices"]
    pending = next(
        (x for x in game.pending(c, action["id"]) if x["id"] == actual["continuation"]), None
    )
    if pending is None:
        return
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == pending["id"],
            choices.c.state == "pending",
        )
        .values(state="completed_by_work", revision=choices.c.revision + 1)
    )
    actual["completed_event"] = event
    state = load_state(c, game.store.campaign_id)
    if not game.pending(c, action["id"]):
        from girlframe.services.m3_mockingbird_plays import _finish

        _finish(game, c, state, action)
    game.save_action(c, action)
    source_actor = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if source_actor is None:
        raise WorkflowError("Recover the actual completing Handler Void event")
    prior_index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    completed = game.event(
        c,
        viewer.user_id if viewer else source_actor,
        key,
        "m3.mockingbird_void_completed",
        state,
        event_index=1 if prior_index is None else prior_index + 1,
        action_id=action["id"],
        work_id=identity,
    )
    from girlframe.services.m3_mockingbird import synchronize as synchronize_risk

    synchronize_risk(game, c, action, completed)
    game.save_action(c, action)
    if action["state"] == "complete" and action["data"].get("battle_counter_source"):
        from girlframe.services.m3_battle import complete_counter_play

        complete_counter_play(game, c, action, completed, viewer, key)
    elif action["state"] == "complete" and action["data"].get("gorgon_counter_source"):
        from girlframe.services.m3_gorgon_play import complete_response

        complete_response(game, c, action, completed, viewer, key)


def complete_handler_void(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    _complete_handler_void(game, c, identity, event, viewer, key, girl_rules=False)


def complete_handler_girl_void(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    _complete_handler_void(game, c, identity, event, viewer, key, girl_rules=True)
