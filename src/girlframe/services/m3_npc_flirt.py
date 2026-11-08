"""Actual native Girl/NPC Flirt choices and performed, judged followthrough."""

import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_flirt as rules
from girlframe.engine.m2 import FLIRT_QUESTIONS, ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, current_ref, depth, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_battle_npc import NARRATIVE
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_dose_up import _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _receipt_sha(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _copy(state: GameState, other: GameState) -> None:
    for field in GameState.model_fields:
        setattr(state, field, getattr(other, field))


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    Access(game.store).authorize(c, viewer, "plays", director_response=True)
    registry = Access(game.store).registry
    assert registry is not None
    for rule in (rules.RULE, "core.core.npcs", "core.core.npc-assets", "core.core.npc-tags"):
        registry.require_available(rule)


def _npc(state: GameState, ref: ActorRef) -> Npc:
    value = (
        next((x for x in state.world.npcs if x.id == ref.entity), None)
        if state.world and ref.kind == "npc"
        else None
    )
    if value is None or value.source_kind is not None or "director" in value.jobs:
        raise WorkflowError("Use an actual ordinary World NPC, not a Director/Wraith/PC alias")
    return value


def _event(
    game: GameService, c: Connection, event: str, kinds: tuple[str, ...], author: int | None = None
) -> dict[str, Any]:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] not in kinds
        or author is not None
        and row["actor_id"] != str(author)
    ):
        raise WorkflowError("Recover the actual canonical NPC Flirt source and human author")
    return dict(row)


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer)
    from girlframe.services.m3_princess_performer import acting_owner
    from girlframe.services.m3_princess_sex import child_source

    owner = acting_owner(game, c, viewer, prepared, state)
    direction = child_source(game, c, viewer, state, prepared, channel)
    actor = current_ref(state, owner)
    if owner != viewer.user_id and (
        direction is None
        or direction["actor"] != actor.model_dump(mode="json")
        or direction["actor_controller"] != owner
        or direction["author"] != viewer.user_id
    ):
        raise WorkflowError("Prove the original Princess direction for this real performer")
    target = prepared.target_actor
    if prepared.play != "flirt" or prepared.target is not None or target is None:
        raise WorkflowError("Flirt as your actual Girl with an actual NPC ActorRef")
    npc = _npc(state, target)
    cast = _cast(game, c, state, channel)
    bound = profiles(c, game.store.campaign_id)
    girl, other = resolve(state, actor, bound), resolve(state, target, bound)
    if (
        actor.kind != "pilot"
        or girl.rules != "girl_frame"
        or not girl.alive
        or girl.offstage_source
        or not npc.alive
        or not _visible(state, target, viewer.user_id)
        or not _visible(state, target, owner)
        or other.offstage_source
        or not all(
            any(x.actor == ref and x.controller == controller for x in cast.roles)
            for ref, controller in ((actor, owner), (target, npc.controller))
        )
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
    ):
        raise WorkflowError(
            "Use the genuine available original Girl/NPC and actual scene interaction"
        )
    approval = game.store.policy.m3_approval
    assert approval is not None
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Recover the actual current Handler before this source Play")
    meta = dict(
        actor_label=girl.label,
        target_label=other.label,
        handler=handler.model_dump(mode="json"),
        handler_controller=resolve(state, handler, bound).controller,
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        target_controller=npc.controller,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        registry=approval.registry_sha256,
        target_json=json.dumps(
            dict(
                id=npc.id,
                controller=npc.controller,
                jobs=npc.jobs,
                alive=npc.alive,
                source_kind=npc.source_kind,
            ),
            sort_keys=True,
        ),
        target_sha256=fingerprint(npc),
        target_position=other.position_sha256,
        table=sorted(
            {x.controller for x in cast.roles} | ({cast.facilitator} if cast.facilitator else set())
        ),
    )
    if direction is not None:
        meta["princess_direction"] = direction["direction"]
    return meta


def bind(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["npc_flirt"]
    meta["id"] = action["id"]
    rules.put(
        state,
        rules.Session(
            id=action["id"],
            actor=ActorRef.model_validate(meta["actor"]),
            target=ActorRef.model_validate(meta["target"]),
            controller=meta["target_controller"],
            actor_label=meta["actor_label"],
            target_label=meta["target_label"],
            cast=SceneCast.model_validate_json(json.dumps(meta["cast"])),
            registry=meta["registry"],
            target_json=meta["target_json"],
            target_sha256=meta["target_sha256"],
            target_position=meta["target_position"],
            event=event,
            princess_direction=meta.get("princess_direction"),
        ),
    )


def _actor_author(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], value: rules.Session
) -> int:
    from girlframe.services.m3_princess_sex import child_author

    author = child_author(game, c, state, action)
    scope = action["data"].get("princess_child")
    if value.princess_direction is None:
        if scope is not None or author is not None:
            raise WorkflowError("Preserve the original source's explicit directed provenance")
        return int(value.actor.entity)
    if scope is None or scope.get("direction") != value.princess_direction or author is None:
        raise WorkflowError("Prove the exact original Princess child before author override")
    return author


