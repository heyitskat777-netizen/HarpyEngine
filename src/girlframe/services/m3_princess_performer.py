"""Resolve only genuine Princess-directed resources; preserve normal actor ownership."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.engine import RowMapping

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.engine.m3_princess_sex import HighDirection
    from girlframe.services.m2_game import GameService


def acting_owner(
    game: "GameService", c: Connection, viewer: GuildViewer, prepared: PlayInput, state: GameState
) -> int:
    """A Princess directive supplies only its proved original performer's resources."""
    if prepared.parent and prepared.source_work:
        from girlframe.engine import m3_princess_sex as princess
        from girlframe.services.m3_princess_sex import child_source, pre_roll_child

        direction = next(
            (x for x in princess.directions(state) if x.id == prepared.source_work), None
        )
        if direction is not None and direction.child is not None:
            action = game.action(c, direction.child)
            if (
                viewer.user_id != direction.author_controller
                or prepared != PlayInput.model_validate(action["data"]["prepared"])
            ):
                raise WorkflowError("Use only this original directed Play and actual author")
            pre_roll_child(game, c, state, action)
            return direction.actor_controller

        source = child_source(
            game, c, viewer, state, prepared, int(game.action(c, prepared.parent)["channel_id"])
        )
        if source is not None:
            return int(source["actor_controller"])
    return viewer.user_id


def _battle_trigger(game: "GameService", c: Connection, action: dict[str, Any], event: str) -> int:
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if audit is None or audit["actor_id"] is None:
        raise WorkflowError("Recover the real directed battle completion cause")
    payload = json.loads(audit["payload_json"])
    choices = t.m2["m2_choices"]
    choice = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == payload.get("choice_id"),
                choices.c.action_id == action["id"],
                choices.c.state == "answered",
            )
        )
        .mappings()
        .first()
    )
    if (
        audit["kind"] in ("m2.choice_resolved", "m3.choice_resolved")
        and payload.get("action_id") == action["id"]
        and choice is not None
    ):
        scope = action["data"]["princess_child"]
        expected = (
            str(scope["author"]) if choice["actor_id"] == action["actor_id"] else choice["actor_id"]
        )
        if audit["actor_id"] == expected:
            return int(audit["actor_id"])
    work = t.m3["m3_required_work"]
    followups = action["data"]["battle"].get("followups", ())
    if followups and c.scalar(
        sa.select(work.c.id)
        .where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.id.in_(followups),
            work.c.event_id == event,
            work.c.state == "resolved",
        )
        .limit(1)
    ):
        return int(audit["actor_id"])
    raise WorkflowError(
        "SOURCE_BATTLE_COMPLETION_REQUIRED: retain the actual battle choice or work"
    )


def complete_battle(
    game: "GameService", c: Connection, action: dict[str, Any], trigger: str
) -> None:
    from girlframe.engine import m3_princess_sex as princess
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_princess_sex import complete_child

    state = load_state(c, game.store.campaign_id)
    child = game.action(c, action["id"])
    scope = child["data"].get("princess_child")
    if not scope or not child["data"].get("battle") or child["state"] != "complete":
        return
    direction = princess.direction(state, scope["direction"])
    if direction.completed_event:
        return
    human = _battle_trigger(game, c, child, trigger)
    event = str(uuid4())
    complete_child(game, c, state, child, event)
    game.event(
        c,
        human,
        str(uuid4()),
        "m3.princess_directed_battle_completed",
        state,
        event_id=event,
        action_id=child["id"],
        parent=direction.parent,
        direction=direction.id,
        trigger_event=trigger,
    )


def prove_battle_completion(
    game: "GameService", c: Connection, value: "HighDirection", audit: RowMapping
) -> None:
    payload = json.loads(audit["payload_json"])
    child = game.action(c, value.child or "")
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == child["id"],
        )
    )
    if (
        audit["kind"] != "m3.princess_directed_battle_completed"
        or payload.get("action_id") != child["id"]
        or payload.get("parent") != value.parent
        or payload.get("direction") != value.id
        or child.get("parent_id") != value.parent
        or child["actor_id"] != value.actor.entity
        or (child["data"].get("princess_child") or {}).get("direction") != value.id
        or not child["data"].get("battle")
        or child["state"] != "complete"
        or receipt is None
        or json.loads(receipt) != child["data"].get("receipt")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError("Prove the actual directed battle, source and immutable receipt")
    if int(audit["actor_id"]) != _battle_trigger(game, c, child, payload.get("trigger_event", "")):
        raise WorkflowError("Preserve the actual human battle-completion author")


def complete_npc_flirt(
    game: "GameService", c: Connection, action: dict[str, Any], trigger: str
) -> None:
    """Close only a genuine directed NPC Flirt after its canonical external work."""
    from girlframe.engine import m3_princess_sex as princess
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_npc_flirt import completion_author
    from girlframe.services.m3_princess_sex import complete_child

    state = load_state(c, game.store.campaign_id)
    child = game.action(c, action["id"])
    scope = child["data"].get("princess_child")
    if not scope or not child["data"].get("npc_flirt") or child["state"] != "complete":
        return
    direction = princess.direction(state, scope["direction"])
    if direction.completed_event:
        return
    human = completion_author(game, c, child, trigger)
    event = str(uuid4())
    complete_child(game, c, state, child, event)
    game.event(
        c,
        human,
        event,
        "m3.princess_directed_npc_flirt_completed",
        state,
        event_id=event,
        action_id=child["id"],
        parent=direction.parent,
        direction=direction.id,
        trigger_event=trigger,
    )


def prove_npc_flirt_completion(
    game: "GameService", c: Connection, value: "HighDirection", audit: RowMapping
) -> None:
    from girlframe.services.m3_npc_flirt import completion_author

    payload = json.loads(audit["payload_json"])
    child = game.action(c, value.child or "")
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == child["id"],
        )
    )
    if (
        audit["kind"] != "m3.princess_directed_npc_flirt_completed"
        or payload.get("action_id") != child["id"]
        or payload.get("parent") != value.parent
        or payload.get("direction") != value.id
        or child.get("parent_id") != value.parent
        or child["actor_id"] != value.actor.entity
        or (child["data"].get("princess_child") or {}).get("direction") != value.id
        or not child["data"].get("npc_flirt")
        or child["data"]["play"] != "flirt"
        or child["state"] != "complete"
        or receipt is None
        or json.loads(receipt) != child["data"].get("receipt")
        or game.pending(c, child["id"])
    ):
        raise WorkflowError("Prove the actual directed NPC Flirt, source and immutable receipt")
    if int(audit["actor_id"]) != completion_author(
        game, c, child, payload.get("trigger_event", "")
    ):
        raise WorkflowError("Preserve the actual human NPC consequence completion author")
