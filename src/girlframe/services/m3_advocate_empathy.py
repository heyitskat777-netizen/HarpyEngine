"""An original Advocate reacts to the actual outcome of their direct order."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, shift_status
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m3_access import Access, digest
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m2_game import GameService

RULE = "handler-playbook.advocate.conditional-empathy"
CHOICE = "advocate_empathy"
BAD_GIRL = "Bad Girl"
REWARDS = ("pass", "apologize", "apologize_profusely", "compliment_tag", "raise_status")


def _source(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    order_state: str,
) -> dict[str, Any] | None:
    persona = state.handler_persona
    handler = active_handler(state)
    if persona is None or persona.draft.playbook != "Advocate" or handler is None:
        return None
    policy = game.store.policy.m3_approval
    if (
        policy is None
        or "plays" not in policy.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return None
    registry = Access(game.store).registry
    if registry is None or digest(registry) != policy.registry_sha256:
        return None
    entry = registry.entry(RULE)
    if (
        entry.implementation == "unimplemented"
        or entry.module not in registry.enabled_modules
        or (policy.scope == "core_complete" and not entry.verified)
    ):
        return None
    order_id = action["data"].get("order_id") or action["data"].get("prepared", {}).get("order_id")
    table = t.m2["m2_orders"]
    order = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == order_id,
                table.c.issuer_id == handler.entity,
                table.c.state == order_state,
                table.c.target_id == action["actor_id"],
                table.c.channel_id == action["channel_id"],
            )
        )
        .mappings()
        .first()
    )
    if order is None or json.loads(order["body_json"]).get("npc_order"):
        return None
    proof = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == persona.source_event,
        )
    ).first()
    if proof is None or proof.kind != "m3.handler_activated" or proof.actor_id != handler.entity:
        return None
    target = current_ref(state, int(order["target_id"]))
    return dict(
        handler=handler.model_dump(mode="json"),
        actor=target.model_dump(mode="json"),
        persona=persona.source_event,
        order=order_id,
        rule=RULE,
    )


def _bad_girl(state: GameState, target: int) -> bool:
    return any(
        x.label.strip().casefold() == BAD_GIRL.casefold() for x in state.sheets[str(target)].tags
    )


def on_discovery(
    choices: "ChoiceEngine",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> None:
    if not action["data"]["result"].get("can_disobey"):
        return
    source = _source(choices.game, c, state, action, "disobey")
    target = int(action["actor_id"])
    if source is not None and not _bad_girl(state, target):
        tag = choices.add_tag(state, action, target, int(source["handler"]["entity"]), BAD_GIRL)
        action["data"]["result"]["bad_girl_tag"] = tag.id


def offer_reward(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    source = _source(game, c, state, action, "followed")
    if source is None or _bad_girl(state, int(action["actor_id"])):
        return False
    game.request(c, action, int(source["handler"]["entity"]), CHOICE, source)
    return True


def apply_reward(
    choices: "ChoiceEngine",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    if len(answer.options) != 1 or answer.options[0] not in REWARDS:
        raise WorkflowError("Choose one actual Advocate response or pass")
    selected = answer.options[0]
    if selected == "pass":
        return
    target = int(action["actor_id"])
    source = _source(choices.game, c, state, action, "followed")
    if source is None or source != json.loads(request["body_json"]) or _bad_girl(state, target):
        raise WorkflowError("Recover the original untagged Girl, obeyed order and Advocate")
    result: dict[str, Any] = dict(choice=selected)
    if selected == "raise_status":
        shift_status(state, target, 1)
        state.sheets[str(target)].revision += 1
    else:
        if not answer.text.strip():
            raise WorkflowError("Record what your original Advocate says in this scene")
        result["account"] = answer.text.strip()
        if selected == "compliment_tag":
            tag = choices.add_tag(
                state, action, target, int(request["actor_id"]), answer.fields.get("tag", "")
            )
            result["tag"] = tag.id
    action["data"]["result"]["advocate_response"] = result