def _row_author(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> int:
    from girlframe.services.m3_princess_sex import decision_author

    subject = json.loads(row["body_json"]).get("subject")
    if row["kind"] in rules.KINDS and subject != action["data"]["npc_flirt"]["actor"]:
        return int(row["actor_id"])
    author = decision_author(game, c, state, action, row)
    return int(row["actor_id"]) if author is None else author


def _flirt_roll_source(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    value: rules.Session,
) -> tuple[str, int]:
    if value.princess_direction is None:
        return _roll_source(game, c, action)
    # Only this positively bound original Princess source separates actor and author.
    # Never rewrite the Action's actor to make a generic receipt proof accept it.
    author = _actor_author(game, c, _history(c, game, value.event), action, value)
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        .mappings()
        .first()
    )
    if receipt is None or json.loads(receipt["body_json"]) != action["data"].get("receipt"):
        raise WorkflowError("Recover the actual directed NPC Flirt SQL roll receipt")
    event = c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
            t.events.c.actor_id == str(author),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id") == receipt["id"],
        )
    )
    if (
        event is None
        or _actor_author(game, c, _history(c, game, str(event)), action, value) != author
    ):
        raise WorkflowError("Prove the actual directed NPC Flirt roll and original Princess author")
    if action["data"].get("prince_mark"):
        from girlframe.services.m3_prince import prove_mark

        prove_mark(game, c, load_state(c, game.store.campaign_id), action)
    total = action["data"]["receipt"]["pre_total"] + sum(
        x["amount"] for x in action["data"]["modifiers"]
    )
    from girlframe.engine.m3_gender_designation import man_floor

    minimum = man_floor(action)
    if minimum is not None:
        total = max(total, minimum)
    if action["data"].get("casualty_override"):
        from girlframe.services.m3_casualty import prove_override

        adjustment = prove_override(game, c, load_state(c, game.store.campaign_id), action)
        if adjustment is not None:
            total = max(total, adjustment)
    if action["data"].get("prince_override"):
        from girlframe.services.m3_prince import prove_override as prove_prince_override

        adjustment = prove_prince_override(game, c, load_state(c, game.store.campaign_id), action)
        if adjustment is not None:
            total = max(total, adjustment)
    if action["data"].get("consume_disobey_limit"):
        from girlframe.services.m3_consume import prove_disobey_limit

        cap = prove_disobey_limit(game, c, load_state(c, game.store.campaign_id), action)
        if cap is not None:
            total = min(total, cap)
    if action["data"].get("ankou_roll_modifiers"):
        from girlframe.services.m3_ankou import prove_roll_modifiers

        actual_modifiers = prove_roll_modifiers(
            game, c, load_state(c, game.store.campaign_id), action
        )
        source_ids = {x["source"] for x in actual_modifiers}
        recorded_modifiers = [
            x
            for x in action["data"]["receipt"].get("pre_modifiers", ())
            if x["source"] in source_ids
        ]
        if actual_modifiers != action["data"]["ankou_roll_modifiers"] or [
            (x["source"], x["amount"]) for x in actual_modifiers
        ] != [(x["source"], x["amount"]) for x in recorded_modifiers]:
            raise WorkflowError("Recover the actual consumed Fight/Fawn sources and receipt")
    if action["data"].get("changeling_flirt"):
        from girlframe.services.m3_changeling import prove_flirt_modifier

        actual = prove_flirt_modifier(game, c, load_state(c, game.store.campaign_id), action)
        recorded = sum(
            x["amount"]
            for x in action["data"]["receipt"].get("pre_modifiers", ())
            if x["source"] == "changeling_fingers_flirt"
        )
        if actual != recorded:
            raise WorkflowError("Recover the actual consumed psychic Flirt grant")
    if action["data"].get("red_queen_modifier"):
        from girlframe.services.m3_red_queen import prove_personality_modifier

        if (
            prove_personality_modifier(game, c, load_state(c, game.store.campaign_id), action)
            != action["data"]["red_queen_modifier"]
        ):
            raise WorkflowError("Recover the actual consumed personality modifier")
    if action["data"].get("red_queen_doll"):
        from girlframe.services.m3_red_queen import prove_doll_limit

        limit = prove_doll_limit(game, c, load_state(c, game.store.campaign_id), action)
        if limit is None:
            raise WorkflowError("Recover the actual consumed Doll source")
        total = min(total, limit)
    if total != action["data"]["result"]["total"]:
        raise WorkflowError("Recover the actual source roll and applied Tag modifiers")
    return str(event), int(total)


def _source(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> rules.Session:
    value = rules.get(state, rules.Session, action["id"])
    born = rules.get(_history(c, game, value.event), rules.Session, value.id)
    meta = action["data"].get("npc_flirt", {})
    author = _actor_author(game, c, state, action, value)
    _event(game, c, value.event, ("m2.play_confirmed", "m3.play_confirmed"), author)
    if (
        any(
            getattr(value, k) != getattr(born, k)
            for k in (
                "id",
                "actor",
                "target",
                "controller",
                "actor_label",
                "target_label",
                "cast",
                "registry",
                "target_json",
                "target_sha256",
                "target_position",
                "event",
                "princess_direction",
            )
        )
        or born.effect_event is not None
        or born.completed_event is not None
        or meta.get("princess_direction") != value.princess_direction
        or meta.get("id") != value.id
        or meta.get("actor") != value.actor.model_dump(mode="json")
        or meta.get("target") != value.target.model_dump(mode="json")
        or meta.get("target_controller") != value.controller
        or meta.get("registry") != value.registry
        or meta.get("cast_sha256") != fingerprint(value.cast)
        or meta.get("target_json") != value.target_json
        or meta.get("target_sha256") != value.target_sha256
        or meta.get("target_position") != value.target_position
        or action["actor_id"] != value.actor.entity
        or action["data"].get("play") != "flirt"
        or action["scene_id"] != value.cast.id
        or str(action["channel_id"]) != str(value.cast.channel)
        or action["data"].get("character_ids", {}).get(value.actor.entity)
        != value.actor.incarnation
        or action["data"]["prepared"].get("target") is not None
        or action["data"]["prepared"].get("target_actor") != value.target.model_dump(mode="json")
    ):
        raise WorkflowError(
            "Preserve the actual native Girl/NPC source; controller is never the NPC person"
        )
    original = _npc(_history(c, game, value.event), value.target)
    if (
        fingerprint(original) != value.target_sha256
        or original.id != value.target.entity
        or original.controller != value.controller
        or not original.alive
        or original.source_kind
        or "director" in original.jobs
    ):
        raise WorkflowError("Preserve the actual original ordinary NPC and controller")
    if value.effect_event:
        _, total = _flirt_roll_source(game, c, state, action, value)
        effect = rules.get(_history(c, game, value.effect_event), rules.Session, value.id)
        level = "high" if total >= 11 else "mid" if total >= 8 else "low"
        if effect.effect_event != value.effect_event or value.tier != level:
            raise WorkflowError("NPC Flirt effects require the exact genuine original result")
    return value


def prove(game: GameService, c: Connection, state: GameState, action_id: str) -> rules.Session:
    action = game.action(c, action_id)
    value = _source(game, c, state, action)
    _selected_source(game, c, state, value)
    if value.cancelled_event:
        cancelled = rules.get(_history(c, game, value.cancelled_event), rules.Session, value.id)
        audit = _event(
            game,
            c,
            value.cancelled_event,
            ("m3.shared_play_recovered",),
            _actor_author(game, c, state, action, value),
        )
        payload = json.loads(audit["payload_json"])
        if (
            cancelled != value
            or value.phase != "cancelled"
            or value.effect_event
            or value.completed_event
            or action["data"].get("receipt")
            or payload.get("action_id") != value.id
            or payload.get("cancelled_unrolled") is not True
        ):
            raise WorkflowError(
                "Preserve the actual unrolled source cancellation and original work"
            )
    if value.completed_event:
        final = rules.get(_history(c, game, value.completed_event), rules.Session, value.id)
        if (
            final.completed_event != value.completed_event
            or action["state"] != "complete"
            or game.pending(c, value.id)
            or not action["data"].get("receipt")
        ):
            raise WorkflowError("The real Flirt completes only after actual effects/work")
        _prove_completion(game, c, state, action, value)
    return value


def _current(game: GameService, c: Connection, state: GameState, value: rules.Session) -> Npc:
    npc = _npc(state, value.target)
    if (
        not npc.alive
        or npc.controller != value.controller
        or current_ref(state, int(value.actor.entity)) != value.actor
    ):
        raise WorkflowError("Recover the original living participants and actual NPC controller")
    return npc


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer)
    _source(game, c, load_state(c, game.store.campaign_id), action)
    if viewer.user_id not in action["data"]["npc_flirt"]["table"]:
        raise WorkflowError("Only the actual source table may access this saved Play")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = _source(game, c, state, action)
    npc = _current(game, c, state, value)
    if (
        viewer.user_id != _actor_author(game, c, state, action, value)
        or value.effect_event
        or value.completed_event
        or value.cancelled_event
        or fingerprint(npc) != action["data"]["npc_flirt"]["target_sha256"]
        or _cast(game, c, state, value.cast.channel) != value.cast
    ):
        raise WorkflowError("STALE_NPC_FLIRT: preserve actual source/roles/body before dice")
    target = resolve(state, value.target, profiles(c, game.store.campaign_id))
    if target.position_sha256 != action["data"]["npc_flirt"]["target_position"]:
        raise WorkflowError("STALE_NPC_FLIRT: the actual target position changed")


