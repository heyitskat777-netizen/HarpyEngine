"""A Girl can Tag the original Trainer after a successful refusal."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine.m2 import ChoiceAnswer, GameState, TagState
from girlframe.services.m3_handler_book_orders import direct_order_source
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.trainer.control-freak"
CHOICE = "trainer_control_freak"


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any] | None:
    data = action["data"]
    if (
        data.get("play") != "disobey_orders"
        or not data.get("receipt")
        or not data["result"].get("can_disobey")
    ):
        return None
    return direct_order_source(
        game, c, state, action, book="Trainer", rule=RULE, order_state="disobey"
    )


def offer(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> None:
    source = _source(game, c, state, action)
    if source is not None:
        game.request(c, action, int(action["actor_id"]), CHOICE, source)


def apply(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    label = answer.text.strip()
    if (
        answer.options not in (("pass",), ("give_tag",))
        or answer.denied
        or answer.fields
        or answer.flag is not None
        or answer.member is not None
        or answer.number is not None
        or (answer.options == ("pass",) and label)
        or (answer.options == ("give_tag",) and not 1 <= len(label) <= 120)
    ):
        raise WorkflowError(
            "Pass or give the original Trainer one Tag with a 1–120 character label"
        )
    if answer.options == ("pass",):
        return
    source = _source(game, c, state, action)
    if source is None or source != json.loads(request["body_json"]):
        raise WorkflowError(
            "Recover the original successful refusal and Trainer before giving a Tag"
        )
    girl = int(action["actor_id"])
    state.handler_tags.append(
        TagState(
            id=str(uuid4()),
            label=label,
            giver=girl,
            observers=(girl, int(source["handler"]["entity"])),
        )
    )
