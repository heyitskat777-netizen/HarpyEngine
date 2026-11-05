"""Source-specific extensions of an actual owned Dive, never a second roll."""

import json
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import Connection

from girlframe.engine import m3_mockingbird as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_dive import Outcome, resources
from girlframe.engine.m3_mockingbird_assets import classify
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

CLASSIFY = "call_reclassify_assets"
BOARD = "call_cockpit_guest"
RELAY = "call_gorgon_relay"


def enabled(state: GameState, actor: ActorRef) -> bool:
    if not rules.owns(state, actor, rules.CALL):
        return False
    try:
        load_registry().require_available(rules.CALL)
    except ValueError:
        return False
    return True


def options(state: GameState, actor: ActorRef) -> tuple[str, ...]:
    return (CLASSIFY, BOARD, RELAY) if enabled(state, actor) else ()


def effect(state: GameState, actor: ActorRef, answer: ChoiceAnswer) -> dict[str, Any]:
    if (
        answer.fields
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
        or answer.text
        or len(set(answer.options)) != len(answer.options)
    ):
        raise WorkflowError("Choose only actual Asset moves and any exact cap replacements")
    actual, _ = resources(state, actor)
    old = {x.id: x for x in actual}
    if not set(answer.options) <= set(old):
        raise WorkflowError("Move only actual existing owned Girl or Frame Assets")
    return dict(
        moves={key: "frame" if old[key].family == "girl" else "girl" for key in answer.options},
        replaced=list(answer.denied),
    )


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    step: int,
    actor: ActorRef,
) -> Outcome:
    selected = action["data"]["dive"]["steps"][step]
    data = selected["effect"]
    changed, followups = classify(
        state,
        profiles(c, game.store.campaign_id),
        actor,
        {key: _family(value) for key, value in data["moves"].items()},
        tuple(data["replaced"]),
        action=action["id"],
        step=step,
        event=action["data"]["response_event"],
        account=selected["account"],
    )
    changed.facts.append(
        dict(
            kind="dive_effect",
            actor=actor.model_dump_json(),
            action=action["id"],
            step=str(step),
            option=CLASSIFY,
            effect=json.dumps(data, sort_keys=True),
            source_event=action["data"]["response_event"],
        )
    )
    return Outcome(state=changed, followups=followups)


def _family(value: str) -> Literal["girl", "frame"]:
    if value == "girl":
        return "girl"
    if value == "frame":
        return "frame"
    raise ValueError("Choose only an actual Girl or Frame classification")


def prove_classification_void(
    state: GameState,
    actor: ActorRef,
    action: dict[str, Any],
    body: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    event = body["source_event"]
    fact = next(
        (
            x
            for x in state.facts
            if x.get("kind") == "mockingbird_classification"
            and x.get("actor") == actor.model_dump_json()
            and x.get("action") == action["id"]
            and x.get("step") == str(body["step"])
            and x.get("event") == event
        ),
        None,
    )
    selected = action["data"]["dive"]["steps"][body["step"]]
    if (
        fact is None
        or selected["option"] != CLASSIFY
        or not rules.owns(state, actor, rules.CALL)
        or set(selected["effect"]["moves"]) != set(answer.options)
        or selected["effect"]["replaced"] != list(answer.denied)
    ):
        raise ValueError("Recover the actual source Call classification and owned response")
    assets, _ = resources(state, actor)
    if not all(
        next((x.classification_event == event for x in assets if x.id == key), False)
        for key in selected["effect"]["moves"]
    ):
        raise ValueError("Recover the exact actual sole-origin classification source")
