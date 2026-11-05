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
REDIRECT_KIND = "mockingbird_redirect_handler_void"
REDIRECT_GIRL_KIND = "mockingbird_redirect_handler_girl_void"


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
    redirect: bool = False,
) -> None:
    from girlframe.engine.m3_mockingbird import SEX as SEX_RULE
    from girlframe.engine.m3_mockingbird import owns
    from girlframe.services.m3_medical import MedicalService

    meta = action["data"]["mockingbird"]
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
    source_kind = (
        (REDIRECT_GIRL_KIND if girl_rules else REDIRECT_KIND)
        if redirect
        else (GIRL_KIND if girl_rules else KIND)
    )
    expected_kind = "mockingbird_sex_restore" if redirect else "mockingbird_sex_high_commit"
    expected_human = meta["parties"][0]["controller"] if redirect else int(action["actor_id"])
    if (
        action["data"]["play"] != "mockingbird_sex"
        or meta["play"] != "mockingbird_sex"
        or action["data"]["result"]["tier"] != ("mid" if redirect else "high")
        or actual_choice is None
        or actual_choice["kind"] != expected_kind
        or actual_choice["action_id"] != action["id"]
        or actual_choice["actor_id"] != str(expected_human)
        or not owns(state, ActorRef.model_validate(meta["actor"]), SEX_RULE)
    ):
        raise WorkflowError(
            "Use the genuine owned source intimacy effect, never another tier or action"
        )
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    selection = meta.get("sex_transfer") if redirect else None
    if (
        actual.rules not in (("handler_girl",) if girl_rules else ("handler", "director"))
        or not actual.alive
        or (
            target.model_dump(mode="json") != selection["destination"]
            if selection
            else target.model_dump(mode="json") != meta["parties"][0]["actor"]
        )
    ):
        raise WorkflowError("Use this source interaction's actual physiological destination")
    identity = str(
        uuid5(NAMESPACE_URL, "girlframe:" + source_kind + ":" + action["id"] + ":" + choice)
    )
    if any(x["id"] == identity for x in meta.get("followups", ())):
        raise WorkflowError("Resume this actual destination's existing Void source")
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
        effect_controller=expected_human,
        redirect=redirect,
        transfer=dict(selection) if selection else None,
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
        if body.get("source_pdf") != 19 or body.get("kind") not in (
            KIND,
            GIRL_KIND,
            REDIRECT_KIND,
            REDIRECT_GIRL_KIND,
        ):
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
    from girlframe.engine.m3_mockingbird_sex import assets
    from girlframe.services.m3_mockingbird_effects import source_trigger

    action = game.action(c, body["source_action"])
    meta = action["data"]["mockingbird"]
    original = next((x for x in meta["followups"] if x["id"] == row["id"]), None)
    redirect = source_kind in (REDIRECT_KIND, REDIRECT_GIRL_KIND)
    expected_human = meta["parties"][0]["controller"] if redirect else int(action["actor_id"])
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
        original is None
        or row["kind"] != source_kind
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
        or bool(body.get("redirect")) != redirect
        or audit is None
        or audit["actor_id"] != str(expected_human)
        or json.loads(audit["payload_json"]).get("action_id") != action["id"]
        or json.loads(audit["payload_json"]).get("choice_id") != body["source_choice"]
        or saved is None
        or fact not in saved.facts
    ):
        raise ValueError(
            "Recover the actual authenticated intimacy response and physiological source"
        )
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
    total = (
        receipt["pre_total"] + sum(x["amount"] for x in action["data"]["modifiers"])
        if receipt
        else 0
    )
    if (
        response is None
        or response.kind
        != ("mockingbird_sex_restore" if redirect else "mockingbird_sex_high_commit")
        or response.action_id != action["id"]
        or response.actor_id != str(expected_human)
        or receipt != action["data"]["receipt"]
        or (not 8 <= total <= 10 if redirect else total < 11)
        or action["data"]["result"]["tier"] != ("mid" if redirect else "high")
    ):
        raise ValueError("Prove the actual source tier and owned response; labels cannot stand in")
    source_trigger(game, c, action, saved)
    if not redirect:
        if answer != ChoiceAnswer(flag=True) or meta["parties"][0]["actor"] != actor.model_dump(
            mode="json"
        ):
            raise ValueError("Prove the actual original high initiator's committed consequence")
        return
    selection = body.get("transfer")
    if (
        selection is None
        or selection["destination"] != actor.model_dump(mode="json")
        or actor.model_dump(mode="json") not in [x["actor"] for x in meta["parties"]]
        or answer is None
        or not answer.text.strip()
        or answer.model_copy(update={"text": ""}) != ChoiceAnswer()
        or answer.text != selection["restore"]
    ):
        raise ValueError("Prove this actual redirected Void's source and destination parties")
    selected = c.execute(
        sa.select(choices.c.kind, choices.c.actor_id, responses.c.answer_json)
        .join(
            responses,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.id == selection["caster_choice"],
        )
    ).first()
    cast_answer = ChoiceAnswer.model_validate_json(selected.answer_json) if selected else None
    if (
        selected is None
        or selected.kind != "mockingbird_sex_redirect"
        or selected.actor_id != str(action["actor_id"])
        or cast_answer is None
        or cast_answer.fields
        != {
            "source_asset": selection["source_asset"],
            "destination": actor.token,
            "destination_asset": "",
        }
    ):
        raise ValueError(
            "Only the genuine caster's actual source selection grants this destination"
        )
    source = ActorRef.model_validate(meta["parties"][0]["actor"])
    history = t.m2["m2_state_history"]
    previous = c.scalar(
        sa.select(history.c.body_json)
        .select_from(history.join(t.events, history.c.event_id == t.events.c.id))
        .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < audit["seq"])
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    before = GameState.model_validate_json(previous) if previous else None
    old = (
        next((x for x in assets(before, source) if x.id == selection["source_asset"]), None)
        if before
        else None
    )
    new = next((x for x in assets(saved, source) if x.id == selection["source_asset"]), None)
    if (
        old is None
        or new is None
        or old.model_dump_json() != selection["source_snapshot"]
        or not old.void
        or new.void
        or new.description != answer.text
        or old.model_dump(exclude={"void", "description", "concealed"})
        != new.model_dump(exclude={"void", "description", "concealed"})
    ):
        raise ValueError(
            "The genuine source Asset must actually lose Void without repair or replacement"
        )


