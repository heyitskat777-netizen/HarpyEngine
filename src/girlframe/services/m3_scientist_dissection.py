"""Complete an original lab dissection and prove its real Session advancement."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_scientist_dissection as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Gorgon
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_advancements import (
    HandlerAdvancementService,
    _appointment_at,
    _history,
)
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService, _session
from girlframe.services.m3_scientist_private_scene import lab_at
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.scientist_dissection_awarded"


def death(game: GameService, c: Connection, specimen: Gorgon) -> str | None:
    if specimen.alive or not specimen.exposed:
        return None
    history = t.m2["m2_state_history"]
    gorgons = sa.func.json_each(history.c.body_json, "$.world.gorgons").table_valued("value")
    found = c.execute(
        sa.select(history.c.revision, history.c.event_id)
        .select_from(history.join(gorgons, sa.true()))
        .where(
            history.c.campaign_id == game.store.campaign_id,
            sa.func.json_extract(gorgons.c.value, "$.id") == specimen.id,
            sa.func.json_extract(gorgons.c.value, "$.alive") == 0,
        )
        .order_by(history.c.revision)
        .limit(1)
    ).first()
    if found is None:
        return None
    prior = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.revision == found.revision - 1,
        )
    )
    before = GameState.model_validate_json(prior) if prior else None
    if (
        before
        and before.world
        and any(x.id == specimen.id and x.alive for x in before.world.gorgons)
    ):
        return str(found.event_id)
    return None


def eligible(
    game: GameService, c: Connection, state: GameState, session: ordinary.Session, handler: ActorRef
) -> tuple[tuple[Gorgon, str, str], ...]:
    role = active_book(game, c, state, book="Scientist", rule=rules.BOOK)
    if (
        state.world is None
        or role is None
        or role[0] != handler
        or session.end_event is not None
        or session.facilitator != int(handler.entity)
        or any(
            x.handler == handler and (x.session == session.id or x.trigger == rules.TRIGGER)
            for x in ordinary.marks(state)
        )
    ):
        return ()
    used = {x.specimen.entity for x in rules.records(state)}
    return tuple(
        (specimen, lab, event)
        for specimen in state.world.gorgons
        if specimen.id not in used
        and (lab := lab_at(state, specimen.cell)) is not None
        and (event := death(game, c, specimen)) is not None
    )


def prove_award(game: GameService, c: Connection, award: awards.Award) -> None:
    source = award.ordinary_source
    assert source is not None
    saved = _history(c, game, award.award_event)
    value = next((x for x in rules.records(saved) if x.id == source.review), None)
    session = _session(game, c, saved, source.session)
    original = next((x for x in awards.awards(saved) if x.id == award.id), None)
    found = c.scalar(
        sa.select(t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == award.award_event,
            t.events.c.actor_id == award.handler.entity,
        )
    )
    specimen = (
        next((x for x in saved.world.gorgons if value and x.id == value.specimen.entity), None)
        if saved.world
        else None
    )
    marks = [
        x
        for x in ordinary.marks(saved)
        if x.handler == award.handler and (x.session == session.id or x.trigger == rules.TRIGGER)
    ]
    if (
        value is None
        or specimen is None
        or value.handler != award.handler
        or value.event != award.award_event
        or award.source_event != value.event
        or value.account != award.account
        or value.lab != lab_at(saved, specimen.cell)
        or value.death != death(game, c, specimen)
        or original is None
        or original.phase != "held"
        or original.handler != award.handler
        or original.source_event != award.source_event
        or original.ordinary_source != source
        or original.appointment != award.appointment
        or active_handler(saved) != award.handler
        or session.end_event is not None
        or session.appointment != award.appointment
        or saved.handler_persona is None
        or saved.handler_persona.playbook != "Scientist"
        or found != EVENT
        or len(marks) != 1
        or marks[0].award != award.id
        or marks[0].review != value.id
        or marks[0].event != value.event
        or marks[0].trigger != rules.TRIGGER
    ):
        raise WorkflowError("Recover the actual original Scientist, specimen and Session award")


class DissectionService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def perform(
        self,
        viewer: GuildViewer,
        key: str,
        session_id: str,
        expected: int,
        specimen_id: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            session = _session(self.game, c, state, session_id)
            handler = active_handler(state)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or state.revision != expected
            ):
                raise WorkflowError(
                    "Only the original Scientist may reopen the actual current Session"
                )
            appointment = _appointment_at(c, self.game, session.start_event, handler)
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if session.appointment != appointment:
                raise WorkflowError("Recover the original Scientist's Session appointment")
            picked = next(
                (
                    x
                    for x in eligible(self.game, c, state, session, handler)
                    if x[0].id == specimen_id
                ),
                None,
            )
            if picked is None or not 1 <= len(account.strip()) <= 1200:
                raise WorkflowError(
                    "Complete a real eligible laboratory dissection in a free Session"
                )
            specimen, lab, original_death = picked
            event = str(uuid4())
            value = rules.Dissection(
                id=rules.KIND + ":" + specimen.id,
                handler=handler,
                specimen=ActorRef(kind="gorgon", entity=specimen.id),
                lab=lab,
                death=original_death,
                event=event,
                account=account.strip(),
            )
            identity = "ordinary:" + value.id
            state.facts.append(dict(kind=rules.KIND, id=value.id, body=value.model_dump_json()))
            ordinary.put(
                state,
                ordinary.Mark(
                    id=rules.KIND + ":" + handler.token,
                    handler=handler,
                    session=session.id,
                    review=value.id,
                    award=identity,
                    event=event,
                    trigger=rules.TRIGGER,
                ),
            )
            awards.grant(
                state,
                awards.Award(
                    id=identity,
                    rule=ordinary.RULE,
                    handler=handler,
                    appointment=appointment,
                    ordinary_source=ordinary.AwardSource(
                        session=session.id, review=value.id, trigger=rules.TRIGGER
                    ),
                    source_event=event,
                    award_event=event,
                    account=value.account,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                session_id=session.id,
                award_id=identity,
            )
            return dict(id=identity, phase="held")

        return HandlerOrdinaryService(self.store)._write(
            viewer,
            key,
            EVENT,
            dict(
                session=session_id,
                expected=expected,
                specimen=specimen_id,
                account=account,
            ),
            operation,
        )
