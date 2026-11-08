"""Actual Sex Asset effects and source-owned Void continuation; draft, not release evidence."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_mockingbird_sex import assets, void_criteria
from girlframe.engine.m3_void import start_threshold
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

CONTINUATION = "mockingbird_sex_void_threshold"


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def record_effect(
    game: "GameService",
    c: Connection,
    state: GameState,
    before: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    affected: tuple[ActorRef, ...],
    effect: str,
    details: dict[str, Any],
) -> None:
    event = action["data"]["response_event"]
    meta = action["data"]["mockingbird"]
    if row["action_id"] != action["id"] or not effect or not affected:
        raise WorkflowError("Use this exact actual intimacy response and affected originals")
    identity = str(uuid5(NAMESPACE_URL, "girlframe:sex-effect:" + action["id"] + ":" + row["id"]))
    if any(
        x.get("kind") == "mockingbird_sex_effect" and x.get("id") == identity for x in state.facts
    ):
        raise WorkflowError("This actual source response already applied its effects")
    record = dict(
        id=identity,
        action=action["id"],
        choice=row["id"],
        choice_kind=row["kind"],
        effect_controller=int(row["actor_id"]),
        event=event,
        effect=effect,
        affected=[x.model_dump(mode="json") for x in affected],
        details=details,
        before={x.token: [y.model_dump_json() for y in assets(before, x)] for x in affected},
        after={x.token: [y.model_dump_json() for y in assets(state, x)] for x in affected},
    )
    meta.setdefault("sex_effects", []).append(record)
    state.facts.append(
        dict(
            kind="mockingbird_sex_effect",
            id=identity,
            action=action["id"],
            event=event,
            body=json.dumps(record, sort_keys=True),
        )
    )
    for actor in dict.fromkeys(affected):
        for raw_family in void_criteria(before, state, actor):
            family: Literal["girl", "frame"] = "girl" if raw_family == "girl" else "frame"
            work = str(uuid5(NAMESPACE_URL, identity + ":void:" + actor.token + ":" + family))
            changed, threshold = start_threshold(
                state,
                profiles(c, game.store.campaign_id),
                actor,
                family,
                event,
                work,
                source_action=action["id"],
            )
            _copy(state, changed)
            owner = resolve(
                state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
            ).controller
            continuation = game.request(c, action, owner, CONTINUATION, dict(work_id=work))
            meta.setdefault("sex_followups", []).append(
                dict(
                    id=work,
                    owner=actor.model_dump(mode="json"),
                    character=actor.incarnation,
                    source_action=action["id"],
                    source_choice=row["id"],
                    source_event=event,
                    source_effect=identity,
                    source_pdf=19,
                    rule_source_pdf=36,
                    reason="mockingbird_sex",
                    details=dict(family=family),
                    threshold=threshold.id,
                    continuation=continuation,
                    controller=owner,
                    immediate=True,
                )
            )


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    table = t.m3["m3_required_work"]
    for body in action["data"].get("mockingbird", {}).get("sex_followups", ()):
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
            "void_threshold",
            body,
            body["source_event"],
        )


def prove_void_source(
    game: "GameService", c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    action = game.action(c, body["source_action"])
    meta = action["data"]["mockingbird"]
    item = next((x for x in meta.get("sex_followups", ()) if x["id"] == first["id"]), None)
    record = next(
        (x for x in meta.get("sex_effects", ()) if x["id"] == body["source_effect"]), None
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    after = GameState.model_validate_json(raw) if raw else None
    history = t.m2["m2_state_history"]
    previous = (
        c.scalar(
            sa.select(history.c.body_json)
            .select_from(history.join(t.events, history.c.event_id == t.events.c.id))
            .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < event["seq"])
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if event
        else None
    )
    before = GameState.model_validate_json(previous) if previous else None
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    response = c.execute(
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
            choices.c.id == body["source_choice"],
            responses.c.event_id == body["source_event"],
        )
    ).first()
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if (
        item is None
        or record is None
        or event is None
        or after is None
        or before is None
        or first["kind"] != "void_threshold"
        or first["revision"] != 1
        or first["owner_id"] != str(item["controller"])
        or first["subject_id"] != str(item["controller"])
        or first["scene_id"] != action["scene_id"]
        or first["event_id"] != body["source_event"]
        or any(body.get(k) != v for k, v in item.items() if k != "completed_event")
        or body["owner"] != actor.model_dump(mode="json")
        or body["character"] != actor.incarnation
        or response is None
        or response.kind != record["choice_kind"]
        or response.actor_id != str(record["effect_controller"])
        or event["actor_id"] != response.actor_id
        or json.loads(event["payload_json"]).get("choice_id") != record["choice"]
        or record["event"] != body["source_event"]
        or receipt is None
        or json.loads(receipt) != action["data"]["receipt"]
        or action["data"]["play"] != "mockingbird_sex"
        or action["data"]["result"]["tier"] not in ("mid", "high")
        or dict(
            kind="mockingbird_sex_effect",
            id=record["id"],
            action=action["id"],
            event=record["event"],
            body=json.dumps(record, sort_keys=True),
        )
        not in after.facts
        or body["details"]["family"] not in void_criteria(before, after, actor)
        or record["before"].get(actor.token) != [x.model_dump_json() for x in assets(before, actor)]
        or record["after"].get(actor.token) != [x.model_dump_json() for x in assets(after, actor)]
    ):
        raise WorkflowError("Recover the real source intimacy response and actual Asset corruption")
    from girlframe.engine.m2 import tier

    level = tier(
        json.loads(receipt)["pre_total"] + sum(x["amount"] for x in action["data"]["modifiers"])
    )
    expected = {
        "high_infect": ("high", "mockingbird_sex_rewrite"),
        "collect_self": ("mid", "mockingbird_sex_self"),
        "collect_redirect": ("mid", "mockingbird_sex_rewrite"),
    }.get(record["effect"])
    if (
        expected is None
        or (level, record["choice_kind"]) != expected
        or action["data"]["result"]["tier"] != level
    ):
        raise WorkflowError("Only an actual printed source corruption can open this Void threshold")
    source_trigger(game, c, action, after)
    # Source responses are parsed, never treated as mere labels or trust markers.
    ChoiceAnswer.model_validate_json(response.answer_json)


def complete_void_continuation(
    game: "GameService",
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.services.m3_void import source

    row, body, _ = source(game, c, identity)
    if row["state"] != "resolved":
        raise WorkflowError("Resolve this actual original Void consequence first")
    action = game.action(c, body["source_action"])
    actual = next(x for x in action["data"]["mockingbird"]["sex_followups"] if x["id"] == identity)
    pending = next(
        (x for x in game.pending(c, action["id"]) if x["id"] == actual["continuation"]), None
    )
    if pending is None:
        return
    if pending["kind"] != CONTINUATION:
        raise WorkflowError("Recover the exact intimacy Void continuation")
    c.execute(
        t.m2["m2_choices"]
        .update()
        .where(
            t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_choices"].c.id == pending["id"],
            t.m2["m2_choices"].c.state == "pending",
        )
        .values(state="completed_by_work", revision=t.m2["m2_choices"].c.revision + 1)
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
        raise WorkflowError("Preserve the actual source completion event")
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    completed = game.event(
        c,
        viewer.user_id if viewer else source_actor,
        key,
        "m3.mockingbird_sex_void_completed",
        state,
        event_index=(index or 0) + 1,
        action_id=action["id"],
        work_id=identity,
    )
    from girlframe.services.m3_mockingbird import synchronize as risk_sync

    risk_sync(game, c, action, completed)
    game.save_action(c, action)
    if action["state"] == "complete" and action["data"].get("battle_counter_source"):
        from girlframe.services.m3_battle import complete_counter_play

        complete_counter_play(game, c, action, completed, viewer, key)
    elif action["state"] == "complete" and action["data"].get("gorgon_counter_source"):
        from girlframe.services.m3_gorgon_play import complete_response

        complete_response(game, c, action, completed, viewer, key)


def source_trigger(
    game: "GameService",
    c: Connection,
    action: dict[str, Any],
    proof: GameState,
    *,
    handler_required: bool = True,
) -> tuple[ActorRef, int]:
    """Recover original rule parties and fictional Handler from the signed declaration snapshot."""
    from girlframe.engine.m3_actor_state import SceneCast
    from girlframe.engine.m3_actors import fingerprint
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.engine.m3_mockingbird import PERSON, SEX, owns

    meta = action["data"]["mockingbird"]
    trigger = next((x for x in proof.mockingbird.triggers if x.id == meta["trigger"]), None)
    expected = "mockingbird_sex" if handler_required else "mockingbird_person"
    if trigger is None or trigger.action != action["id"] or trigger.play != expected:
        raise WorkflowError("Recover the actual owned interaction trigger")
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == trigger.source_event,
        )
    )
    original = GameState.model_validate_json(raw) if raw else None
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    actual_cast = (
        next((x for x in original.scene_casts if x.id == trigger.scene), None) if original else None
    )
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == trigger.source_event,
            )
        )
        .mappings()
        .first()
    )
    declared = (
        next((x for x in original.mockingbird.triggers if x.id == trigger.id), None)
        if original
        else None
    )
    caster = ActorRef.model_validate(meta["actor"])
    if (
        original is None
        or actual_cast is not None
        and fingerprint(actual_cast) != fingerprint(cast)
        or fingerprint(cast) != meta["cast_sha256"]
        or declared is None
        or any(
            getattr(declared, key) != getattr(trigger, key)
            for key in (
                "id",
                "play",
                "actor",
                "scene",
                "channel",
                "cast_sha256",
                "source_event",
                "account",
            )
        )
        or [(x.actor, x.controller) for x in declared.parties]
        != [(x.actor, x.controller) for x in trigger.parties]
        or trigger.cast_sha256 != meta["cast_sha256"]
        or trigger.actor != caster
        or not owns(original, caster, SEX if handler_required else PERSON)
        or handler_required
        and any(x.decision != "accepted" for x in trigger.parties)
        or [x.actor.model_dump(mode="json") for x in trigger.parties]
        != [x["actor"] for x in meta["parties"]]
        or audit is None
        or audit["kind"] != "m3.mockingbird_trigger"
        or audit["actor_id"] != str(action["actor_id"])
        or json.loads(audit["payload_json"]).get("trigger") != trigger.id
    ):
        raise WorkflowError("Prove original cast, actual rule and original authored trigger")
    if not handler_required:
        return caster, int(action["actor_id"])
    if meta["judge"] is None:
        handler = active_handler(original)
        if (
            handler is None
            or meta["judge_controller"] != original.handler
            or cast.adjudicator is not None
        ):
            raise WorkflowError("No invented fictional Handler or successor may own this source")
        return handler, int(meta["judge_controller"])
    handler = ActorRef.model_validate(meta["judge"])
    role = next((x for x in cast.roles if x.actor == handler), None)
    npc = (
        next(
            (
                x
                for x in original.world.npcs
                if x.id == handler.entity and x.alive and "director" in x.jobs
            ),
            None,
        )
        if original.world
        else None
    )
    signed = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == meta["judge_source"],
            )
        )
        .mappings()
        .first()
    )
    if (
        handler.kind != "npc"
        or role is None
        or npc is None
        or cast.adjudicator != handler
        or role.controller != meta["judge_controller"]
        or npc.controller != role.controller
        or signed is None
        or signed["actor_id"] != str(role.controller)
        or json.loads(signed["payload_json"]).get("action") != "adjudicate"
        or json.loads(signed["payload_json"]).get("scene") != cast.id
    ):
        raise WorkflowError("Prove this actual original Director's scoped adjudication")
    return handler, role.controller


def allowed_archived(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> frozenset[tuple[str, str]]:
    """Only original bodies actually ended by this real Sex Void source remain history."""
    if action["data"].get("mockingbird", {}).get("play") != "mockingbird_sex":
        return frozenset()
    from girlframe.services.m3_harpy_defeat import ended_actor_source
    from girlframe.services.m3_void import source

    result = set()
    for item in action["data"]["mockingbird"].get("sex_followups", ()):
        row, body, actor = source(game, c, item["id"])
        if row["state"] != "resolved" or body["source_action"] != action["id"]:
            continue
        threshold = next(
            (
                x
                for x in state.void_thresholds
                if x.id == body["threshold"] and item["id"] in x.source_works and x.actor == actor
            ),
            None,
        )
        ending = ended_actor_source(game, c, state, actor)
        if threshold is None or ending is None or threshold.response_event != ending:
            continue
        if threshold.stage == "converted":
            converted_body = (
                next(
                    (
                        x
                        for x in state.harpy_states
                        if x.id == threshold.resulting_actor.entity
                        and x.origin == actor
                        and x.source_event == ending
                    ),
                    None,
                )
                if threshold.resulting_actor
                else None
            )
            if converted_body is None:
                raise WorkflowError("Prove the exact source original-to-Harpy conversion")
        elif threshold.stage != "dead":
            continue
        result.add((actor.entity, str(actor.incarnation)))
    return frozenset(result)
