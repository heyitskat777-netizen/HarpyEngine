"""Source-owned Sex Play effects; no generated intimacy, discovery or fictional answers."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_mockingbird_sex as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import change
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def context(action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    meta = action["data"]["mockingbird"]
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(
        meta["parties"][0]["actor"]
    )


def _copy(state: GameState, changed: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(changed, name))


def results(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    from girlframe.services.m3_mockingbird_plays import _finish

    actor, target = context(action)
    level = action["data"]["result"]["tier"]
    if level == "low":
        _copy(
            state,
            rules.helpless(state, actor, target, action["id"], action["data"]["response_event"]),
        )
        _finish(game, c, state, action)
        return
    if level == "mid":
        game.request(c, action, int(action["actor_id"]), "mockingbird_sex_select")
        return
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.rules in ("handler", "director", "handler_girl"):
        kind = "mockingbird_sex_high_commit"
    elif actual.rules == "npc":
        kind = "mockingbird_sex_npc_void"
    elif any(not x.void for x in rules.assets(state, target)):
        kind = "mockingbird_sex_infect"
    else:
        kind = "mockingbird_sex_saturated"
    game.request(
        c,
        action,
        action["data"]["mockingbird"]["judge_controller"]
        if kind == "mockingbird_sex_npc_void"
        else int(action["actor_id"]),
        kind,
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_mockingbird_plays import _finish
    from girlframe.services.m3_mockingbird_void import stage_handler_void

    actor, target = context(action)
    meta = action["data"]["mockingbird"]
    event = action["data"]["response_event"]
    kind = row["kind"]
    if kind == "mockingbird_sex_select":
        from girlframe.engine.m3_mockingbird_state import CAPABILITIES

        if (
            str(row["actor_id"]) != str(action["actor_id"])
            or len(answer.options) != 1
            or answer.denied
            or answer.flag is not None
            or answer.number is not None
            or answer.member is not None
            or answer.text
        ):
            raise WorkflowError("Choose your exact printed mid-tier intimacy effect")
        if answer.options == ("starry",):
            if (
                set(answer.fields) != {"capability"}
                or answer.fields["capability"] not in CAPABILITIES
            ):
                raise WorkflowError("Choose the actual always-available conversation capability")
            target_view = resolve(
                state, target, profiles(c, game.store.campaign_id), require_current_profile=False
            )
            changed = rules.starry(
                state,
                profiles(c, game.store.campaign_id),
                actor,
                target,
                answer.fields["capability"],
                action["id"],
                event,
                tuple(sorted({int(action["actor_id"]), target_view.controller})),
            )
            _copy(state, changed)
            _finish(game, c, state, action)
            return
        raise WorkflowError("This actual selected intimacy effect is still being completed")
    if kind in ("mockingbird_handler_void", "mockingbird_handler_girl_void"):
        raise WorkflowError(
            "Finish the actual original Handler Void treatment; no acknowledgment substitutes"
        )
    if kind == "mockingbird_sex_high_commit":
        if (
            action["data"]["result"]["tier"] != "high"
            or str(row["actor_id"]) != str(action["actor_id"])
            or answer.flag is not True
            or answer.options
            or answer.denied
            or answer.fields
            or answer.text
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError(
                "The actual initiator applies the printed infection to this source counterpart"
            )
        actual = resolve(
            state, target, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if actual.rules == "handler_girl":
            from girlframe.services.m3_mockingbird_void import stage_handler_girl_void

            stage_handler_girl_void(game, c, state, action, target, row["id"], event)
        else:
            stage_handler_void(game, c, state, action, target, row["id"], event)
        from girlframe.engine.m3_actor_bonds import bond_ref

        _copy(state, change(state, bond_ref(state, actor), bond_ref(state, target), 1, event))
        _copy(state, rules.exposure(state, actor, target, "both_risk", action["id"], event))
        meta["phase"] = "void_pending"
        return
    raise WorkflowError("This actual intimacy effect port is still being completed")


def projection(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    from girlframe.engine.m3_mockingbird_state import CAPABILITIES

    actor, target = context(action)
    if row["kind"] in ("mockingbird_handler_void", "mockingbird_handler_girl_void"):
        return dict(work_id=json.loads(row["body_json"])["work_id"])
    actual = resolve(
        state, target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return dict(
        target=actual.label,
        assets=[dict(id=x.id, label=x.name) for x in rules.assets(state, target) if not x.void],
        options=["starry"],
        capabilities=list(CAPABILITIES),
    )
