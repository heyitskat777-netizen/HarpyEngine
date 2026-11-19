"""Observed Insurgent refusals and an original Girl's own declared sympathy."""

import json
from typing import TYPE_CHECKING, Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.services.m3_handler_book_orders import direct_order_source
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.insurgent.rebel-sympathizers"
WATCH = "insurgent_surveillance"
REVEAL = "insurgent_reveal_sympathy"


class Label(Model):
    girl: ActorRef
    observer: ActorRef
    status: Literal["surveilled", "sympathizer"]
    event: str
    scene: str
    action: str
    tag: str


def labels(state: GameState, girl: ActorRef) -> tuple[Label, ...]:
    return tuple(
        value
        for row in state.facts
        if row.get("kind") == "insurgent_loyalty_label"
        and (value := Label.model_validate_json(row["body"])).girl == girl
    )


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any] | None:
    data = action["data"]
    result = data["result"]
    if (
        data.get("play") != "disobey_orders"
        or not data.get("receipt")
        or not result.get("can_disobey")
        or not result.get("handler_knows")
    ):
        return None
    return direct_order_source(
        game, c, state, action, book="Insurgent", rule=RULE, order_state="disobey"
    )


def offer(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    source = _source(game, c, state, action)
    if source is None:
        return
    girl = ActorRef.model_validate(source["actor"])
    observer = ActorRef.model_validate(source["handler"])
    actual = labels(state, girl)
    if any(x.status == "sympathizer" or x.observer != observer for x in actual):
        return
    if any(x.status == "surveilled" for x in actual):
        game.request(c, action, int(girl.entity), REVEAL, source)
    else:
        game.request(c, action, int(source["handler"]["entity"]), WATCH, source)


def _proved_surveillance(
    game: "GameService", c: Connection, state: GameState, girl: ActorRef, observer: ActorRef
) -> bool:
    history = t.m2["m2_state_history"]
    for value in labels(state, girl):
        if value.status != "surveilled" or value.observer != observer:
            continue
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.event_id == value.event,
            )
        )
        if raw and value in labels(GameState.model_validate_json(raw), girl):
            action = game.action(c, value.action)
            if action["data"].get("insurgent_observation", {}).get("tag") == value.tag:
                return True
    return False


def decide(
    choices: "ChoiceEngine",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    account = answer.text.strip()
    if (
        answer.options
        or answer.denied
        or answer.fields
        or answer.member is not None
        or answer.number is not None
        or answer.flag is None
        or bool(account) != answer.flag
    ):
        raise WorkflowError("Confirm and describe your actual observed act or disclosure, or pass")
    if not answer.flag:
        return
    game = choices.game
    source = _source(game, c, state, action)
    if source is None or source != json.loads(request["body_json"]):
        raise WorkflowError("Recover the actual observed refusal and original Insurgent")
    girl = ActorRef.model_validate(source["actor"])
    observer = ActorRef.model_validate(source["handler"])
    character = girl.incarnation
    if girl.kind != "pilot" or character is None:
        raise WorkflowError("Recover the original Girl from the witnessed refusal")
    actual = labels(state, girl)
    watching = request["kind"] == WATCH
    if watching:
        if any(x.status == "surveilled" for x in actual) or request["actor_id"] != observer.entity:
            raise WorkflowError("Only the original witness can record this first observed lapse")
    elif (
        request["kind"] != REVEAL
        or request["actor_id"] != girl.entity
        or any(x.status == "sympathizer" for x in actual)
        or not _proved_surveillance(game, c, state, girl, observer)
    ):
        raise WorkflowError(
            "Only the original Surveilled Girl can disclose her own sympathies here"
        )
    target, witness = int(girl.entity), int(observer.entity)
    tag = choices.add_tag(
        state, action, target, witness, "Surveilled" if watching else "Sympathizer"
    )
    tag.observers = (witness, target)
    result = Label(
        girl=girl,
        observer=observer,
        status="surveilled" if watching else "sympathizer",
        event=action["data"]["response_event"],
        scene=action["scene_id"],
        action=action["id"],
        tag=tag.id,
    )
    state.facts.append(dict(kind="insurgent_loyalty_label", body=result.model_dump_json()))
    if watching:
        action["data"]["insurgent_observation"] = dict(tag=tag.id, account=account)
    else:
        action["data"]["insurgent_disclosure"] = dict(tag=tag.id, account=account)
        game.obligation(
            state,
            action,
            "punishment",
            target,
            witness,
            cause=RULE,
            source_pdf="135",
            character_id=character,
        )
