"""Bridge real saved M2 discipline debts to one actual Off-Duty context."""

import json

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_missions import Mission
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
        if debt.details.get("mission") or debt.details.get("cause") == "defeat":
            continue
        character = debt.details.get("character_id")
        if character and (
            str(debt.owner) not in state.sheets
            or state.sheets[str(debt.owner)].character_id != character
            or period.character_ids.get(str(debt.owner)) != character
            or str(debt.owner) in period.ended_characters
        ):
            continue
        identity = period.id + ":m2-punishment:" + debt.id
        if _already_bound(c, store, state, debt.id, debt.owner, identity):
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
                        "character": character or state.sheets[str(debt.owner)].character_id,
                    },
                    sort_keys=True,
                ),
            )
        )


def _already_bound(
    c: Connection,
    store: OnboardingStore,
    state: GameState,
    obligation: str,
    owner: int,
    identity: str,
) -> bool:
    table = t.m3["m3_required_work"]
    rows = c.execute(
        sa.select(table)
        .where(
            table.c.campaign_id == store.campaign_id,
            sa.or_(
                table.c.id == identity,
                sa.func.json_extract(table.c.body_json, "$.obligation_id") == obligation,
            ),
        )
        .order_by(table.c.revision)
    ).mappings()
    latest = {row["id"]: dict(row) for row in rows}
    if not latest:
        return False
    if identity in latest or any(x["state"] != "resolved" for x in latest.values()):
        return True
    if any(
        json.loads(x["body_json"]).get("resolution") != "original_character_career_ended"
        for x in latest.values()
    ):
        return True
    character = state.sheets[str(owner)].character_id
    returned = any(
        ticket.state == "returned"
        and ticket.owner == owner
        and any(
            a.id == ticket.archive and a.actor.incarnation == character
            for a in state.career_archives
        )
        for ticket in state.career_returns
    )
    return not returned


def bind_mission(state: GameState, mission: Mission) -> None:
    """A Defeat debt comes due after an actual mission of that original character."""
    for debt in state.obligations:
        character = debt.details.get("character_id")
        sheet = state.sheets.get(str(debt.owner))
        if (
            debt.kind == "punishment"
            and debt.state == "pending"
            and debt.details.get("cause") == "defeat"
            and not debt.details.get("mission")
            and sheet is not None
            and character == sheet.character_id
            and mission.character_ids.get(str(debt.owner)) == character
        ):
            debt.details["mission"] = mission.id


def synchronize_mission(
    c: Connection, store: OnboardingStore, state: GameState, mission: Mission, event: str
) -> None:
    from girlframe.services.m3_work import related

    for debt in state.obligations:
        if (
            debt.kind != "punishment"
            or debt.state != "pending"
            or debt.details.get("cause") != "defeat"
            or debt.details.get("mission") != mission.id
        ):
            continue
        identity = mission.id + ":defeat-punishment:" + debt.id
        if _already_bound(c, store, state, debt.id, debt.owner, identity):
            continue
        related(
            c,
            store,
            dict(campaign_id=store.campaign_id, mission_id=mission.id),
            identity,
            mission.handler,
            debt.owner,
            "punishment",
            dict(
                reason="defeat_post_mission",
                obligation_id=debt.id,
                source_action=debt.action,
                source_pdf=29,
                character=debt.details["character_id"],
            ),
            event,
        )
