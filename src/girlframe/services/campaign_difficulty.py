"""Read the approved opening and enforce its settings at the existing writers."""

import json

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
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.services import campaign_time_history as calendar
from girlframe.services.onboarding import OnboardingStore, WorkflowError

EVENT = "campaign.opening"
DEATH_USED = "campaign.narrative_death_used"
LETHAL_ENDINGS = frozenset({"death", "execution"})


def opening(c: Connection, campaign: str) -> Opening | None:
    raw = c.scalar(
        calendar.query(campaign, EVENT)
        .with_only_columns(t.events.c.payload_json)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    return Opening.model_validate_json(raw) if raw is not None else None


def review_facilitator(c: Connection, campaign: str, fallback: int | None = None) -> int | None:
    record = opening(c, campaign)
    return record.facilitator if record is not None and record.facilitator is not None else fallback


def difficulty(c: Connection, campaign: str) -> Difficulty:
    value = opening(c, campaign)
    return value.difficulty if value is not None else DEFAULT_DIFFICULTY


def require_consequence(c: Connection, campaign: str, kind: str) -> None:
    if kind in RESTRICTED_PUNISHMENTS and difficulty(c, campaign) == "narrative":
        raise WorkflowError("NARRATIVE_LIMIT: choose a supported alternative punishment.")


def narrative_death_available(c: Connection, campaign: str, state: GameState) -> bool:
    # Earlier genuine deaths also count if Narrative was selected after legacy play.
    if (
        any(x.ending in LETHAL_ENDINGS for x in state.career_archives)
        or any(x.ending == "death" for x in state.handler_archives)
        or any(not x.alive for x in state.harpy_states)
    ):
        return False
    if state.world is not None and state.native_harpies:
        harpies = {x.id for x in state.native_harpies}
        if any(x.id in harpies and not x.alive for x in state.world.pilots):
            return False
    return (
        c.scalar(calendar.query(campaign, DEATH_USED).with_only_columns(t.events.c.id).limit(1))
        is None
    )


def _confirmed_defeat(
    c: Connection,
    campaign: str,
    archive: CareerArchive,
    actor: int | str,
    event: str,
    action_id: str | None,
    choice_id: str | None,
) -> bool:
    if (
        archive.ending != "death"
        or archive.source_event != event
        or archive.actor.kind != "pilot"
        or archive.actor.entity != str(actor)
        or action_id is None
        or choice_id is None
    ):
        return False
    actions, choices = t.m2["m2_actions"], t.m2["m2_choices"]
    raw = c.scalar(
        sa.select(actions.c.body_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == actions.c.campaign_id,
                choices.c.action_id == actions.c.id,
            ),
        )
        .where(
            actions.c.campaign_id == campaign,
            actions.c.id == action_id,
            actions.c.actor_id == str(actor),
            choices.c.id == choice_id,
            choices.c.actor_id == str(actor),
            choices.c.kind == "defeat_select",
            choices.c.state == "answered",
        )
    )
    if raw is None:
        return False
    data = json.loads(raw)
    choice = data.get("choices", {}).get(f"defeat_select:{actor}", {})
    return (
        data.get("play") == "defeat"
        and data.get("result", {}).get("tier") == "low"
        and data.get("response_event") == event
        and data.get("defeat", {}).get("actor") == archive.actor.model_dump(mode="json")
        and choice.get("options") == ["death"]
        and choice.get("flag") is True
    )


def guard_transition(
    c: Connection,
    store: OnboardingStore,
    before: GameState,
    after: GameState,
    event_kind: str,
    event: str,
    actor: int | str,
    *,
    action_id: str | None,
    choice_id: str | None,
) -> None:
    campaign = store.campaign_id
    if event_kind == "m3.reign_prisoner_executed":
        require_consequence(c, campaign, "execution")
    elif event_kind == "m3.lobotomy_started":
        require_consequence(c, campaign, "lobotomization")

    old_careers = {x.id for x in before.career_archives}
    deaths = [
        x for x in after.career_archives if x.id not in old_careers and x.ending in LETHAL_ENDINGS
    ]
    old_handlers = {x.id for x in before.handler_archives}
    other_death = any(
        x.id not in old_handlers and x.ending == "death" for x in after.handler_archives
    ) or harpy_death(before, after)
    if not (deaths or other_death) or difficulty(c, campaign) != "narrative":
        return
    if not narrative_death_available(c, campaign, before):
        raise WorkflowError("NARRATIVE_LIMIT: this campaign has already recorded its one death.")
    if (
        other_death
        or len(deaths) != 1
        or event_kind != "m3.choice_resolved"
        or not _confirmed_defeat(c, campaign, deaths[0], actor, event, action_id, choice_id)
    ):
        raise WorkflowError(
            "NARRATIVE_LIMIT: choose a supported nonlethal consequence or seek a Handler ruling."
        )
    store._audit(
        c,
        actor,
        "narrative-death:" + event,
        DEATH_USED,
        {"death_event": event, "archive": deaths[0].id, "action": action_id, "choice": choice_id},
        ruleset_version="narrative-v1",
    )


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
        if session_zero_pending(c, campaign):
            raise WorkflowError("Complete Session Zero before offering the first mission.")
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


def session_zero_pending(c: Connection, campaign: str) -> bool:
    from girlframe.services.session_zero import EVENT as SESSION_ZERO_SAVED

    started = c.scalar(
        calendar.query(campaign, SESSION_ZERO_SAVED).with_only_columns(t.events.c.id).limit(1)
    )
    return started is not None and not historical_mission(c, campaign)
