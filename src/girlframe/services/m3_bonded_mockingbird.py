"""Canonical native Bonded Pair-rule Mockingbird child receipt admission."""

import json
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_bonded as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_mockingbird_state import Trigger
from girlframe.services.m3_dose_up import _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prove_native_child(
    game: "GameService", c: Connection, state: GameState, child: Trigger, action: dict[str, Any]
) -> bool:
    meta = action["data"]["mockingbird"]
    if child.bonded_source is None or meta.get("bonded_lesson") is not None:
        return False
    from girlframe.services.m3_bonded import prove_delegation
    from girlframe.services.m3_mockingbird_plays import _trigger

    parent = rules.get(state, child.bonded_source)
    if (
        parent.learned_source is not None
        or parent.changeling_source is not None
        or parent.target is None
        or child.learned_sex_source is not None
        or child.learned_source is not None
        or child.changeling_source is not None
        or child.play != "mockingbird_sex"
        or child.actor != parent.actor
        or child.action != action["id"]
        or not child.parties
        or len({x.actor for x in child.parties}) != len(child.parties)
        or any(
            x.actor == child.actor
            or not any(
                r.actor == x.actor and r.controller == x.controller for r in parent.cast.roles
            )
            for x in child.parties
        )
        or child.parties[0].actor != parent.target
        or meta.get("bonded_source") != parent.id
        or meta.get("learned_sex_source") is not None
        or meta.get("learned_source") is not None
        or meta.get("parties") != [x.model_dump(mode="json") for x in child.parties]
        or meta.get("trigger") != child.id
        or action["data"].get("prepared", {}).get("source_work") != child.id
    ):
        raise WorkflowError("Use the actual native Pair-rule child, not a copied entitlement")
    prove_delegation(
        game,
        c,
        state,
        parent.id,
        child.id,
        parent.actor,
        parent.target,
        "girl.mockingbird.sex-play",
    )
    beginnings = c.execute(
        sa.select(t.events.c.id, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.play_confirmed",
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
        )
    ).all()
    if len(beginnings) != 1 or beginnings[0].actor_id != parent.actor.entity:
        raise WorkflowError("Recover the original native child's canonical Action birth")
    bound = _trigger(_history(c, game, beginnings[0].id), child.id)
    if (
        bound.action != action["id"]
        or bound.state != "ready"
        or bound.parties != child.parties
        or bound.bonded_source != parent.id
    ):
        raise WorkflowError("Preserve the actual original native child binding")
    birth = _trigger(_history(c, game, child.source_event), child.id)
    if (
        birth.state != "proposed"
        or birth.action is not None
        or [(x.actor, x.controller) for x in birth.parties]
        != [(x.actor, x.controller) for x in child.parties]
        or any(x.decision != "pending" or x.event is not None for x in birth.parties)
        or child.parties[0].controller != parent.controllers.get(parent.target.token)
    ):
        raise WorkflowError("Preserve the original group declaration and primary counterpart")
    final_answer = False
    for party in child.parties:
        if party.decision != "accepted" or party.event is None:
            raise WorkflowError("Every actual child counterpart must independently consent")
        response = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == party.event,
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(response["payload_json"]) if response else {}
        answered = _trigger(_history(c, game, party.event), child.id)
        if (
            response is None
            or response["kind"] != "m3.mockingbird_trigger_attested"
            or response["actor_id"] != str(party.controller)
            or payload.get("trigger") != child.id
            or payload.get("accept") is not True
            or payload.get("party") != party.actor.model_dump(mode="json")
            or party not in answered.parties
            or [(x.actor, x.controller) for x in answered.parties]
            != [(x.actor, x.controller) for x in birth.parties]
            or any(x.decision not in ("pending", "accepted") for x in answered.parties)
            or any(x.decision == "accepted" and x not in child.parties for x in answered.parties)
            or any(
                getattr(answered, k) != getattr(birth, k)
                for k in (
                    "actor",
                    "play",
                    "scene",
                    "channel",
                    "cast_sha256",
                    "source_event",
                    "account",
                    "bonded_source",
                    "learned_source",
                    "learned_sex_source",
                    "changeling_source",
                )
            )
            or answered.state
            != ("ready" if all(x.decision == "accepted" for x in answered.parties) else "proposed")
            or answered.action is not None
            or child.action is None
        ):
            raise WorkflowError(
                "Preserve each child's actual independent confirmation before its Action"
            )
        final_answer = final_answer or answered.parties == child.parties
    if not final_answer:
        raise WorkflowError("Recover the final all-participant acceptance before the Action")
    _roll_source(game, c, action)
    return True