def _request(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    value: rules.Session,
    kind: str,
    npc: bool = False,
) -> str:
    return game.request(
        c,
        action,
        value.controller if npc else int(value.actor.entity),
        kind,
        dict(subject=(value.target if npc else value.actor).model_dump(mode="json")),
    )


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = _source(game, c, state, action)
    if value.effect_event:
        raise WorkflowError("Resume the real NPC Flirt result; never repeat its Bond effect")
    event, level = action["data"]["response_event"], action["data"]["result"]["tier"]
    if level == "low":
        if depth(state, value.actor, value.target):
            _copy(state, change(state, value.actor, value.target, -1, event))
        _request(game, c, action, value, "npc_flirt_target", True)
    else:
        _request(game, c, action, value, "npc_flirt_actor")
    rules.put(
        state,
        value.model_copy(
            update=dict(
                effect_event=event, tier=level, phase="target" if level == "low" else "actor"
            )
        ),
    )


def _jobs(game: GameService, state: GameState, target: ActorRef) -> list[dict[str, str]]:
    registry = Access(game.store).registry
    assert registry is not None
    result = []
    for job in _npc(state, target).jobs:
        if job not in NARRATIVE:
            continue
        try:
            registry.require_available("npc.npc." + job.replace("_", "-"))
        except ValueError:
            continue
        result.append(dict(id=job, move=NARRATIVE[job][0]))
    return result


def _strict(
    answer: ChoiceAnswer,
    *,
    options: tuple[str, ...] = (),
    fields: set[str] | None = None,
    text: bool = False,
    denied: bool = False,
    flag: bool = False,
) -> None:
    if (
        answer.options != options
        or set(answer.fields) - (fields or set())
        or answer.denied
        and not denied
        or answer.flag is not None
        and not flag
        or answer.number is not None
        or answer.member is not None
        or (not answer.text.strip() if text else bool(answer.text))
    ):
        raise WorkflowError("Use only this actual owned NPC Flirt response")


def _work_done(game: GameService, c: Connection, value: rules.Damage) -> bool:
    table = t.m3["m3_required_work"]
    for identity in value.work:
        row = c.execute(
            sa.select(table.c.state)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        ).first()
        if row is None or row.state != "resolved":
            return False
    return bool(value.work)


def intercept_finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("npc_flirt"):
        return False
    value = _source(game, c, state, action)
    if game.pending(c, value.id):
        return True
    if value.damage and not _work_done(game, c, rules.get(state, rules.Damage, value.damage)):
        return True
    grant_id = action["data"].get("handler_play_m3")
    if grant_id and not any(
        x.id == grant_id and x.state == "complete" for x in state.handler_plays
    ):
        return True
    if value.phase != "complete":
        rules.put(
            state,
            value.model_copy(
                update=dict(phase="complete", completed_event=action["data"]["response_event"])
            ),
        )
    return False


