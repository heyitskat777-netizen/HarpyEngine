"""Source-owned ordinary Flirt between an actual Harpy/Core and an actual Girl.

The controller is a response owner, never a replacement resource or Bond endpoint.
Other NPC/Gorgon/Harpy counterpart ports remain explicit separate contexts.
"""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import FLIRT_QUESTIONS, ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, depth, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_flirt import copy_state, unmark
from girlframe.services.m3_actors import profiles

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def unmark_owned(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    selected: tuple[str, ...],
    maximum: int,
) -> None:
    if len(selected) != len(set(selected)):
        raise ValueError("Choose distinct actual marked Identities")
    if actor.kind != "pilot":
        unmark(state, actor, selected, maximum)
        return
    from girlframe.services.m2_choices import ChoiceEngine

    sheet = state.sheets[actor.entity]
    if sheet.character_id != actor.incarnation:
        raise ValueError("Use the actual original Girl's Identities")
    ChoiceEngine(game).unmark(c, state, sheet, selected, maximum)
    if selected:
        sheet.revision += 1


def refs(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"].get("harpy_flirt") or action["data"]["harpy_followthrough"]
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])


def conversation(state: GameState, first: ActorRef, second: ActorRef) -> None:
    from girlframe.engine.m3_janus import can_speak
    from girlframe.engine.m3_janus_link import has_mental_channel

    mental = has_mental_channel(state, first, second)
    can_speak(state, first, mental_link=mental)
    can_speak(state, second, mental_link=mental)


