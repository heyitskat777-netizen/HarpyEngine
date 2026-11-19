"""Current Off-Duty upkeep is adjudicated privately by the appointed human GM."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_princess_npc_orders as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_standards import RULE, labels
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.princess_off_duty_upkeep_reviewed"


def period_for(game: GameService, c: Connection, identity: str) -> Period | None:
    table = t.m3["m3_off_duty"]
    raw = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == identity,
        )
    )
    return Period.model_validate_json(raw) if raw else None


def _standards(state: GameState, period: Period, girl: ActorRef) -> str | None:
    sheet = state.sheets.get(girl.entity)
    if (
        period.phase != "active"
        or girl.kind != "pilot"
        or sheet is None
        or sheet.character_id != girl.incarnation
        or period.character_ids.get(girl.entity) != girl.incarnation
        or girl.entity in period.ended_characters
        or sheet.owner not in state.order
    ):
        return None
    return rules.standards_hash(sheet)


def authority(
    game: GameService,
    c: Connection,
    state: GameState,
    girl: ActorRef,
    *,
    event: str | None = None,
    active: bool = True,
) -> rules.Upkeep | None:
    value = rules.latest(state, girl)
    if (
        value is None
        or value.girl != girl
        or not value.approved
        or (event is not None and value.event != event)
    ):
        return None
    current = period_for(game, c, value.period)
    if active and (
        current is None
        or _standards(state, current, girl) != value.standards
        or (value.gm, value.appointment) != MedicalService(game.store)._handler(c)
    ):
        return None
    history, periods = t.m2["m2_state_history"], t.m3["m3_off_duty_history"]
    born = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == value.event,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == EVENT,
            t.events.c.actor_id == str(value.gm),
        )
    )
    original_period = c.scalar(
        sa.select(periods.c.body_json).where(
            periods.c.campaign_id == game.store.campaign_id,
            periods.c.id == value.period,
            periods.c.revision == value.period_revision,
        )
    )
    if born is None or original_period is None:
        raise WorkflowError("Recover the original GM's upkeep review for this Off-Duty period")
    original, at_review = (
        GameState.model_validate_json(born),
        Period.model_validate_json(original_period),
    )
    if (
        rules.latest(original, girl, value.period) != value
        or at_review.handler != value.gm
        or _standards(original, at_review, girl) != value.standards
    ):
        raise WorkflowError("Recover the three original standards and actual upkeep review")
    return value


def review_candidates(
    game: GameService, c: Connection, state: GameState, period: Period, viewer: GuildViewer
) -> dict[str, Any]:
    if viewer.user_id != period.handler or period.phase != "active":
        return {}
    access = Access(game.store)
    try:
        access.authorize(c, viewer, "plays", director_response=True)
        assert access.registry is not None
        access.registry.require_available(RULE)
        if MedicalService(game.store)._handler(c)[0] != viewer.user_id:
            return {}
    except (ValueError, WorkflowError):
        return {}
    return {
        uid: dict(name=state.sheets[uid].callsign, standards=labels(state.sheets[uid]))
        for uid, inc in period.character_ids.items()
        if _standards(state, period, ActorRef(kind="pilot", entity=uid, incarnation=inc))
        is not None
    }


def review(
    periods: OffDutyService,
    viewer: GuildViewer,
    key: str,
    identity: str,
    revision: int,
    expected: int,
    recipient: int,
    upheld: tuple[rules.Standard, ...],
    account: str,
) -> dict[str, Any]:
    game = periods.game

    def authorize(c: Connection) -> None:
        Access(game.store).authorize(c, viewer, "plays", director_response=True)
        game.unpaused(c)
        if MedicalService(game.store)._handler(c)[0] != viewer.user_id:
            raise WorkflowError("Only the appointed human GM reviews current standards")

    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.services.m3_handler_plays import _ordinary_scene_idle

        _ordinary_scene_idle(c, game)
        period = periods._get(c, identity)
        state = load_state(c, game.store.campaign_id)
        if (
            period.revision != revision
            or state.revision != expected
            or str(recipient) not in review_candidates(game, c, state, period, viewer)
            or len(set(upheld)) != len(upheld)
            or not set(upheld) <= rules.ALL_STANDARDS
            or not 0 < len(account.strip()) <= 1200
        ):
            raise WorkflowError("Review the three actual standards in the current Off-Duty period")
        girl = current_ref(state, recipient)
        standards = _standards(state, period, girl)
        assert standards is not None
        gm, appointment = MedicalService(game.store)._handler(c)
        event = str(uuid4())
        value = rules.Upkeep(
            girl=girl,
            period=period.id,
            period_revision=period.revision,
            standards=standards,
            gm=gm,
            appointment=appointment,
            upheld=upheld,
            account=account.strip(),
            event=event,
        )
        rules.save(state, value)
        game.event(c, viewer.user_id, key, EVENT, state, event_id=event, period_id=period.id)
        return dict(event=event, approved=value.approved)

    return game.store._write(
        viewer,
        key,
        EVENT,
        dict(
            period=identity,
            revision=revision,
            expected=expected,
            recipient=recipient,
            upheld=upheld,
            account=account,
        ),
        operation,
        auto_audit=False,
        authorize=authorize,
    )
