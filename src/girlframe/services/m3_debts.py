"""Bridge real saved M2 discipline debts to one actual Off-Duty context."""

import json

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_off_duty import Period
from girlframe.services.onboarding import OnboardingStore


def synchronize(c: Connection, store: OnboardingStore, state: GameState, event: str) -> None:
    if store.policy.m3_approval is None:
        return
    table = t.m3["m3_off_duty"]
    body = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == store.campaign_id, table.c.phase != "complete"
        )
    )
    if body is None:
        return
    period = Period.model_validate_json(body)
    from girlframe.services.m3_frame_rewards import synchronize as frame_rewards

    frame_rewards(c, store, state, period, event)
    work = t.m3["m3_required_work"]
    for debt in state.obligations:
        if debt.kind != "punishment" or debt.state != "pending" or debt.owner not in period.pilots:
            continue
        if debt.details.get("after_period") == period.id:
            continue
        if debt.details.get("mission"):
            continue
        character = debt.details.get("character_id")
        if (
            character
            and c.scalar(
                sa.select(t.characters.c.id).where(
                    t.characters.c.campaign_id == store.campaign_id,
                    t.characters.c.user_id == str(debt.owner),
                )
            )
            != character
        ):
            continue
        identity = period.id + ":m2-punishment:" + debt.id
        if c.scalar(
            sa.select(work.c.id)
            .where(
                work.c.campaign_id == store.campaign_id,
                sa.or_(
                    work.c.id == identity,
                    sa.func.json_extract(work.c.body_json, "$.obligation_id") == debt.id,
                ),
            )
            .limit(1)
        ):
            continue
        c.execute(
            work.insert().values(
                campaign_id=store.campaign_id,
                id=identity,
                revision=1,
                mission_id=None,
                off_duty_id=period.id,
                owner_id=str(period.handler),
                subject_id=str(debt.owner),
                kind="punishment",
                state="pending",
                event_id=event,
                body_json=json.dumps(
                    {
                        "reason": "m2_play",
                        "obligation_id": debt.id,
                        "source_action": debt.action,
                        "source_pdf": int(debt.details.get("source_pdf", "27")),
                        "cause": debt.details.get("cause", "m2_play"),
                        "due_stage": "active",
                    },
                    sort_keys=True,
                ),
            )
        )