def prepare(
    game: "GameService",
    c: Connection,
    state: GameState,
    cast: SceneCast,
    ref: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    bound = profiles(c, game.store.campaign_id)
    actor = resolve(state, ref, bound)
    target = resolve(state, prepared.target_actor, bound) if prepared.target_actor else None
    if target is None or not (
        ref.kind == "pilot"
        and target.ref.kind == "external_pilot"
        and target.girl == "harpy"
        or ref.kind == "external_pilot"
        and actor.girl == "harpy"
        and target.ref.kind == "pilot"
    ):
        raise ValueError("SOURCE_PORT_REQUIRED: choose the actual Harpy/Core and original Girl")
    if not all(any(x.actor == v.ref for x in cast.roles) for v in (actor, target)):
        raise ValueError("Join both actual people to the original Flirt scene")
    if (
        actor.cell is None
        or actor.cell != target.cell
        or actor.offstage_source
        or target.offstage_source
    ):
        raise ValueError("Establish actual interaction with this original Harpy or Core")
    if prepared.play != "flirt" or prepared.target is not None or prepared.source_work:
        raise ValueError("Use ordinary actual-source Flirt without an unrelated work item")
    conversation(state, ref, target.ref)
    return dict(
        actor=ref.model_dump(mode="json"),
        target=target.ref.model_dump(mode="json"),
        actor_controller=actor.controller,
        target_controller=target.controller,
        cast=cast.model_dump(mode="json"),
    )


def validate(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any]:
    meta: dict[str, Any] = (
        action["data"].get("harpy_flirt") or action["data"]["harpy_followthrough"]
    )
    bound = profiles(c, game.store.campaign_id)
    actor, target = refs(action)
    conversation(state, actor, target)
    for ref, controller in ((actor, meta["actor_controller"]), (target, meta["target_controller"])):
        if resolve(state, ref, bound, require_current_profile=False).controller != controller:
            raise ValueError("STALE_ACTOR: recover the actual original Flirt response owners")
    return meta


def finish(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    if action["data"].get("actor_basic"):
        from girlframe.services.m3_actor_plays import ActorPlayService

        ActorPlayService(game).finish(c, state, action)
    else:
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).finish(c, state, action)


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    actor, target = refs(action)
    meta = validate(game, c, state, action)
    if action["data"]["result"]["tier"] == "low":
        if depth(state, actor, target):
            copy_state(state, change(state, actor, target, -1, action["data"]["response_event"]))
        game.request(c, action, meta["target_controller"], "harpy_flirt_target")
    else:
        game.request(c, action, meta["actor_controller"], "harpy_flirt_actor")


def _after_questions(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    actor, target = refs(action)
    meta = validate(game, c, state, action)
    result, event = action["data"]["result"], action["data"]["response_event"]
    if result.get("tier") == "low":
        finish(game, c, state, action)
        return
    # Each participant's independently owned question can produce its own
    # follow-through. The original source action and endpoints remain immutable.
    requests = [
        (
            actor,
            target,
            meta["actor_controller"],
            meta["target_controller"],
            result["target_answer"],
        )
    ]
    if result.get("return_question"):
        requests.append(
            (
                target,
                actor,
                meta["target_controller"],
                meta["actor_controller"],
                result["actor_answer"],
            )
        )
    for performer, recipient, owner, target_owner, wanted in requests:
        game.obligation(
            state,
            action,
            "harpy_flirt_followthrough",
            owner,
            target_owner,
            actor=performer.model_dump_json(),
            target_actor=recipient.model_dump_json(),
            wanted=wanted,
        )
    extra = result.get("extra")
    if extra == "handler":
        from girlframe.services.m3_handler_plays import request_from_play

        required = game.request(c, action, state.handler, "handler_brief")
        changed, grant = request_from_play(
            game, c, state, action, required, "flirt.high.handler", event, targets=(actor, target)
        )
        copy_state(state, changed)
        action["data"]["handler_play_m3"] = grant
    elif extra in ("escape", "owe"):
        game.request(c, action, meta["target_controller"], "harpy_flirt_" + extra)
    else:
        finish(game, c, state, action)


def respond(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    actor, target = refs(action)
    meta = validate(game, c, state, action)
    result = action["data"]["result"]
    level, kind, event = result.get("tier"), row["kind"], action["data"]["response_event"]
    if kind == "harpy_flirt_followthrough_confirm":
        if answer.flag is None or not answer.text.strip():
            raise ValueError(
                "The actual recipient must confirm or decline the described follow-through"
            )
        item = next(
            x
            for x in state.obligations
            if x.id == action["data"]["harpy_followthrough"]["obligation"]
        )
        if item.state != "pending":
            raise ValueError("This original follow-through already resolved")
        if answer.flag:
            copy_state(state, change(state, actor, target, 1, event))
            next(x for x in state.obligations if x.id == item.id).state = "fulfilled"
        result.update(confirmed=answer.flag, response=answer.text)
        finish(game, c, state, action)
    elif kind == "harpy_flirt_actor":
        if len(answer.options) != 1 or answer.options[0] not in FLIRT_QUESTIONS:
            raise ValueError("Ask one actual printed Flirt question")
        unmark_owned(game, c, state, actor, answer.denied, 2)
        result["question"] = answer.options[0]
        if level == "high":
            if (
                set(answer.fields) != {"extra"}
                or answer.fields["extra"] not in ("escape", "handler", "owe")
                or not answer.text.strip()
            ):
                raise ValueError("Describe going too far and choose one printed consequence")
            result.update(extra=answer.fields["extra"], too_far=answer.text)
        elif answer.fields:
            raise ValueError("This result has no extra high-tier consequence")
        game.request(c, action, meta["target_controller"], "harpy_flirt_target")
    elif kind == "harpy_flirt_target":
        from girlframe.services.m3_ankou_bonds import intense_benefit

        if not answer.text.strip():
            raise ValueError("The actual target must answer for herself")
        unmark_owned(game, c, state, target, answer.denied, 1 if level == "low" else 2)
        if len(answer.options) > 1 or set(answer.options) - set(FLIRT_QUESTIONS):
            raise ValueError("Optionally ask one printed return question")
        if (
            level != "low"
            and result["question"] == "intimacy"
            and intense_benefit(game, c, state, target, actor)
            and answer.flag is not True
        ):
            raise ValueError("Record the actual human's safety consent; it is never inferred")
        result["target_answer"] = answer.text
        if answer.options:
            result["return_question"] = answer.options[0]
            game.request(c, action, meta["actor_controller"], "harpy_flirt_answer")
        else:
            _after_questions(game, c, state, action)
    elif kind == "harpy_flirt_answer":
        from girlframe.services.m3_ankou_bonds import intense_benefit

        if not answer.text.strip():
            raise ValueError("Answer the actual returned question")
        if (
            result["return_question"] == "intimacy"
            and intense_benefit(game, c, state, actor, target)
            and answer.flag is not True
        ):
            raise ValueError("Record the actual human's safety consent; it is never inferred")
        result["actor_answer"] = answer.text
        _after_questions(game, c, state, action)
    elif kind == "harpy_flirt_owe":
        from girlframe.engine.m3_mockingbird import give_tag

        tag = str(uuid4())
        copy_state(
            state,
            give_tag(
                state,
                profiles(c, game.store.campaign_id),
                actor,
                target,
                answer.text,
                tag,
                event,
                tuple(action["data"]["participants"]),
            ),
        )
        game.obligation(
            state,
            action,
            "harpy_cannot_refuse_until_tag_resolved",
            meta["actor_controller"],
            meta["target_controller"],
            actor=actor.model_dump_json(),
            target_actor=target.model_dump_json(),
            tag=tag,
        )
        finish(game, c, state, action)
    elif kind == "harpy_flirt_escape":
        if answer.options == ("helpless",):
            copy_state(state, make_helpless(state, target, actor, event))
            result["helpless_actor"] = target.model_dump(mode="json")
            finish(game, c, state, action)
        elif answer.options == ("damage",) and len(answer.denied) == 1:
            from girlframe.services.m3_battle import damage_actor

            changed, work = damage_actor(
                game,
                c,
                state,
                target=target,
                asset_id=answer.denied[0],
                event=event,
                source_action=action["id"],
                source_work=None,
                actor=target,
                opponent=actor,
                occurrence="harpy-flirt-escape",
            )
            copy_state(state, changed)
            result["escaped"] = True
            meta["damage_followups"] = list(work)
            if not work:
                finish(game, c, state, action)
        elif answer.options == ("play",):
            game.request(
                c,
                action,
                meta["target_controller"],
                "escape_play",
                dict(actor=target.model_dump(mode="json"), attacker=actor.model_dump(mode="json")),
            )
        else:
            raise ValueError("Accept actual Helplessness or escape by actual Asset damage or Play")
    else:
        raise ValueError("Use this original Harpy/Girl Flirt response")


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    actor, target = refs(action)
    ref = actor if row["kind"] in ("harpy_flirt_actor", "harpy_flirt_answer") else target
    view = resolve(state, ref, profiles(c, game.store.campaign_id), require_current_profile=False)
    identities = [x.model_dump(mode="json") for x in view.identities]
    if ref.kind == "pilot":
        from girlframe.engine.m3_oldgen import marked_maxims

        sheet = state.sheets[ref.entity]
        identities = [x for x in identities if x["id"] not in sheet.sedation_locked]
        identities.extend(
            dict(id=k, label=v, marked=True) for k, v in marked_maxims(state, sheet.owner)
        )
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        identities=identities,
        assets=[x.model_dump(mode="json") for x in view.assets],
        maximum=1 if action["data"]["result"].get("tier") == "low" else 2,
    )


def prepare_followthrough(
    game: "GameService",
    c: Connection,
    state: GameState,
    cast: SceneCast,
    ref: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    actual = resolve(state, ref, profiles(c, game.store.campaign_id))
    item = next(
        (
            x
            for x in state.obligations
            if x.id == prepared.source_work
            and x.kind == "harpy_flirt_followthrough"
            and x.state == "pending"
            and x.owner == actual.controller
            and ActorRef.model_validate_json(x.details["actor"]) == ref
        ),
        None,
    )
    if item is None or prepared.heat or prepared.identity or prepared.gain or prepared.pair_share:
        raise ValueError("Choose your actual owed follow-through without dice or resources")
    actor = ActorRef.model_validate_json(item.details["actor"])
    target = ActorRef.model_validate_json(item.details["target_actor"])
    original = game.action(c, item.action)
    if (
        original["state"] != "complete"
        or not original["data"].get("harpy_flirt")
        or set(refs(original)) != {actor, target}
    ):
        raise ValueError("Recover this original completed Flirt and its owed endpoints")
    recipient = resolve(state, target, profiles(c, game.store.campaign_id))
    if (
        not all(any(x.actor == v for x in cast.roles) for v in (actor, target))
        or item.target != recipient.controller
    ):
        raise ValueError("Both original people must join this actual follow-through scene")
    return dict(
        obligation=item.id,
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        actor_controller=actual.controller,
        target_controller=recipient.controller,
        cast=cast.model_dump(mode="json"),
    )


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_battle import synchronize_damage

    synchronize_damage(game, c, event)
    actual = game.action(c, action["id"])
    if (
        actual["data"].get("harpy_flirt", {}).get("damage_followups")
        and not game.pending(c, actual["id"])
        and actual["state"] != "complete"
    ):
        state = load_state(c, game.store.campaign_id)
        finish(game, c, state, actual)
        game.save_action(c, actual)


def validate_escape_child(
    game: "GameService", c: Connection, parent: dict[str, Any], actor: ActorRef, prepared: PlayInput
) -> dict[str, Any]:
    meta = parent["data"].get("harpy_flirt")
    from girlframe.services.m2_state import load_state

    state = load_state(c, game.store.campaign_id)
    if meta is None or parent["state"] in ("complete", "aborted") or refs(parent)[1] != actor:
        raise ValueError("Only this original Flirt target can make the escape Play")
    validate(game, c, state, parent)
    row = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["kind"] == "escape_play"
            and x["actor_id"] == str(meta["target_controller"])
            and json.loads(x["body_json"]).get("actor") == actor.model_dump(mode="json")
        ),
        None,
    )
    if row is None or prepared.parent != parent["id"] or prepared.source_work:
        raise ValueError("Use the original held escape request without another work source")
    return dict(choice=row["id"], actor=actor.model_dump(mode="json"), parent=parent["id"])


def complete_escape_child(
    game: "GameService", c: Connection, child: dict[str, Any], event: str
) -> None:
    source = child["data"].get("harpy_flirt_escape_source")
    if source is None or child["state"] != "complete":
        return
    parent = game.action(c, source["parent"])
    if (
        child.get("parent_id") != parent["id"]
        or child["data"].get("actor_basic", {}).get("ref") != source["actor"]
    ):
        raise ValueError("Complete the actual original target's source-bound escape Play")
    pending = next(
        (
            x
            for x in game.pending(c, parent["id"])
            if x["id"] == source["choice"] and x["kind"] == "escape_play"
        ),
        None,
    )
    if pending is None:
        return
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
    parent["data"]["result"]["escaped"] = True
    parent["data"]["harpy_flirt"]["escape_child"] = child["id"]
    from girlframe.services.m2_state import load_state

    finish(game, c, load_state(c, game.store.campaign_id), parent)
    game.save_action(c, parent)
