"""Proof of the selected Strain source before reserving/consuming its next-roll +2."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_refusal as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def view(game: "GameService", viewer: GuildViewer) -> list[dict[str, Any]]:
    with game.store.engine.connect() as c:
        game.authorize(c, viewer, game=False)
        state = load_state(c, game.store.campaign_id)
        game.character_binding(c, state, viewer.user_id, require_current_profile=False)
        return [
            {"source": x["source"], "amount": x["amount"]}
            for x in rules.modifiers(state.refusal_bonuses, state.handler)
        ]


def prepare(
    game: "GameService", c: Connection, viewer: GuildViewer, state: GameState
) -> list[dict[str, Any]]:
    modifiers = rules.modifiers(state.refusal_bonuses, state.handler)
    if not modifiers:
        return []
    from girlframe.services.m3_access import Access

    Access(game.store).authorize(c, viewer, "plays")
    Access(game.store).authorize(c, viewer, "strain")
    works = t.m3["m3_required_work"]
    for bonus in state.refusal_bonuses:
        if bonus.action is not None:
            continue
        row = (
            c.execute(
                sa.select(works)
                .where(
                    works.c.campaign_id == game.store.campaign_id,
                    works.c.id == bonus.id,
                )
                .order_by(works.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == bonus.source_event,
                )
            )
            .mappings()
            .first()
        )
        source = (
            next((x for x in state.strain.events if x.id + ":effect" == bonus.id), None)
            if state.strain
            else None
        )
        if (
            row is None
            or row["state"] != "resolved"
            or row["kind"] != "strain_event"
            or row["off_duty_id"] != bonus.period
            or row["owner_id"] != str(bonus.handler)
            or row["event_id"] != bonus.source_event
            or source is None
            or source.rule_id != "strain.rebellion.low.1.2"
            or source.period_id != bonus.period
            or json.loads(row["body_json"]).get("rule_id") != source.rule_id
            or event is None
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != str(bonus.handler)
            or json.loads(event["payload_json"]).get("work_id") != bonus.id
            or json.loads(event["payload_json"]).get("rule_id") != source.rule_id
        ):
            raise WorkflowError(
                "SOURCE_CONTROL_MISSING: recover the actual resolved Strain source first."
            )
    return modifiers


def pre_roll(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = action["data"].get("m3_refusal", [])
    current = prepare(game, c, viewer, state)
    if current != expected:
        raise WorkflowError(
            "STALE_CONTROL: recover the unrolled refusal and confirm current sources."
        )
    actor = ActorRef(
        kind="pilot",
        entity=str(viewer.user_id),
        incarnation=game.character_binding(c, state, viewer.user_id, require_current_profile=False),
    )
    state.refusal_bonuses = rules.consume(
        state.refusal_bonuses, state.handler, expected, actor, action["id"]
    )
    return [{"source": x["source"], "amount": x["amount"]} for x in expected]