def _finish(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    if not intercept_finish(game, c, state, action):
        ChoiceEngine(game).finish(c, state, action)
        game.save_action(c, action)


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    if row["kind"] not in rules.KINDS or not action["data"].get("npc_flirt"):
        return False
    value = _source(game, c, state, action)
    _current(game, c, state, value)
    kind, event = row["kind"], action["data"]["response_event"]
    npc_choice = kind in ("npc_flirt_target", "npc_flirt_escape", "npc_flirt_play", "npc_flirt_owe")
    expected = value.controller if npc_choice else int(value.actor.entity)
    if row["actor_id"] != str(expected) or json.loads(row["body_json"]).get("subject") != (
        value.target if npc_choice else value.actor
    ).model_dump(mode="json"):
        raise WorkflowError("Use the actual bound NPC/Girl role, not its controller's other person")
    result = action["data"]["result"]
    if kind == "npc_flirt_actor":
        from girlframe.services.m3_kicked_puppy import questions as available_questions

        if len(answer.options) != 1 or answer.options[0] not in available_questions(
            game, c, state, action
        ):
            raise WorkflowError("Ask one genuine printed Flirt question")
        _strict(
            answer, options=answer.options, denied=True, fields={"extra"}, text=value.tier == "high"
        )
        if (
            value.tier == "high"
            and answer.fields.get("extra") not in ("escape", "handler", "owe")
            or value.tier != "high"
            and answer.fields
        ):
            raise WorkflowError("Only the actual high result adds one printed consequence")
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).unmark(c, state, state.sheets[value.actor.entity], answer.denied, 2)
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    question=answer.options[0],
                    question_event=event,
                    extra=answer.fields.get("extra"),
                    phase="target",
                )
            ),
        )
        result.update(
            question=answer.options[0], too_far=answer.text, extra=answer.fields.get("extra")
        )
        _request(game, c, action, value, "npc_flirt_target", True)
    elif kind == "npc_flirt_target":
        if value.tier == "low":
            if len(answer.options) > 1 or set(answer.options) - set(FLIRT_QUESTIONS):
                raise WorkflowError("The actual NPC may ask one printed return question")
            _strict(answer, options=answer.options, text=True)
            result["target_answer"] = answer.text
            if answer.options:
                result["return_question"] = answer.options[0]
                _request(game, c, action, value, "npc_flirt_answer")
            else:
                _finish(game, c, state, action)
        else:
            _strict(answer, text=True, flag=True)
            from girlframe.services.m3_ankou_bonds import intense_benefit

            if (
                value.question == "intimacy"
                and intense_benefit(game, c, state, value.target, value.actor)
                and answer.flag is not True
            ):
                raise WorkflowError(
                    "Actual intimacy/safety confirmation is never inferred from a Bond"
                )
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        wanted=answer.text, wanted_event=event, phase=value.extra or "answer"
                    )
                ),
            )
            result["target_answer"] = answer.text
            if value.extra == "escape":
                _request(game, c, action, value, "npc_flirt_escape", True)
            elif value.extra == "owe":
                _request(game, c, action, value, "npc_flirt_owe", True)
            elif value.extra == "handler":
                from girlframe.services.m3_handler_plays import request_from_play

                required = game.request(c, action, action["data"]["handler"], "handler_brief")
                updated, grant = request_from_play(
                    game,
                    c,
                    state,
                    action,
                    required,
                    "flirt.high.handler",
                    event,
                    targets=(value.actor, value.target),
                )
                _copy(state, updated)
                action["data"]["handler_play_m3"] = grant
            else:
                _finish(game, c, state, action)
    elif kind == "npc_flirt_answer":
        _strict(answer, text=True)
        result["actor_answer"] = answer.text
        _finish(game, c, state, action)
    elif kind == "npc_flirt_owe":
        _strict(answer, text=True)
        tag = rules.identity("tag", event)
        _copy(
            state,
            give_tag(
                state,
                profiles(c, game.store.campaign_id),
                value.actor,
                value.target,
                answer.text,
                tag,
                event,
                tuple(action["data"]["participants"]),
            ),
        )
        debt = game.obligation(
            state,
            action,
            "npc_flirt_cannot_refuse",
            int(value.actor.entity),
            value.controller,
            actor=value.actor.model_dump_json(),
            npc=value.target.model_dump_json(),
            tag=tag,
            grant=tag,
        )
        rules.put(
            state,
            rules.TagGrant(
                id=tag,
                action=value.id,
                actor=value.actor,
                npc=value.target,
                controller=value.controller,
                label=answer.text,
                event=event,
                choice=row["id"],
                obligation=debt,
            ),
        )
        result["npc_tag"] = tag
        _finish(game, c, state, action)
    elif kind == "npc_flirt_escape":
        _strict(answer, options=answer.options)
        if answer.options == ("helpless",):
            _copy(state, make_helpless(state, value.target, value.actor, event))
            result["helpless_actor"] = value.target.model_dump(mode="json")
            _finish(game, c, state, action)
        elif answer.options == ("play",):
            if not _jobs(game, state, value.target):
                raise WorkflowError(
                    "SOURCE_NPC_PLAY_REQUIRED: select an actual supported job performance"
                )
            _request(game, c, action, value, "npc_flirt_play", True)
        elif answer.options == ("damage",):
            damage = rules.Damage(
                id=rules.identity("damage", event),
                action=value.id,
                npc=value.target,
                controller=value.controller,
                choice=row["id"],
                event=event,
            )
            rules.put(state, damage)
            rules.put(state, value.model_copy(update=dict(damage=damage.id, phase="damage")))
            from girlframe.services.m3_battle import npc_flirt_escape

            changed, work = npc_flirt_escape(game, c, state, action, row["id"], event)
            _copy(state, changed)
            rules.put(state, damage.model_copy(update=dict(work=tuple(work))))
            if not work:
                raise WorkflowError(
                    "The actual NPC Asset replacement must produce its real consequence"
                )
        else:
            raise WorkflowError("Accept real Helplessness, or escape through real damage/Play")
    elif kind == "npc_flirt_play":
        if len(answer.options) != 1:
            raise WorkflowError("Choose one actual NPC job")
        _strict(answer, options=answer.options, fields={"move"}, text=True)
        job = answer.options[0]
        if (
            job not in {x["id"] for x in _jobs(game, state, value.target)}
            or job not in NARRATIVE
            or answer.fields.get("move") != NARRATIVE[job][0]
        ):
            raise WorkflowError(
                "Perform the actual supported job move, not narrative mechanical damage/healing"
            )
        if _cast(game, c, state, value.cast.channel) != value.cast:
            raise WorkflowError("Reconcile the actual changed scene before this performed escape")
        recipient = next(x for x in value.cast.roles if x.actor == value.actor)
        performance = rules.Performance(
            id=rules.identity("performance", event),
            action=value.id,
            kind="escape",
            actor=value.target,
            controller=value.controller,
            cast=value.cast,
            recipients=(recipient,),
            rendition=answer.text,
            event=event,
            job=job,
            move=NARRATIVE[job][0],
            choice=row["id"],
        )
        rules.put(state, performance)
        result.update(escaped=True, escape_performance=performance.id)
        _finish(game, c, state, action)
    return True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    value = _source(game, c, state, action)
    own = state.sheets[value.actor.entity]
    from girlframe.engine.m3_clone_am import additional_identities
    from girlframe.services.m3_clone_am import prove_additional
    from girlframe.services.m3_kicked_puppy import questions as available_questions

    extra = additional_identities(state, own.owner)
    if extra and row["kind"] == "npc_flirt_actor":
        prove_additional(game, c, state, own.owner)
    return dict(
        actor=value.actor.model_dump(mode="json"),
        actor_label=value.actor_label,
        actor_author=_actor_author(game, c, state, action, value),
        directed=value.princess_direction is not None,
        target=value.target.model_dump(mode="json"),
        target_controller=value.controller,
        question=action["data"]["result"].get("question"),
        tier=value.tier,
        identities=[x.model_dump(mode="json") for x in (*own.identities, *extra) if x.marked]
        if row["kind"] == "npc_flirt_actor"
        else [],
        questions=list(available_questions(game, c, state, action)),
        jobs=_jobs(game, state, value.target),
    )


def _answer_source(
    game: GameService, c: Connection, action: dict[str, Any], event: str, kind: str, author: int
) -> tuple[dict[str, Any], ChoiceAnswer]:
    audit = _event(game, c, event, ("m2.choice_resolved", "m3.choice_resolved"))
    payload = json.loads(audit["payload_json"])
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == payload.get("choice_id"),
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == payload.get("choice_id"),
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or response is None
        or row["kind"] != kind
        or row["action_id"] != action["id"]
        or row["actor_id"] != str(author)
        or row["state"] != "answered"
        or payload.get("action_id") != action["id"]
        or response["event_id"] != event
    ):
        raise WorkflowError("Recover the exact original source choice and its true owned answer")
    # The row belongs to the actual person; a source-proved Princess may author only
    # that person's actor decisions. NPC-controller replies never become Girl decisions.
    from girlframe.services.m3_princess_sex import prove_response_author

    subject = json.loads(row["body_json"]).get("subject")
    expected_subject = action["data"]["npc_flirt"][
        "actor" if kind in ("npc_flirt_actor", "npc_flirt_answer") else "target"
    ]
    if subject != expected_subject:
        raise WorkflowError("Preserve the original Girl or NPC subject, not a controller alias")
    human = (
        prove_response_author(game, c, _history(c, game, event), action, dict(row), event)
        if kind in ("npc_flirt_actor", "npc_flirt_answer")
        else None
    )
    expected = author if human is None else human
    if audit["actor_id"] != str(expected) or response["actor_id"] != str(expected):
        raise WorkflowError("Preserve the source-proved human author and actual row owner")
    return dict(row), ChoiceAnswer.model_validate_json(response["answer_json"])


