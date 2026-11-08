"""Source-proved Asset failures hold actual Engage until its Handler authors calamities."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_sabotage as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

KIND = "budget_asset_calamity"


def prove(game: GameService, c: Connection, value: rules.Trap) -> None:
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    original = (
        next((x for x in rules.traps(GameState.model_validate_json(raw)) if x.id == value.id), None)
        if raw
        else None
    )
    if (
        event is None
        or original is None
        or event["kind"] != "m3.strain_effect_applied"
        or event["actor_id"] != value.handler.entity
        or json.loads(event["payload_json"]).get("rule_id") != "strain.budget.low.2.2"
        or json.loads(event["payload_json"]).get("work_id") != value.source_work
        or any(
            getattr(original, k) != getattr(value, k)
            for k in ("id", "source_work", "source_event", "handler", "pin", "account")
        )
    ):
        raise WorkflowError("Recover the original private Asset card source")


def intercept(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
    actor: ActorRef,
    assets: set[str],
) -> bool:
    if action["data"].get("sabotage_resolving"):
        return False
    selected = rules.matching(state, actor, assets)
    if not selected:
        return False
    if (
        action["parent_id"]
        or action["data"].get("actor_basic")
        or row["kind"] != "engage_maneuvers"
    ):
        raise WorkflowError("SOURCE_PORT_REQUIRED: preserve this nested Asset-use interruption")
    if action["data"].get("sabotage"):
        raise WorkflowError("Resume the actual already revealed Asset calamity")
    for trap in selected:
        prove(game, c, trap)
        if not same_handler_body(state, trap.handler):
            raise WorkflowError("Recover the original Asset card's Handler before this failure")
        rules.put(
            state,
            trap.model_copy(
                update=dict(
                    phase="revealed",
                    action=action["id"],
                    choice=row["id"],
                    reveal_event=action["data"]["response_event"],
                )
            ),
        )
    action["data"]["sabotage"] = dict(
        traps=[x.id for x in selected],
        original_choice=row["id"],
        answer=answer.model_dump(mode="json"),
        actor=actor.model_dump(mode="json"),
        receipt=action["data"]["receipt"],
    )
    game.request(
        c, action, int(selected[0].handler.entity), KIND, dict(traps=[x.id for x in selected])
    )
    return True


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    from girlframe.services.m3_engage import apply as apply_engage

    meta = action["data"].get("sabotage")
    selected = [x for x in rules.traps(state) if meta and x.id in meta["traps"]]
    if (
        not meta
        or not selected
        or set(answer.fields) != {x.id for x in selected}
        or answer.options
        or answer.denied
        or answer.text
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
    ):
        raise WorkflowError("Describe the actual calamity for each revealed Asset card")
    for trap in selected:
        prove(game, c, trap)
        if (
            not same_handler_body(state, trap.handler)
            or trap.handler.entity != row["actor_id"]
            or trap.phase != "revealed"
            or trap.action != action["id"]
            or not answer.fields[trap.id].strip()
            or len(answer.fields[trap.id]) > 1200
        ):
            raise WorkflowError(
                "Only the original Handler supplies these actual revealed calamities"
            )
    responses = t.m2["m2_responses"]
    original = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == meta["original_choice"],
            )
        )
        .mappings()
        .one()
    )
    signed = (
        c.execute(
            sa.select(responses).where(
                responses.c.campaign_id == game.store.campaign_id,
                responses.c.choice_id == original["id"],
            )
        )
        .mappings()
        .one()
    )
    if (
        signed["actor_id"] != meta["actor"]["entity"]
        or json.loads(signed["answer_json"]) != meta["answer"]
        or action["data"]["receipt"] != meta["receipt"]
    ):
        raise WorkflowError("Recover the actual actor's saved choice and unchanged real receipt")
    action["data"]["sabotage_resolving"] = True
    action["data"]["sabotage_failed_assets"] = list({x.pin.asset for x in selected})
    apply_engage(
        game,
        c,
        state,
        action,
        dict(original),
        ChoiceAnswer.model_validate_json(json.dumps(meta["answer"])),
    )
    action["data"].pop("sabotage_resolving")
    for trap in selected:
        rules.put(
            state,
            trap.model_copy(
                update=dict(
                    phase="spent",
                    calamity=answer.fields[trap.id].strip(),
                    resolved_event=action["data"]["response_event"],
                )
            ),
        )
    action["data"]["result"]["asset_calamities"] = [answer.fields[x.id].strip() for x in selected]
    action["data"]["sabotage"]["complete"] = True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> list[dict[str, str]]:
    meta = action["data"].get("sabotage") or {}
    result = []
    for trap in rules.traps(state):
        if trap.id not in meta.get("traps", []):
            continue
        prove(game, c, trap)
        result.append(
            dict(
                id=trap.id,
                label=next(
                    (
                        x.name
                        for x in state.sheets[trap.pin.owner.entity].assets
                        if x.id == trap.pin.asset
                    ),
                    "Original used Asset",
                ),
            )
        )
    return result
