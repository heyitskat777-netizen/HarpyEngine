"""Read the approved opening and enforce its settings at the existing writers."""

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.campaign_opening import (
    DEFAULT_DIFFICULTY,
    RESTRICTED_PUNISHMENTS,
    Difficulty,
    Opening,
)
from girlframe.engine.m2 import GameState
from girlframe.services import campaign_time_history as calendar
from girlframe.services.onboarding import WorkflowError

EVENT = "campaign.opening"
LETHAL_ENDINGS = frozenset({"death", "execution"})


def opening(c: Connection, campaign: str) -> Opening | None:
    raw = c.scalar(
        calendar.query(campaign, EVENT)
        .with_only_columns(t.events.c.payload_json)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    return Opening.model_validate_json(raw) if raw is not None else None


def difficulty(c: Connection, campaign: str) -> Difficulty:
    value = opening(c, campaign)
    return value.difficulty if value is not None else DEFAULT_DIFFICULTY


def require_consequence(c: Connection, campaign: str, kind: str) -> None:
    if (kind in RESTRICTED_PUNISHMENTS or kind == "death") and difficulty(
        c, campaign
    ) == "narrative":
        raise WorkflowError(
            "NARRATIVE_LIMIT: choose a supported nonlethal consequence or seek a Handler ruling."
        )


def guard_transition(
    c: Connection, campaign: str, before: GameState, after: GameState, event_kind: str
) -> None:
    old_careers = {x.id for x in before.career_archives}
    old_handlers = {x.id for x in before.handler_archives}
    if (
        any(x.id not in old_careers and x.ending in LETHAL_ENDINGS for x in after.career_archives)
        or any(x.id not in old_handlers and x.ending == "death" for x in after.handler_archives)
        or harpy_death(before, after)
    ):
        require_consequence(c, campaign, "death")
    elif event_kind == "m3.reign_prisoner_executed":
        require_consequence(c, campaign, "execution")
    elif event_kind == "m3.lobotomy_started":
        require_consequence(c, campaign, "lobotomization")


def harpy_death(before: GameState, after: GameState) -> bool:
    living_originals = {x.id for x in before.harpy_states if x.alive}
    if any(x.id in living_originals and not x.alive for x in after.harpy_states):
        return True
    if not before.world or not after.world or not before.native_harpies:
        return False
    owned = {x.id for x in before.native_harpies}
    living = {x.id for x in before.world.pilots if x.alive and x.id in owned}
    return any(x.id in living and not x.alive for x in after.world.pilots)


def initial_mission_needed(c: Connection, campaign: str) -> bool:
    table = t.m3["m3_missions"]
    return (
        c.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == campaign,
                table.c.phase == "complete",
                sa.func.json_extract(table.c.body_json, "$.introductory") == 1,
            )
            .limit(1)
        )
        is None
    )


def briefing(
    c: Connection, campaign: str, players: tuple[int, ...], hard_stake: str | None
) -> tuple[bool, str | None]:
    applied = opening(c, campaign)
    if applied is None:
        if hard_stake is not None:
            raise WorkflowError("Extra Hard-mode stakes require a Hard campaign.")
        return False, None
    if initial_mission_needed(c, campaign):
        if not set(players) <= set(applied.audience):
            raise WorkflowError("Invite introductory Pilots from the Session Zero group.")
        anchor = calendar.anchor(c, campaign)
        if anchor is None or anchor[1].position.day < applied.first_mission_day:
            raise WorkflowError(
                "Use the opening roleplay days first. "
                f"The first mission starts on Day {applied.first_mission_day}."
            )
        table = t.m3["m3_missions"]
        if c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == campaign, table.c.phase.not_in(("complete", "cancelled")))
            .limit(1)
        ):
            raise WorkflowError("Finish the introductory mission before offering another.")
        if hard_stake is not None:
            raise WorkflowError("Give the introductory mission one simple objective.")
        return True, None
    if applied.difficulty == "hard":
        if hard_stake is None or not hard_stake.strip() or len(hard_stake) > 300:
            raise WorkflowError("Describe an extra obstacle for the Hard-mode mission briefing.")
        return False, hard_stake.strip()
    if hard_stake is not None:
        raise WorkflowError("Extra Hard-mode stakes require a Hard campaign.")
    return False, None


def historical_mission(c: Connection, campaign: str) -> bool:
    table = t.m3["m3_missions"]
    return (
        c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == campaign, table.c.phase != "cancelled")
            .limit(1)
        )
        is not None
    )