def _selected_source(
    game: GameService, c: Connection, state: GameState, value: rules.Session
) -> None:
    action = game.action(c, value.id)
    if value.question is not None:
        if value.question_event is None:
            raise WorkflowError("The selected actual Flirt question needs its canonical source")
        selected = rules.get(_history(c, game, value.question_event), rules.Session, value.id)
        _, answer = _answer_source(
            game, c, action, value.question_event, "npc_flirt_actor", int(value.actor.entity)
        )
        if (
            (selected.question, selected.extra) != (value.question, value.extra)
            or answer.options != (value.question,)
            or answer.fields.get("extra") != value.extra
        ):
            raise WorkflowError("Preserve the actual Girl's selected question and high consequence")
    if value.wanted_event:
        wanted = rules.get(_history(c, game, value.wanted_event), rules.Session, value.id)
        _, answer = _answer_source(
            game, c, action, value.wanted_event, "npc_flirt_target", value.controller
        )
        if wanted.wanted != value.wanted or answer.text != value.wanted or value.tier == "low":
            raise WorkflowError(
                "Preserve the original NPC's actual answer and specific wanted outcome"
            )
    elif value.wanted is not None:
        raise WorkflowError("The actual wanted outcome needs its original NPC reply")


def validate_pending_escape_damage(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    choice_id: str,
    event: str,
) -> dict[str, Any]:
    value = _source(game, c, state, action)
    _selected_source(game, c, state, value)
    damage = rules.get(state, rules.Damage, value.damage or "")
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == choice_id,
            )
        )
        .mappings()
        .first()
    )
    if (
        value.tier != "high"
        or value.extra != "escape"
        or not value.wanted_event
        or damage.action != value.id
        or damage.choice != choice_id
        or damage.event != event
        or damage.npc != value.target
        or damage.controller != value.controller
        or action["data"]["response_event"] != event
        or action["data"]["choices"]
        .get("npc_flirt_escape:" + str(value.controller), {})
        .get("options")
        != ["damage"]
        or row is None
        or row["kind"] != "npc_flirt_escape"
        or row["state"] != "answered"
        or row["action_id"] != value.id
        or row["actor_id"] != str(value.controller)
    ):
        raise WorkflowError("Only the genuine current NPC escape self-cost grants NPC damage")
    return dict(
        id=damage.id,
        action=value.id,
        target=value.target.model_dump(mode="json"),
        actor=value.target.model_dump(mode="json"),
        chooser=value.controller,
        cast=value.cast.model_dump(mode="json"),
        source_event=event,
        source_choice=choice_id,
        physical_blow=False,
    )


def prove_escape_damage(
    game: GameService, c: Connection, state: GameState, action_id: str, event: str
) -> rules.Damage:
    action = game.action(c, action_id)
    value = _source(game, c, state, action)
    _selected_source(game, c, state, value)
    damage = next(
        (
            x
            for x in rules.records(state, rules.Damage)
            if x.action == action_id and x.event == event
        ),
        None,
    )
    if damage is None or rules.get(_history(c, game, event), rules.Damage, damage.id) != damage:
        raise WorkflowError("Recover this actual NPC escape damage source")
    row, answer = _answer_source(game, c, action, event, "npc_flirt_escape", value.controller)
    if (
        damage.npc != value.target
        or damage.controller != value.controller
        or damage.choice != row["id"]
        or answer.options != ("damage",)
        or value.tier != "high"
        or value.extra != "escape"
        or not damage.work
    ):
        raise WorkflowError("Preserve the genuine NPC self-cost and its real consequence work")
    return damage


