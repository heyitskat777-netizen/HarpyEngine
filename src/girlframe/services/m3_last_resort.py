"""Spend an actual advancement on the original Handler's hidden Frame reserve."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancements
from girlframe.engine import m3_last_resort as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world_state import Location
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def bases(state: GameState) -> tuple[Location, ...]:
    if state.world is None:
        return ()
    return tuple(
        x
        for x in state.world.locations
        if x.kind == "base" and x.foundation_operational and in_responsibility(state, x.cell)
    )


class LastResortService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)
        self.advancement = HandlerAdvancementService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        self.advancement._access(c, viewer, rules.RULE)
        self.game.unpaused(c)

    def options(self, viewer: GuildViewer, award: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _, state, handler, appointment, saved = self.advancement._source(c, viewer, award)
            self.advancement._current(c, state, handler, appointment)
            if saved is None or saved.phase != "held":
                raise WorkflowError("Choose a genuine held advancement for the reserve")
            return dict(
                revision=state.revision,
                bases=tuple((x.id, x.name) for x in bases(state)),
            )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        expected: int,
        base_id: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            _, state, handler, appointment, award = self.advancement._source(c, viewer, award_id)
            self.advancement._current(c, state, handler, appointment)
            base = next((x for x in bases(state) if x.id == base_id), None)
            if (
                award is None
                or award.phase != "held"
                or state.revision != expected
                or not 1 <= len(account.strip()) <= 1200
                or base is None
                or any(x.handler == handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError(
                    "Use a held award and an actual operational Base for the reserve"
                )
            event = str(uuid4())
            value = rules.Acquisition(
                id="last-resort:" + award.id,
                award=award.id,
                handler=handler,
                appointment=appointment,
                event=event,
                base=base.id,
                cell=base.cell,
                chassis="last-resort-frame:" + event,
                cadre=tuple(current_ref(state, uid) for uid in state.order),
                account=account.strip(),
            )
            rules.put(state, value)
            advancements.put(
                state,
                award.model_copy(
                    update=dict(
                        phase="spent",
                        acquired_rule=rules.RULE,
                        acquisition=value.id,
                        spend_event=event,
                        spend_account=account.strip(),
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="reserved")

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_advancement_spent",
                dict(
                    award_id=award_id,
                    expected=expected,
                    base=base_id,
                    account=account,
                    rule=rules.RULE,
                ),
                operation,
                authorize=lambda c: self._access(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def menu(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
            if (
                value is None
                or value.handler != active_handler(state)
                or value.handler.entity != str(viewer.user_id)
            ):
                raise WorkflowError("The hidden reserve belongs to its original Handler")
            history = _history(c, self.game, value.event)
            recorded = next((x for x in rules.acquisitions(history) if x.id == identity), None)
            award = next((x for x in advancements.awards(history) if x.id == value.award), None)
            event = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.event,
                )
            ).first()
            if (
                recorded != value
                or event is None
                or event.kind != "m3.handler_advancement_spent"
                or event.actor_id != value.handler.entity
                or award is None
                or award.phase != "spent"
                or award.acquired_rule != rules.RULE
                or award.acquisition != value.id
                or award.spend_event != value.event
                or award.appointment != value.appointment
                or award.handler != value.handler
                or not any(x.id == value.base and x.cell == value.cell for x in bases(history))
            ):
                raise WorkflowError(
                    "Recover the actual paid Last / Resort reserve and its original Base"
                )
            dead, needed = rules.loss_threshold(state, value)
            location = next(
                (x for x in bases(state) if x.id == value.base and x.cell == value.cell), None
            )
            return dict(
                id=value.id,
                base=location.name if location else None,
                base_available=location is not None,
                chassis=value.chassis,
                confirmed_losses=len(dead),
                needed=needed,
                loss_threshold_met=len(dead) >= needed,
                phase="reserved",
            )