def prove_handler_void_source(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    _prove_handler_source(
        game,
        c,
        row,
        body,
        actor,
        source_kind=REDIRECT_KIND if row["kind"] == REDIRECT_KIND else KIND,
    )


def prove_handler_girl_void_source(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    if row["kind"] == "call_guest_handler_girl_void":
        from girlframe.services.m3_mockingbird_communion import prove_guest_girl_void

        prove_guest_girl_void(game, c, row, body, actor)
        return
    _prove_handler_source(
        game,
        c,
        row,
        body,
        actor,
        source_kind=REDIRECT_GIRL_KIND if row["kind"] == REDIRECT_GIRL_KIND else GIRL_KIND,
    )


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
    allowed = (GIRL_KIND, REDIRECT_GIRL_KIND) if girl_rules else (KIND, REDIRECT_KIND)
    if row is None or row["state"] != "resolved" or row["kind"] not in allowed:
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
    if (
        c.scalar(
            sa.select(t.m3["m3_required_work"].c.kind)
            .where(
                t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                t.m3["m3_required_work"].c.id == identity,
            )
            .limit(1)
        )
        == "call_guest_handler_girl_void"
    ):
        from girlframe.services.m3_mockingbird_communion import complete_guest_girl_void

        complete_guest_girl_void(game, c, identity, event, viewer, key)
        return
    _complete_handler_void(game, c, identity, event, viewer, key, girl_rules=True)


def stage_redirect_handler_void(
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
    _stage_handler_void(
        game, c, state, action, target, choice, event, girl_rules=girl_rules, redirect=True
    )