def prove_escape_performance(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Performance:
    value = rules.get(state, rules.Performance, identity)
    source = _source(game, c, state, game.action(c, value.action))
    _selected_source(game, c, state, source)
    born = _history(c, game, value.event)
    if (
        rules.get(born, rules.Performance, identity) != value
        or value.kind != "escape"
        or source.extra != "escape"
        or source.tier != "high"
    ):
        raise WorkflowError("Use only the real source-owned NPC Conversation opportunity")
    row, answer = _answer_source(
        game, c, game.action(c, value.action), value.event, "npc_flirt_play", source.controller
    )
    original_npc = _npc(born, source.target)
    if (
        value.actor != source.target
        or value.controller != source.controller
        or value.cast != source.cast
        or value.choice != row["id"]
        or value.job not in original_npc.jobs
        or value.job not in NARRATIVE
        or value.move != NARRATIVE[value.job][0]
        or answer.options != (value.job,)
        or answer.fields != {"move": value.move}
        or answer.text != value.rendition
        or value.recipients != tuple(x for x in value.cast.roles if x.actor == source.actor)
    ):
        raise WorkflowError(
            "Prove the actual original NPC job move, rendition and addressed recipient"
        )
    return value


def prove_tag(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, tag_id: str
) -> rules.TagGrant:
    value = rules.get(state, rules.TagGrant, tag_id)
    source = _source(game, c, state, game.action(c, value.action))
    _selected_source(game, c, state, source)
    born = _history(c, game, value.event)
    row, answer = _answer_source(
        game, c, game.action(c, value.action), value.event, "npc_flirt_owe", source.controller
    )
    tag = next((x for x in born.sheets[source.actor.entity].tags if x.id == tag_id), None)
    debt = next((x for x in born.obligations if x.id == value.obligation), None)
    if (
        rules.get(born, rules.TagGrant, value.id) != value
        or source.extra != "owe"
        or source.tier != "high"
        or value.actor != actor
        or value.actor != source.actor
        or value.npc != source.target
        or value.choice != row["id"]
        or value.label != answer.text
        or tag is None
        or tag.giver_actor != source.target
        or tag.giver != source.controller
        or tag.label != value.label
        or debt is None
        or debt.kind != "npc_flirt_cannot_refuse"
        or debt.owner != int(actor.entity)
        or debt.details.get("npc") != source.target.model_dump_json()
        or debt.details.get("grant") != value.id
    ):
        raise WorkflowError("Recover the actual NPC-given Tag and original refusal obligation")
    return value


def cannot_refuse(
    game: GameService, c: Connection, state: GameState, subject: ActorRef, npc: ActorRef
) -> str | None:
    for grant in rules.records(state, rules.TagGrant):
        if grant.actor != subject or grant.npc != npc:
            continue
        prove_tag(game, c, state, subject, grant.id)
        debt = next((x for x in state.obligations if x.id == grant.obligation), None)
        if debt is None:
            raise WorkflowError("Recover the actual owed NPC Tag obligation")
        if debt.state == "pending":
            sheet = state.sheets.get(subject.entity)
            if (
                sheet is None
                or sheet.character_id != subject.incarnation
                or not any(x.id == grant.id for x in sheet.tags)
            ):
                raise WorkflowError("Resolve the actual missing owed Tag; no silent refusal waiver")
            return grant.id
    return None


def tag_resolved(state: GameState, subject: ActorRef, tag_id: str) -> None:
    for grant in rules.records(state, rules.TagGrant):
        if grant.actor == subject and grant.id == tag_id:
            for debt in state.obligations:
                if (
                    debt.id == grant.obligation
                    and debt.kind == "npc_flirt_cannot_refuse"
                    and debt.details.get("grant") == tag_id
                ):
                    debt.state = "fulfilled"


def complete_damage_work(
    game: GameService, c: Connection, work: dict[str, Any], event: str
) -> bool:
    state = load_state(c, game.store.campaign_id)
    damage = next((x for x in rules.records(state, rules.Damage) if work["id"] in x.work), None)
    if damage is None:
        return False
    prove_escape_damage(game, c, state, damage.action, damage.event)
    if not _work_done(game, c, damage):
        return True
    action = game.action(c, damage.action)
    if action["state"] == "complete":
        return True
    audit = c.execute(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if audit is None or not audit.actor_id.isdecimal():
        raise WorkflowError("Recover the actual NPC consequence completion author")
    final = str(uuid4())
    completion = rules.Completion(
        id=final,
        action=action["id"],
        trigger=event,
        work=damage.work,
        receipt=_receipt_sha(action["data"]["receipt"]),
        event=final,
    )
    rules.put(state, completion)
    action["data"]["response_event"] = final
    _finish(game, c, state, action)
    if action["state"] != "complete":
        raise WorkflowError("Actual NPC consequence work or Flirt choices still remain")
    game.event(
        c,
        int(audit.actor_id),
        final,
        "m3.npc_flirt_completed",
        state,
        event_id=final,
        action_id=action["id"],
        trigger=event,
        work=list(damage.work),
    )
    _complete_court_child(game, c, action["id"], final)
    if action["data"].get("princess_child"):
        from girlframe.services.m3_princess_performer import complete_npc_flirt

        complete_npc_flirt(game, c, game.action(c, action["id"]), final)
    return True


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if not action["data"].get("npc_flirt"):
        return
    from girlframe.services.m3_battle import synchronize_damage

    synchronize_damage(game, c, event)


def _proof_performance(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Performance:
    value = rules.get(state, rules.Performance, identity)
    if value.kind == "escape":
        return prove_escape_performance(game, c, state, identity)
    source = prove(game, c, state, value.action)
    _selected_source(game, c, state, source)
    born = _history(c, game, value.event)
    _event(
        game, c, value.event, ("m3.npc_flirt_followthrough_performed",), int(source.actor.entity)
    )
    if (
        rules.get(born, rules.Performance, identity) != value
        or not source.wanted_event
        or value.actor != source.actor
        or value.controller != int(source.actor.entity)
        or value.recipients
        != tuple(
            x
            for x in value.cast.roles
            if x.actor == source.target and x.controller == source.controller
        )
        or not any(
            x.actor == source.actor and x.controller == value.controller for x in value.cast.roles
        )
    ):
        raise WorkflowError("Prove the actual addressed source performance, not an acknowledgment")
    if value.performed_action:
        performed = game.action(c, value.performed_action)
        if (
            performed["state"] != "complete"
            or game.pending(c, performed["id"])
            or performed["actor_id"] != source.actor.entity
            or performed["data"].get("character_ids", {}).get(source.actor.entity)
            != source.actor.incarnation
        ):
            raise WorkflowError("Use the original Girl's actual completed mechanical source")
        _roll_source(game, c, performed)
    return value


class NpcFlirtService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def targets(self, viewer: GuildViewer, channel: int) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            cast = _cast(self.game, c, state, channel)
            if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles):
                raise WorkflowError("Join your actual original Girl to this source scene")
            result = []
            for role in cast.roles:
                if role.actor.kind != "npc" or not _visible(state, role.actor, viewer.user_id):
                    continue
                candidate = (
                    next((x for x in state.world.npcs if x.id == role.actor.entity), None)
                    if state.world
                    else None
                )
                if candidate is not None and (
                    candidate.source_kind is not None or "director" in candidate.jobs
                ):
                    continue
                value = _npc(state, role.actor)
                if value.alive and value.controller == role.controller:
                    actual = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                    if not actual.offstage_source:
                        result.append(
                            dict(ref=role.actor.model_dump(mode="json"), label=actual.label)
                        )
            return result

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != request["revision"]:
                raise WorkflowError("STALE_NPC_FLIRT: reopen the actual saved source")
            return operation(c, state, str(uuid4()))

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                request,
                run,
                auto_audit=False,
                authorize=lambda c: _access(self.game, c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def perform_escape(
        self,
        viewer: GuildViewer,
        key: str,
        action_id: str,
        revision: int,
        job: str,
        move: str,
        rendition: str,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, action_id)
            if source.controller != viewer.user_id or state.revision != revision:
                raise WorkflowError("Use your actual original NPC's current escape opportunity")
            row = next(
                (x for x in self.game.pending(c, action_id) if x["kind"] == "npc_flirt_play"), None
            )
            if row is None:
                raise WorkflowError("Open the actual source-owned NPC Conversation opportunity")
        return self.game.respond(
            viewer,
            key,
            row["id"],
            row["revision"],
            ChoiceAnswer(options=(job,), fields={"move": move}, text=rendition),
        )

    def record_followthrough(
        self,
        viewer: GuildViewer,
        key: str,
        action_id: str,
        revision: int,
        channel: int,
        account: str,
        *,
        performed_action: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove(self.game, c, state, action_id)
            _selected_source(self.game, c, state, source)
            _current(self.game, c, state, source)
            if (
                viewer.user_id != int(source.actor.entity)
                or not source.completed_event
                or not source.wanted_event
                or not account.strip()
                or len(account) > 1800
                or any(
                    x.action == action_id and x.accepted
                    for x in rules.records(state, rules.Judgment)
                )
            ):
                raise WorkflowError(
                    "Perform the original wanted followthrough once; no automatic Bond reward"
                )
            cast = _cast(self.game, c, state, channel)
            recipient = next(
                (
                    x
                    for x in cast.roles
                    if x.actor == source.target and x.controller == source.controller
                ),
                None,
            )
            if recipient is None or not any(
                x.actor == source.actor and x.controller == viewer.user_id for x in cast.roles
            ):
                raise WorkflowError(
                    "Address the actual original NPC in a real current source scene"
                )
            if performed_action:
                actual = self.game.action(c, performed_action)
                if (
                    actual["state"] != "complete"
                    or self.game.pending(c, actual["id"])
                    or actual["actor_id"] != source.actor.entity
                    or actual["data"].get("character_ids", {}).get(source.actor.entity)
                    != source.actor.incarnation
                ):
                    raise WorkflowError(
                        "Mechanical claims require your genuine completed source Action"
                    )
                _roll_source(self.game, c, actual)
            value = rules.Performance(
                id=rules.identity("performance", event),
                action=action_id,
                kind="followthrough",
                actor=source.actor,
                controller=viewer.user_id,
                cast=cast,
                recipients=(recipient,),
                rendition=account.strip(),
                event=event,
                performed_action=performed_action,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_flirt_followthrough_performed",
                state,
                event_id=event,
                performance=value.id,
                action_id=action_id,
            )
            return dict(id=value.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.npc_flirt_followthrough_performed",
            dict(
                action=action_id,
                revision=revision,
                channel=channel,
                account=account,
                performed_action=performed_action,
            ),
            operation,
        )

    def confirm_followthrough(
        self,
        viewer: GuildViewer,
        key: str,
        performance_id: str,
        revision: int,
        accepted: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            performance = _proof_performance(self.game, c, state, performance_id)
            source = prove(self.game, c, state, performance.action)
            _current(self.game, c, state, source)
            if (
                performance.kind != "followthrough"
                or viewer.user_id != source.controller
                or type(accepted) is not bool
                or not account.strip()
                or len(account) > 1800
                or any(
                    x.performance == performance_id for x in rules.records(state, rules.Judgment)
                )
                or any(
                    x.action == source.id and x.accepted
                    for x in rules.records(state, rules.Judgment)
                )
            ):
                raise WorkflowError(
                    "The actual NPC controller judges this genuine specific fulfillment once"
                )
            before = depth(state, source.actor, source.target)
            if accepted:
                _copy(state, change(state, source.actor, source.target, 1, event))
            value = rules.Judgment(
                id=rules.identity("judgment", event),
                performance=performance_id,
                action=source.id,
                npc=source.target,
                controller=source.controller,
                accepted=accepted,
                account=account.strip(),
                event=event,
                before_depth=before,
                after_depth=depth(state, source.actor, source.target),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_flirt_followthrough_judged",
                state,
                event_id=event,
                judgment=value.id,
                performance=performance_id,
            )
            return dict(id=value.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.npc_flirt_followthrough_judged",
            dict(performance=performance_id, revision=revision, accepted=accepted, account=account),
            operation,
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, identity)
            action = self.game.action(c, identity)
            author = _actor_author(self.game, c, state, action, source)
            participants = (int(source.actor.entity), source.controller)
            if viewer.user_id not in (*participants, author):
                raise WorkflowError(
                    "Only original participants and the proven one-Play author see this source"
                )
            # Direction grants no later authority over the performer's voluntary followthrough.
            performances = [
                x
                for x in rules.records(state, rules.Performance)
                if x.action == identity and (x.kind == "escape" or viewer.user_id in participants)
            ]
            for value in performances:
                _proof_performance(self.game, c, state, value.id)
            judgments = [
                prove_judgment(self.game, c, state, x.id)
                for x in rules.records(state, rules.Judgment)
                if x.action == identity and viewer.user_id in participants
            ]
            can_order, order_blocked = False, None
            if viewer.user_id == source.controller:
                npc = _npc(state, source.target)
                if npc.alive and npc.controller == source.controller:
                    try:
                        can_order = (
                            cannot_refuse(self.game, c, state, source.actor, source.target)
                            is not None
                        )
                    except WorkflowError as error:
                        order_blocked = str(error)
            return dict(
                can_order=can_order,
                order_blocked=order_blocked,
                directed=source.princess_direction is not None,
                actor_author=author,
                id=identity,
                revision=state.revision,
                source=source.model_dump(mode="json", exclude={"target_json", "registry"}),
                performances=[x.model_dump(mode="json") for x in performances],
                judgments=[x.model_dump(mode="json") for x in judgments],
                can_perform=viewer.user_id == int(source.actor.entity)
                and bool(source.completed_event and source.wanted_event)
                and not any(x.accepted for x in judgments),
                can_judge=viewer.user_id == source.controller,
                pending=[
                    x
                    for x in self.game.pending(c, identity)
                    if _row_author(self.game, c, state, action, x) == viewer.user_id
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for source in rules.records(state, rules.Session):
            action = self.game.action(c, source.id)
            author = _actor_author(self.game, c, state, action, source)
            if viewer.user_id not in (int(source.actor.entity), source.controller, author):
                continue
            own_rows = [
                x
                for x in self.game.pending(c, source.id)
                if _row_author(self.game, c, state, action, x) == viewer.user_id
            ]
            awaiting = [
                x
                for x in rules.records(state, rules.Performance)
                if x.action == source.id
                and x.kind == "followthrough"
                and not any(y.performance == x.id for y in rules.records(state, rules.Judgment))
            ]
            pending = bool(own_rows or viewer.user_id == source.controller and awaiting)
            result.append(
                dict(
                    id=source.id,
                    revision=state.revision,
                    label="Actual NPC Flirt and followthrough",
                    phase="complete" if source.completed_event else source.phase,
                    pending=pending,
                    waiting=bool(
                        not source.completed_event and not source.cancelled_event and not pending
                    ),
                )
            )
        return result


def _prove_completion(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    source: rules.Session,
) -> None:
    if source.completed_event is None:
        raise WorkflowError("Preserve the actual source completion")
    completed = next(
        (
            x
            for x in rules.records(state, rules.Completion)
            if x.action == source.id and x.event == source.completed_event
        ),
        None,
    )
    if completed:
        born = _history(c, game, completed.event)
        audit = _event(game, c, completed.event, ("m3.npc_flirt_completed",))
        trigger = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == completed.trigger,
                )
            )
            .mappings()
            .first()
        )
        if (
            rules.get(born, rules.Completion, completed.id) != completed
            or completed.receipt != _receipt_sha(action["data"]["receipt"])
            or trigger is None
            or trigger["actor_id"] != audit["actor_id"]
        ):
            raise WorkflowError(
                "Prove the actual external completion, source receipt and true human author"
            )
        if completed.handler:
            grant = next((x for x in born.handler_plays if x.id == completed.handler), None)
            if (
                grant is None
                or grant.state != "complete"
                or grant.source_action != source.id
                or grant.completed_event != completed.trigger
            ):
                raise WorkflowError(
                    "Complete the actual source Handler Play before closing NPC Flirt"
                )
        else:
            damage = rules.get(state, rules.Damage, source.damage or "")
            prove_escape_damage(game, c, state, damage.action, damage.event)
            if completed.work != damage.work or not _work_done(game, c, damage):
                raise WorkflowError("Complete every real source NPC damage consequence")
            table = t.m3["m3_required_work"]
            if not c.scalar(
                sa.select(table.c.id).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id.in_(damage.work),
                    table.c.state == "resolved",
                    table.c.event_id == completed.trigger,
                )
            ):
                raise WorkflowError(
                    "The completion trigger must be an actual resolved source work event"
                )
    else:
        audit = _event(
            game, c, source.completed_event, ("m2.choice_resolved", "m3.choice_resolved")
        )
        choice = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == json.loads(audit["payload_json"]).get("choice_id"),
                )
            )
            .mappings()
            .first()
        )
        if choice is None or choice["kind"] not in (
            "npc_flirt_target",
            "npc_flirt_answer",
            "npc_flirt_escape",
            "npc_flirt_play",
            "npc_flirt_owe",
        ):
            raise WorkflowError(
                "Prove the actual final NPC Flirt response, not an arbitrary source event"
            )
        owner = (
            int(source.actor.entity) if choice["kind"] == "npc_flirt_answer" else source.controller
        )
        _answer_source(game, c, action, source.completed_event, choice["kind"], owner)
        if choice["kind"] == "npc_flirt_play":
            performance = next(
                (
                    x
                    for x in rules.records(state, rules.Performance)
                    if x.action == source.id and x.event == source.completed_event
                ),
                None,
            )
            if performance is None:
                raise WorkflowError("The escape requires its actual performed NPC Conversation")
            prove_escape_performance(game, c, state, performance.id)


