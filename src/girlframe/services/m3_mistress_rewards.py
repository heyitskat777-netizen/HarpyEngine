"""Only the original Girl can accept the Mistress's rewards for direct obedience."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine.m2 import ChoiceAnswer, GameState, shift_status
from girlframe.services.m3_handler_book_orders import direct_order_source
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.mistress.catch-more-flies-with-honey"
OFFER = "mistress_honey_offer"
REPLY = "mistress_honey_reply"
REJECTION = "mistress_honey_rejection"
REWARDS = ("praise", "pet_name", "raise_status")
LABELS = {
    "praise": "Praise or sympathy",
    "pet_name": "A pet name",
    "raise_status": "Raise your Status",
}


def _source(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any] | None:
    if action["data"].get("play") != "receive_orders" or action["data"]["result"].get(
        "response"
    ) not in ("obedient", "immediate"):
        return None
    return direct_order_source(
        game, c, state, action, book="Mistress", rule=RULE, order_state="followed"
    )


def offer(game: "GameService", c: Connection, state: GameState, action: dict[str, Any]) -> bool:
    source = _source(game, c, state, action)
    if source is None:
        return False
    game.request(c, action, int(source["handler"]["entity"]), OFFER, dict(source=source))
    return True


def choose(
    choices: "ChoiceEngine",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    game = choices.game
    body = json.loads(request["body_json"])
    source = _source(game, c, state, action)
    if source is None or source != body["source"]:
        raise WorkflowError("Recover the original Mistress, Girl and unhesitating obedience")
    if (
        answer.denied
        or answer.number is not None
        or answer.member is not None
        or answer.text.strip()
    ):
        raise WorkflowError("Use only the fields for this reward decision")
    handler, target = int(source["handler"]["entity"]), int(source["actor"]["entity"])
    rewards = action["data"].setdefault("mistress_rewards", {})
    kind = request["kind"]
    if kind == OFFER:
        if answer.options == ("pass",) and not answer.fields and answer.flag is None:
            return
        if (
            not 1 <= len(answer.options) <= 2
            or not set(answer.options) <= set(REWARDS)
            or answer.flag is not None
            or set(answer.fields) - {"praise", "pet_name", "tag"}
        ):
            raise WorkflowError("Choose one or two offered rewards, or pass")
        for option in ("praise", "pet_name"):
            value = answer.fields.get(option, "").strip()
            if bool(value) != (option in answer.options):
                raise WorkflowError("Provide an account for each chosen spoken reward only")
        tag = answer.fields.get("tag", "").strip()
        if tag and ("pet_name" not in answer.options or len(tag) > 120):
            raise WorkflowError("Only a pet name can carry a matching Tag of up to 120 characters")
        for reward in answer.options:
            offered = dict(source=source, reward=reward)
            if reward != "raise_status":
                offered["account"] = answer.fields[reward].strip()
            if reward == "pet_name" and tag:
                offered["tag"] = tag
            decision = game.request(c, action, target, REPLY, offered)
            rewards[decision] = dict(offer=offered, state="pending")
        return
    if kind == REPLY:
        recorded = rewards.get(request["id"])
        if (
            recorded is None
            or recorded != dict(offer=body, state="pending")
            or answer.flag is None
            or answer.options
            or answer.fields
        ):
            raise WorkflowError("The original Girl accepts or rejects this exact offered reward")
        recorded.update(state="accepted" if answer.flag else "rejected")
        if answer.flag and body["reward"] == "raise_status":
            shift_status(state, target, 1)
            state.sheets[str(target)].revision += 1
        if answer.flag and body.get("tag"):
            tag_value = choices.add_tag(state, action, target, handler, body["tag"])
            tag_value.observers = (handler, target)
            recorded["tag"] = tag_value.id
        if all(x["state"] != "pending" for x in rewards.values()) and any(
            x["state"] == "rejected" for x in rewards.values()
        ):
            game.request(c, action, handler, REJECTION, dict(source=source))
        return
    if (
        kind != REJECTION
        or answer.flag is not None
        or answer.fields
        or answer.options
        not in (
            ("smile",),
            ("punish",),
        )
    ):
        raise WorkflowError("Choose how the original Mistress treats the rejected reward")
    action["data"]["mistress_reward_rejection"] = answer.options[0]
    if answer.options == ("punish",):
        action["data"]["mistress_reward_discipline"] = game.obligation(
            state,
            action,
            "punishment",
            target,
            handler,
            cause=RULE,
            source_pdf="125",
            character_id=source["actor"]["incarnation"],
        )
