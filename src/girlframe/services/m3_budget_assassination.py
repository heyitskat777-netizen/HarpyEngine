"""Actual future mission binding and proved original-target death before rewards."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_assassination as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_missions import Mission
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def proof(
    c: Connection, store: OnboardingStore, state: GameState, identity: str
) -> rules.Assignment:
    value = rules.get(state, identity)
    source = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == store.campaign_id, t.events.c.id == value.source_event
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    original = rules.get(GameState.model_validate_json(raw), identity) if raw else None
    if (
        source is None
        or original is None
        or source["kind"] != "m3.strain_effect_applied"
        or source["actor_id"] != value.handler.entity
        or json.loads(source["payload_json"]).get("rule_id") != rules.RULE
        or json.loads(source["payload_json"]).get("work_id") != value.source_work
        or any(
            getattr(original, k) != getattr(value, k)
            for k in (
                "id",
                "source_work",
                "source_event",
                "period",
                "handler",
                "target",
                "people",
                "account",
            )
        )
    ):
        raise WorkflowError("Recover the original political target and actual assignment source")
    return value


def bind(
    c: Connection, store: OnboardingStore, state: GameState, identity: str, mission: Mission
) -> None:
    value = proof(c, store, state, identity)
    current = tuple(sorted((str(uid), state.sheets[str(uid)].character_id) for uid in state.order))
    original = tuple(sorted((x.entity, x.incarnation) for x in value.people))
    if (
        value.phase != "pending"
        or not same_handler_body(state, value.handler)
        or mission.handler != int(value.handler.entity)
        or current != original
        or set(mission.offered_to) != {int(x.entity) for x in value.people}
    ):
        raise WorkflowError(
            "Offer this actual assignment to the original current Cadre under its original Handler"
        )
    target = resolve(state, value.target, ())
    if not mission.objective.startswith("Assassinate " + target.label + "."):
        raise WorkflowError("Preserve this actual mission's political target objective")
    rules.put(
        state,
        value.model_copy(
            update=dict(phase="mission", mission=mission.id, attempts=(*value.attempts, mission.id))
        ),
    )


def death(c: Connection, store: OnboardingStore, state: GameState, value: rules.Assignment) -> str:
    from girlframe.services.m3_battle_npc import NpcDamageService

    npc = (
        next((x for x in state.world.npcs if x.id == value.target.entity), None)
        if state.world
        else None
    )
    if npc is None or npc.alive:
        raise WorkflowError(
            "The actual political target is still alive; this assignment cannot claim success"
        )
    history = t.m3["m3_mission_history"]
    started = c.scalar(
        sa.select(t.events.c.seq)
        .join(
            history,
            sa.and_(
                history.c.campaign_id == t.events.c.campaign_id,
                history.c.event_id == t.events.c.id,
            ),
        )
        .where(
            history.c.campaign_id == store.campaign_id,
            history.c.id == value.mission,
            t.events.c.kind == "m3.mission_started",
        )
        .order_by(t.events.c.seq)
        .limit(1)
    )
    if started is None:
        raise WorkflowError("Recover the actual assassination mission dispatch")
    for fact in reversed(state.facts):
        if (
            fact.get("kind") != "npc_asset_replacement"
            or fact.get("effect") != "kill"
            or fact.get("target") != value.target.model_dump_json()
        ):
            continue
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == store.campaign_id, t.events.c.id == fact["event"]
                )
            )
            .mappings()
            .first()
        )
        if (
            source is None
            or source["kind"] != "m3.npc_damage_applied"
            or source["seq"] <= started
            or json.loads(source["payload_json"]).get("effect") != "kill"
            or json.loads(source["payload_json"]).get("work_id") != fact.get("work")
        ):
            continue
        damage = NpcDamageService(store)
        row = damage._row(c, fact["work"])
        target, _ = damage._proof(c, row)
        if target == value.target and row["state"] == "resolved":
            return str(source["id"])
    raise WorkflowError(
        "SOURCE_PORT_REQUIRED: prove the original politician's actual in-mission death source"
    )


def before_rewards(
    c: Connection, store: OnboardingStore, state: GameState, mission: Mission, success: bool
) -> None:
    if not success:
        return
    for value in rules.assignments(state):
        if value.mission == mission.id and value.phase == "mission":
            value = proof(c, store, state, value.id)
            death(c, store, state, value)


def finish(
    c: Connection, store: OnboardingStore, state: GameState, mission: Mission, event: str
) -> bool:
    changed = False
    for value in rules.assignments(state):
        if value.mission != mission.id or value.phase != "mission":
            continue
        value = proof(c, store, state, value.id)
        if mission.phase == "cancelled" or mission.phase == "complete" and not mission.success:
            rules.put(state, value.model_copy(update=dict(phase="pending", mission=None)))
        elif mission.phase == "complete" and mission.success:
            actual_death = death(c, store, state, value)
            rules.put(
                state,
                value.model_copy(
                    update=dict(phase="complete", death_event=actual_death, completed_event=event)
                ),
            )
        else:
            continue
        changed = True
    return changed


def resolve_completed(c: Connection, store: OnboardingStore, state: GameState, event: str) -> None:
    for value in rules.assignments(state):
        if value.completed_event != event:
            continue
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == store.campaign_id, work.c.id == value.id)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        if row["state"] != "pending":
            raise WorkflowError("Recover the original pending assassination assignment")
        c.execute(
            work.insert().values(
                **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                revision=row["revision"] + 1,
                state="resolved",
                event_id=event,
            )
        )


class AssassinationService:
    def __init__(self, store: OnboardingStore):
        self.store = store

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.assignments(state)
            if x.phase != "complete"
            and int(x.handler.entity) == viewer.user_id
            and same_handler_body(state, x.handler)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = proof(c, self.store, state, identity)
            if viewer.user_id != int(value.handler.entity) or not same_handler_body(
                state, value.handler
            ):
                raise WorkflowError("Only the original Handler opens this political assignment")
            npc = (
                next((x for x in state.world.npcs if x.id == value.target.entity), None)
                if state.world
                else None
            )
            if npc is None:
                raise WorkflowError("Recover the actual political target")
            return dict(
                id=identity,
                phase=value.phase,
                mission=value.mission,
                target=npc.name,
                players=tuple(int(x.entity) for x in value.people),
                objective=("Assassinate " + npc.name + ". " + value.account[:800])[:1200],
            )
