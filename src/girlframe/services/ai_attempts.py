"""Campaign-wide budget reservations for durable provider attempts."""

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.briefing import BriefingPolicy
from girlframe.database import tables as t
from girlframe.services import campaign_time_history as calendar
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

BRIEFING_RESERVATION = "ai.mission_briefing_reserved"
REACTION_RESERVATION = "ai.npc_reaction_reserved"
ATTEMPT_SECONDS = 120


def reserve_attempt(
    c: Connection,
    store: OnboardingStore,
    viewer: GuildViewer,
    identity: str,
    policy: BriefingPolicy,
    *,
    kind: str,
    key: str,
    prompt_version: str,
) -> str:
    now = int(store.clock())
    cost = sa.func.json_extract(t.events.c.payload_json, "$.reserved_microusd")
    started = sa.func.json_extract(t.events.c.payload_json, "$.reserved_at")
    hour = now - 3600
    day = now - 86400
    hourly, daily = c.execute(
        calendar.query(store.campaign_id, BRIEFING_RESERVATION, REACTION_RESERVATION)
        .with_only_columns(
            sa.func.coalesce(sa.func.sum(sa.case((started > hour, cost), else_=0)), 0),
            sa.func.coalesce(sa.func.sum(cost), 0),
        )
        .where(started > day)
    ).one()
    budgets = [
        configured
        for configured in (store.policy.ai_mission_briefing, store.policy.ai_npc_reactions)
        if configured is not None
    ]
    reserve = policy.reserved_microusd_per_call
    if hourly + reserve > min(
        item.hourly_budget_microusd for item in budgets
    ) or daily + reserve > min(item.daily_budget_microusd for item in budgets):
        raise WorkflowError(
            "AI_BUDGET_EXCEEDED: wait for the campaign AI budget or continue manually."
        )
    return store._audit(
        c,
        viewer.user_id,
        key,
        kind,
        {
            "request_id": identity,
            "reserved_at": now,
            "expires_at": now + ATTEMPT_SECONDS,
            "reserved_microusd": reserve,
            "model": policy.model,
        },
        ruleset_version=prompt_version,
    )