def complete_external(game: GameService, c: Connection, action: dict[str, Any], event: str) -> bool:
    """After actual Handler work is canonical; save this distinct source closure once."""
    if not action["data"].get("npc_flirt"):
        return False
    state = load_state(c, game.store.campaign_id)
    actual = game.action(c, action["id"])
    value = _source(game, c, state, actual)
    if value.completed_event:
        return True
    grant_id = actual["data"].get("handler_play_m3")
    grant = next((x for x in state.handler_plays if x.id == grant_id), None)
    if (
        grant is None
        or grant.state != "complete"
        or grant.source_action != actual["id"]
        or grant.completed_event != event
    ):
        return False
    audit = c.execute(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if audit is None or not audit.actor_id.isdecimal():
        raise WorkflowError("Recover the actual source Handler completion author")
    final = str(uuid4())
    rules.put(
        state,
        rules.Completion(
            id=final,
            action=actual["id"],
            trigger=event,
            work=(),
            receipt=_receipt_sha(actual["data"]["receipt"]),
            event=final,
            handler=grant.id,
        ),
    )
    actual["data"]["response_event"] = final
    _finish(game, c, state, actual)
    if actual["state"] != "complete":
        raise WorkflowError("Genuine source effects still remain after Handler completion")
    game.event(
        c,
        int(audit.actor_id),
        final,
        "m3.npc_flirt_completed",
        state,
        event_id=final,
        action_id=actual["id"],
        trigger=event,
        grant=grant.id,
    )
    _complete_court_child(game, c, actual["id"], final)
    if actual["data"].get("princess_child"):
        from girlframe.services.m3_princess_performer import complete_npc_flirt

        complete_npc_flirt(game, c, game.action(c, actual["id"]), final)
    action.clear()
    action.update(game.action(c, actual["id"]))
    return True


def _prior(game: GameService, c: Connection, event: str) -> GameState:
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < sequence,
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if raw is None:
        raise WorkflowError(
            "Recover the actual canonical state before this source performance judgment"
        )
    return GameState.model_validate_json(raw)


def prove_judgment(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Judgment:
    value = rules.get(state, rules.Judgment, identity)
    born = _history(c, game, value.event)
    prior = _prior(game, c, value.event)
    performance = _proof_performance(game, c, state, value.performance)
    source = prove(game, c, state, value.action)
    _event(game, c, value.event, ("m3.npc_flirt_followthrough_judged",), source.controller)
    if (
        rules.get(born, rules.Judgment, identity) != value
        or performance.action != source.id
        or performance.kind != "followthrough"
        or value.npc != source.target
        or value.controller != source.controller
        or depth(prior, source.actor, source.target) != value.before_depth
        or depth(born, source.actor, source.target) != value.after_depth
    ):
        raise WorkflowError("Preserve the actual NPC's judgment and real original Bond endpoints")
    from girlframe.engine.m3_bond_operations import records as operations

    changes = [
        x
        for x in operations(born)
        if x.event == value.event and {x.first, x.second} == {source.actor, source.target}
    ]
    if value.accepted:
        if (
            len(changes) != 1
            or changes[0].delta != 1
            or (changes[0].before_depth, changes[0].after_depth)
            != (value.before_depth, value.after_depth)
        ):
            raise WorkflowError(
                "Successful followthrough requires its actual canonical deepen operation"
            )
    elif changes or value.before_depth != value.after_depth:
        raise WorkflowError("A declined judgment cannot invent any Bond reward")
    return value


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    if not action["data"].get("npc_flirt"):
        return False
    source = _source(game, c, state, action)
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.action_id).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if (
        source.effect_event
        or source.completed_event
        or source.cancelled_event
        or action["data"].get("receipt")
        or receipt is not None
        or not event
    ):
        raise WorkflowError(
            "Cancel only the actual unrolled NPC Flirt; keep known results and effects"
        )
    rules.put(state, source.model_copy(update=dict(phase="cancelled", cancelled_event=event)))
    return True


def _complete_court_child(game: GameService, c: Connection, action_id: str, event: str) -> None:
    action = game.action(c, action_id)
    if action["data"].get("red_queen_child"):
        from girlframe.services.m3_red_queen_support import complete_child

        complete_child(game, c, load_state(c, game.store.campaign_id), action, event)


def completion_author(
    game: GameService, c: Connection, action: dict[str, Any], trigger: str
) -> int:
    """Prove only this actual typed delayed NPC closure, before any derived parent closure."""
    audit = _event(game, c, trigger, ("m3.npc_flirt_completed",))
    born = _history(c, game, trigger)
    actual = game.action(c, action["id"])
    source = prove(game, c, born, action["id"])
    completion = next(
        (
            x
            for x in rules.records(born, rules.Completion)
            if x.action == action["id"] and x.event == trigger
        ),
        None,
    )
    payload = json.loads(audit["payload_json"])
    if (
        completion is None
        or source.completed_event != trigger
        or payload.get("action_id") != action["id"]
        or actual["data"].get("receipt") != action["data"].get("receipt")
        or not str(audit["actor_id"]).isdecimal()
    ):
        raise WorkflowError("Prove the actual typed NPC completion and unchanged source receipt")
    return int(audit["actor_id"])
