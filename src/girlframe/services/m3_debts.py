"""Bridge real saved M2 discipline debts to one actual Off-Duty context."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_intracadre_marriage import Allocation, allocation_fields, records
from girlframe.engine.m3_missions import Mission
from girlframe.engine.m3_off_duty import Period
from girlframe.services.onboarding import OnboardingStore, WorkflowError

MISSION_CAUSES = {"mission_failure", "dog_mission_end", "defeat_post_mission"}


def _first(c: Connection, store: OnboardingStore, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision)
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("SOURCE_MISSION_DEBT_MISSING: recover the original discipline work.")
    return dict(row)


def _latest(c: Connection, store: OnboardingStore) -> dict[str, dict[str, Any]]:
    table = t.m3["m3_required_work"]
    return {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(table)
            .where(table.c.campaign_id == store.campaign_id)
            .order_by(table.c.revision)
        ).mappings()
    }


def _returned_missions(
    c: Connection, store: OnboardingStore, state: GameState, period: Period, event: str
) -> None:
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_careers import work_subject_character
    from girlframe.services.m3_returned_work import proof
    from girlframe.services.m3_work import related

    latest = _latest(c, store)
    missions = t.m3["m3_missions"]
    for source in latest.values():
        body = json.loads(str(source["body_json"]))
        if (
            source["kind"] != "punishment"
            or not source["mission_id"]
            or body.get("reason") not in MISSION_CAUSES
            or str(source["subject_id"]) in period.ended_characters
        ):
            continue
        uid = int(str(source["subject_id"]))
        character = work_subject_character(c, GameService(store), source)
        if period.character_ids.get(str(uid)) != character:
            continue
        raw_mission = c.scalar(
            sa.select(missions.c.body_json).where(
                missions.c.campaign_id == store.campaign_id,
                missions.c.id == source["mission_id"],
                missions.c.phase == "complete",
            )
        )
        mission = Mission.model_validate_json(raw_mission) if raw_mission else None
        if mission is None or mission.character_ids.get(str(uid)) != character:
            continue
        obligation = body.get("obligation_id")
        if obligation and not any(
            x.id == obligation and x.owner == uid and x.state == "pending"
            for x in state.obligations
        ):
            continue
        lineage = [
            row
            for row in latest.values()
            if json.loads(str(row["body_json"])).get("return_source_work") == source["id"]
        ]
        if any(
            row["state"] != "resolved"
            or json.loads(str(row["body_json"])).get("resolution")
            != "original_character_career_ended"
            for row in lineage
        ):
            continue
        closed = lineage[-1] if lineage else source
        returned = proof(c, store, state, closed, uid, character)
        if returned is None:
            continue
        identity = period.id + ":returned-mission:" + str(source["id"])
        if identity in latest:
            continue
        related(
            c,
            store,
            dict(campaign_id=store.campaign_id, off_duty_id=period.id),
            identity,
            period.handler,
            uid,
            "punishment",
            json.loads(_first(c, store, source["id"])["body_json"])
            | dict(
                character=character,
                original_mission=source["mission_id"],
                return_source_work=source["id"],
                return_proof=returned,
                due_stage="active",
            ),
            event,
        )


def check_returned(c: Connection, store: OnboardingStore, row: dict[str, Any]) -> None:
    """Recheck original cause, current period and actual return before discipline."""
    from girlframe.services.m2_game import GameService
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_careers import work_subject_character
    from girlframe.services.m3_returned_work import proof

    body = json.loads(row["body_json"])
    if not body.get("return_source_work"):
        return
    source = _first(c, store, body["return_source_work"])
    original = json.loads(source["body_json"])
    created = json.loads(_first(c, store, row["id"])["body_json"])
    returned = body.get("return_proof")
    latest = _latest(c, store)
    prior = latest.get(returned.get("closed_work", "")) if isinstance(returned, dict) else None
    character = work_subject_character(c, GameService(store), source)
    table = t.m3["m3_missions"]
    mission_raw = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == store.campaign_id,
            table.c.id == source["mission_id"],
            table.c.phase == "complete",
        )
    )
    mission = Mission.model_validate_json(mission_raw) if mission_raw else None
    periods = t.m3["m3_off_duty"]
    period_raw = c.scalar(
        sa.select(periods.c.body_json).where(
            periods.c.campaign_id == store.campaign_id, periods.c.id == row["off_duty_id"]
        )
    )
    period = Period.model_validate_json(period_raw) if period_raw else None
    if (
        source["kind"] != "punishment"
        or original.get("reason") not in MISSION_CAUSES
        or body.get("reason") != original["reason"]
        or row["mission_id"] is not None
        or mission is None
        or period is None
        or period.character_ids.get(row["subject_id"]) != character
        or row["subject_id"] in period.ended_characters
        or row["owner_id"] != str(period.handler)
        or mission.character_ids.get(row["subject_id"]) != character
        or source["subject_id"] != row["subject_id"]
        or body.get("character") != character
        or body.get("original_mission") != source["mission_id"]
        or row["id"] != period.id + ":returned-mission:" + source["id"]
        or any(
            body.get(k) != created.get(k)
            for k in (
                "return_proof",
                "return_source_work",
                "original_mission",
                "character",
                "reason",
                "obligation_id",
                "source_action",
            )
        )
        or prior is None
        or not (
            prior["id"] == source["id"]
            or json.loads(prior["body_json"]).get("return_source_work") == source["id"]
        )
        or proof(
            c, store, load_state(c, store.campaign_id), prior, int(row["subject_id"]), character
        )
        != returned
    ):
        raise WorkflowError(
            "SOURCE_MISSION_DEBT_MISSING: reopen the actual returned-original cause."
        )


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
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_show_dog import synchronize as show_dog

    show_dog(GameService(store), c, state, period, event)
    _returned_missions(c, store, state, period, event)
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
        allocation = next((x for x in records(state, Allocation) if x.source_id == debt.id), None)
        subject = int(allocation.subject.entity) if allocation else debt.owner
        actual_character = (
            allocation.subject.incarnation
            if allocation
            else character or state.sheets[str(debt.owner)].character_id
        )
        c.execute(
            work.insert().values(
                campaign_id=store.campaign_id,
                id=identity,
                revision=1,
                mission_id=None,
                off_duty_id=period.id,
                owner_id=str(period.handler),
                subject_id=str(subject),
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
                        "character": actual_character,
                        **allocation_fields(state, debt.id),
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
    from girlframe.services.m3_returned_work import proof

    character = state.sheets[str(owner)].character_id
    return character is None or not any(
        proof(c, store, state, closed, owner, character) is not None for closed in latest.values()
    )


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
        allocation = next((x for x in records(state, Allocation) if x.source_id == debt.id), None)
        subject = int(allocation.subject.entity) if allocation else debt.owner
        actual_character = (
            allocation.subject.incarnation if allocation else debt.details["character_id"]
        )
        related(
            c,
            store,
            dict(campaign_id=store.campaign_id, mission_id=mission.id),
            identity,
            mission.handler,
            subject,
            "punishment",
            dict(
                reason="defeat_post_mission",
                obligation_id=debt.id,
                source_action=debt.action,
                source_pdf=29,
                character=actual_character,
                **allocation_fields(state, debt.id),
            ),
            event,
        )
