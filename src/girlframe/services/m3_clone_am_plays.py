"""Actual clone Flirt source choices; ordinary Bond endpoints never use human aliases."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_clone_am as rules
from girlframe.engine.m2 import FLIRT_QUESTIONS, ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import change, depth, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def copy_state(state: GameState, other: GameState) -> None:
    for field in GameState.model_fields:
        setattr(state, field, getattr(other, field))


def prepare(
    game: "GameService",
    c: Connection,
    state: GameState,
    cast: SceneCast,
    ref: ActorRef,
    prepared: PlayInput,
) -> dict[str, Any]:
    actor = resolve(state, ref, profiles(c, game.store.campaign_id))
    target = (
        resolve(state, prepared.target_actor, profiles(c, game.store.campaign_id))
        if prepared.target_actor
        else None
    )
    if target is None or target.ref.kind != "pilot":
        raise ValueError("SOURCE_PORT_REQUIRED: select the actual original Girl in this scene")
    if not any(x.actor == target.ref for x in cast.roles):
        raise ValueError("Join the actual original target person to this scene")
    if (
        actor.cell is None
        or actor.cell != target.cell
        or actor.offstage_source
        or target.offstage_source
    ):
        raise ValueError("Establish actual interaction with this original Frame-resident copy")
    return dict(
        actor=ref.model_dump(mode="json"),
        target=target.ref.model_dump(mode="json"),
        target_controller=target.controller,
    )


def refs(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"].get("clone_flirt") or action["data"]["clone_followthrough"]
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])


def unmark(state: GameState, ref: ActorRef, selected: tuple[str, ...], maximum: int) -> None:
    if len(selected) != len(set(selected)) or len(selected) > maximum:
        raise ValueError("Choose only the printed number of actual marked Identities")
    if ref.kind == "clone_am":
        value = rules.current(state, ref)
        if set(selected) - {value.identity.id} or selected and not value.identity.marked:
            raise ValueError("Unmark only this copy's actual marked Identity")
        rules.unmark_additional(state, int(value.original.entity), selected)
        return
    sheet = state.sheets[ref.entity]
    choices = (*sheet.identities, *rules.additional_identities(state, sheet.owner))
    if set(selected) - {x.id for x in choices if x.marked}:
        raise ValueError("Unmark only this actual person's marked Identities")
    for identity in sheet.identities:
        if identity.id in selected:
            identity.marked = False
    extra = {x.id for x in rules.additional_identities(state, sheet.owner)}
    rules.unmark_additional(state, sheet.owner, tuple(x for x in selected if x in extra))
    sheet.revision += 1


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    actor, target = refs(action)
    if action["data"]["result"]["tier"] == "low":
        if depth(state, actor, target):
            copy_state(state, change(state, actor, target, -1, action["data"]["response_event"]))
        game.request(
            c, action, action["data"]["clone_flirt"]["target_controller"], "clone_flirt_target"
        )
    else:
        game.request(c, action, int(action["actor_id"]), "clone_flirt_actor")


def respond(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_actor_plays import ActorPlayService

    source = ActorPlayService(game)
    actor, target = refs(action)
    result = action["data"]["result"]
    level, kind = result.get("tier"), row["kind"]
    event = action["data"]["response_event"]
    if kind == "clone_flirt_followthrough_confirm":
        if answer.flag is None or not answer.text.strip():
            raise ValueError(
                "The actual target must confirm or decline the described follow-through"
            )
        item = next(
            x
            for x in state.obligations
            if x.id == action["data"]["clone_followthrough"]["obligation"]
        )
        if item.state != "pending":
            raise ValueError("This actual follow-through already resolved")
        if answer.flag:
            copy_state(state, change(state, actor, target, 1, event))
            next(x for x in state.obligations if x.id == item.id).state = "fulfilled"
        result.update(confirmed=answer.flag, response=answer.text)
        source.finish(c, state, action)
    elif kind == "clone_flirt_actor":
        if len(answer.options) != 1 or answer.options[0] not in FLIRT_QUESTIONS:
            raise ValueError("Ask one actual printed Flirt question")
        unmark(state, actor, answer.denied, 2)
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
        game.request(
            c, action, action["data"]["clone_flirt"]["target_controller"], "clone_flirt_target"
        )
    elif kind == "clone_flirt_target":
        if not answer.text.strip():
            raise ValueError("The actual target must answer for herself")
        unmark(state, target, answer.denied, 1 if level == "low" else 2)
        result["target_answer"] = answer.text
        if level == "low":
            if len(answer.options) > 1 or set(answer.options) - set(FLIRT_QUESTIONS):
                raise ValueError("Optionally ask one actual return question")
            if answer.options:
                result["return_question"] = answer.options[0]
                game.request(c, action, int(action["actor_id"]), "clone_flirt_answer")
            else:
                source.finish(c, state, action)
            return
        if (
            result["question"] == "intimacy"
            and depth(state, actor, target) == 2
            and answer.flag is not True
        ):
            raise ValueError("Record the actual human's safety consent; it is never inferred")
        game.obligation(
            state,
            action,
            "clone_flirt_followthrough",
            int(action["actor_id"]),
            action["data"]["clone_flirt"]["target_controller"],
            actor=actor.model_dump_json(),
            target_actor=target.model_dump_json(),
            wanted=answer.text,
        )
        extra = result.get("extra")
        if extra == "handler":
            from girlframe.services.m3_handler_plays import request_from_play

            required = game.request(c, action, state.handler, "handler_brief")
            changed, grant = request_from_play(
                game,
                c,
                state,
                action,
                required,
                "flirt.high.handler",
                event,
                targets=(actor, target),
            )
            copy_state(state, changed)
            action["data"]["handler_play_m3"] = grant
        elif extra == "escape":
            game.request(
                c, action, action["data"]["clone_flirt"]["target_controller"], "clone_flirt_escape"
            )
        elif extra == "owe":
            game.request(
                c, action, action["data"]["clone_flirt"]["target_controller"], "clone_flirt_owe"
            )
        else:
            source.finish(c, state, action)
    elif kind == "clone_flirt_answer":
        if not answer.text.strip():
            raise ValueError("Answer the actual returned question")
        result["actor_answer"] = answer.text
        source.finish(c, state, action)
    elif kind == "clone_flirt_owe":
        rules.add_tag(
            state, actor, answer.text, tuple(action["data"]["participants"]), giver=target
        )
        tag = rules.tags(state, actor)[-1]
        game.obligation(
            state,
            action,
            "clone_cannot_refuse_until_tag_resolved",
            int(action["actor_id"]),
            action["data"]["clone_flirt"]["target_controller"],
            actor=actor.model_dump_json(),
            target_actor=target.model_dump_json(),
            tag=tag.id,
        )
        source.finish(c, state, action)
    elif kind == "clone_flirt_escape":
        if answer.options == ("helpless",):
            copy_state(state, make_helpless(state, target, actor, event))
            result["helpless_actor"] = target.model_dump(mode="json")
            source.finish(c, state, action)
        elif answer.options == ("damage",) and len(answer.denied) == 1:
            from girlframe.services.m3_battle import damage_actor

            changed, damage_work = damage_actor(
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
                occurrence="clone-flirt-escape",
            )
            copy_state(state, changed)
            result["escaped"] = True
            action["data"]["clone_flirt"]["damage_followups"] = list(damage_work)
            if not damage_work:
                source.finish(c, state, action)
        elif answer.options == ("play",):
            game.request(
                c, action, action["data"]["clone_flirt"]["target_controller"], "escape_play"
            )
        else:
            raise ValueError("Accept actual Helplessness or escape by actual Asset damage or Play")
    else:
        raise ValueError("Use this original source's actual Flirt response")


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    actor, target = refs(action)
    ref = actor if row["kind"] == "clone_flirt_actor" else target
    view = resolve(state, ref, profiles(c, game.store.campaign_id))
    return dict(
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        identities=[x.model_dump(mode="json") for x in view.identities],
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
    item = next(
        (
            x
            for x in state.obligations
            if x.id == prepared.source_work
            and x.kind == "clone_flirt_followthrough"
            and x.state == "pending"
            and x.owner == int(rules.current(state, ref).original.entity)
        ),
        None,
    )
    if item is None or prepared.heat or prepared.identity or prepared.gain or prepared.pair_share:
        raise ValueError("Choose this copy's actual owed follow-through without dice or resources")
    actor = ActorRef.model_validate_json(item.details["actor"])
    target = ActorRef.model_validate_json(item.details["target_actor"])
    original = game.action(c, item.action)
    if actor != ref or refs(original) != (actor, target) or original["state"] != "complete":
        raise ValueError("Recover this original completed Flirt and its owed source")
    original_target = resolve(state, target, profiles(c, game.store.campaign_id))
    if not any(x.actor == target for x in cast.roles) or item.target != original_target.controller:
        raise ValueError("The actual original target must join this follow-through scene")
    return dict(
        obligation=item.id,
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json"),
        target_controller=original_target.controller,
    )


def synchronize(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> None:
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_actor_plays import ActorPlayService
    from girlframe.services.m3_battle import synchronize_damage

    synchronize_damage(game, c, event)
    actual = game.action(c, action["id"])
    if actual["data"].get("clone_flirt", {}).get("damage_followups") and not game.pending(
        c, actual["id"]
    ):
        state = load_state(c, game.store.campaign_id)
        ActorPlayService(game).finish(c, state, actual)
        game.save_action(c, actual)
