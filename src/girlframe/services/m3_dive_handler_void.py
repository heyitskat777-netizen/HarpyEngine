"""Real nearby Directors retain Handler physiology under an owned Dive effect."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_void import require
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

KIND = "dive_handler_void"


def stage(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    *,
    source_choice: str,
    step: int,
    actor: ActorRef,
    candidates: tuple[ActorRef, ...],
    event: str,
) -> None:
    from girlframe.engine.m3_dive import nearby_directors
    from girlframe.services.m3_medical import MedicalService
    from girlframe.services.m3_mockingbird_communion import _cast_npcs

    meta = action["data"]["dive"]
    ordinary = any(
        x.get("kind") == "dive_effect"
        and x.get("action") == action["id"]
        and x.get("step") == str(step)
        and x.get("actor") == actor.model_dump_json()
        and x.get("option") == "nearby_npcs_gain_void"
        and x.get("source_event") == event
        for x in state.facts
    )
    guest = any(
        x.get("kind") == "call_guest_director_void"
        and x.get("event") == event
        and x.get("actor") == actor.model_dump_json()
        and any(
            call.id == x.get("session")
            and call.source_action == action["id"]
            and call.source_choice == source_choice
            and 1000 + call.step == step
            and call.option == "nearby_npcs_gain_void"
            and call.guest == actor
            and call.choice_event
            for call in state.mockingbird.calls
        )
        for x in state.facts
    )
    if not ordinary and not guest:
        raise WorkflowError("Only the actual applied nearby-NPC Void effect creates this source.")
    if ordinary and not guest and actor.model_dump(mode="json") != meta["actor"]:
        raise WorkflowError("Retain the actual original Dive actor.")
    if set(candidates) != set(nearby_directors(state, actor, _cast_npcs(action))):
        raise WorkflowError("Every actual nearby Director retains her own source consequence.")
    _, appointment = MedicalService(game.store)._handler(c)
    for target in dict.fromkeys(candidates):
        actual = resolve(
            state, target, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if target.kind != "npc" or actual.rules != "director" or not actual.alive:
            raise WorkflowError("Use the actual original living Director, never a proxy Handler.")
        identity = str(
            uuid5(
                NAMESPACE_URL,
                "girlframe:dive-handler-void:"
                + action["id"]
                + ":"
                + str(step)
                + ":"
                + target.token,
            )
        )
        if any(x["id"] == identity for x in meta.get("handler_void_followups", ())):
            raise WorkflowError("Resume this actual Director's already-owned consequence.")
        changed, _ = require(
            state, target, work=identity, source_event=event, appointment=appointment
        )
        for field in GameState.model_fields:
            setattr(state, field, getattr(changed, field))
        continuation = game.request(
            c,
            action,
            actual.controller,
            KIND,
            dict(work_id=identity, step=step, owner=target.model_dump(mode="json")),
        )
        body = dict(
            id=identity,
            kind=KIND,
            owner=target.model_dump(mode="json"),
            character=target.incarnation,
            controller=actual.controller,
            source_action=action["id"],
            source_choice=source_choice,
            source_event=event,
            step=step,
            caster=actor.model_dump(mode="json"),
            source_pdf=19,
            rule_source_pdf=24,
            appointment=appointment,
            continuation=continuation,
            immediate=True,
        )
        meta.setdefault("handler_void_followups", []).append(body)
        state.facts.append(
            dict(
                kind=KIND + "_source",
                id=identity,
                source_event=event,
                body=json.dumps(body, sort_keys=True),
            )
        )


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    table = t.m3["m3_required_work"]
    for body in action["data"].get("dive", {}).get("handler_void_followups", ()):
        if c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id, table.c.id == body["id"]
            )
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            body["id"],
            body["controller"],
            body["controller"],
            KIND,
            body,
            body["source_event"],
        )


def prove_handler_void_source(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    action = game.action(c, body["source_action"])
    meta = action["data"]["dive"]
    original = next(
        (x for x in meta.get("handler_void_followups", ()) if x["id"] == row["id"]), None
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == body["source_event"],
        )
    )
    proof = GameState.model_validate_json(raw) if raw else None
    fact = dict(
        kind=KIND + "_source",
        id=row["id"],
        source_event=body["source_event"],
        body=json.dumps(body, sort_keys=True),
    )
    if (
        row["kind"] != KIND
        or row["revision"] != 1
        or row["event_id"] != body["source_event"]
        or row["scene_id"] != action["scene_id"]
        or row["campaign_context"]
        or row["owner_id"] != str(body["controller"])
        or row["subject_id"] != str(body["controller"])
        or original is None
        or any(original.get(k) != v for k, v in body.items())
        or actor.model_dump(mode="json") != body["owner"]
        or actor.kind != "npc"
        or proof is None
        or fact not in proof.facts
    ):
        raise WorkflowError("Recover the real original nearby Director Void source.")
    actual = resolve(
        proof, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.rules != "director" or actual.controller != body["controller"] or not actual.alive:
        raise WorkflowError("The source must identify the actual original Director body.")
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
    if audit is None:
        raise WorkflowError("Recover the authenticated effect event.")
    if audit["kind"] == "m3.call_response":
        from girlframe.services.m3_mockingbird_communion import prove_director_guest_source

        prove_director_guest_source(
            game,
            c,
            action["id"],
            body["source_choice"],
            body["step"],
            body["source_event"],
            ActorRef.model_validate(body["caster"]),
            actor,
        )
        return
    from girlframe.engine.m3_dive import nearby_directors
    from girlframe.services.m3_dive import _handler_controller
    from girlframe.services.m3_mockingbird_communion import _cast_npcs

    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    response = c.execute(
        sa.select(choices.c.kind, choices.c.action_id, choices.c.actor_id)
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
    step = meta["steps"][body["step"]]
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if (
        response is None
        or response.kind != "dive_effect"
        or response.action_id != action["id"]
        or response.actor_id != audit["actor_id"]
        or response.actor_id != str(_handler_controller(meta))
        or body["caster"] != meta["actor"]
        or actor
        not in nearby_directors(proof, ActorRef.model_validate(body["caster"]), _cast_npcs(action))
        or json.loads(audit["payload_json"]).get("choice_id") != body["source_choice"]
        or step["option"] != "nearby_npcs_gain_void"
        or step["applied_event"] != body["source_event"]
        or receipt is None
        or json.loads(receipt) != action["data"]["receipt"]
        or not any(
            x.get("kind") == "dive_effect"
            and x.get("action") == action["id"]
            and x.get("step") == str(body["step"])
            and x.get("option") == "nearby_npcs_gain_void"
            and x.get("source_event") == body["source_event"]
            for x in proof.facts
        )
    ):
        raise WorkflowError(
            "Only the authentic rolled Dive and owned nearby-NPC effect authorize this consequence."
        )


def complete_handler_void(
    game: "GameService",
    c: Connection,
    work: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.services.m3_dive import _next
    from girlframe.services.m3_handler_void import HandlerVoidService, completed_effect

    completed_effect(game, c, work, event)
    _, row, _ = HandlerVoidService(game.store, game)._proof(c, work)
    body = json.loads(row["body_json"])
    action = game.action(c, body["source_action"])
    actual = next(x for x in action["data"]["dive"]["handler_void_followups"] if x["id"] == work)
    if actual.get("completed_event"):
        return
    pending = next(
        (x for x in game.pending(c, action["id"]) if x["id"] == actual["continuation"]), None
    )
    if pending is None or pending["kind"] != KIND:
        raise WorkflowError("Recover the actual pending Director physiology continuation.")
    choices = t.m2["m2_choices"]
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
    _next(game, c, state, action)
    game.save_action(c, action)
    audit_actor = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if audit_actor is None:
        raise WorkflowError("Recover the actual completing physiological source event.")
    prior = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    completed = game.event(
        c,
        viewer.user_id if viewer else audit_actor,
        key,
        "m3.dive_handler_void_completed",
        state,
        event_index=1 if prior is None else prior + 1,
        action_id=action["id"],
        work_id=work,
    )
    if action["state"] == "complete":
        from girlframe.services.m3_mockingbird_communion import CallService

        CallService(game)._source_callbacks(c, action, completed, viewer, key)
