"""A paid borrowed Handler Play uses its real original execution path."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancements
from girlframe.engine import m3_handler_borrowed as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import DRESS_RULE
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_book_orders import book_rule_available
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def owned(
    game: GameService,
    c: Connection,
    state: GameState,
    handler: ActorRef | None,
    rule: str,
) -> bool:
    if handler is None or handler != active_handler(state) or not book_rule_available(game, rule):
        return False
    matching = [x for x in rules.acquisitions(state) if x.handler == handler and x.rule == rule]
    if not matching:
        return False
    if len(matching) != 1:
        raise WorkflowError("Recover the original Handler's one acquired copy of this Play")
    value = matching[0]
    birth = _history(c, game, value.event)
    payment = next((row for row in advancements.awards(birth) if row.id == value.award), None)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.event,
        )
    ).first()
    if (
        value not in rules.acquisitions(birth)
        or active_handler(birth) != handler
        or birth.handler_persona is None
        or birth.handler_persona.draft.playbook == value.book
        or payment is None
        or payment.phase != "spent"
        or payment.acquired_rule != rules.RULE
        or payment.acquisition != value.id
        or payment.handler != handler
        or payment.appointment != value.appointment
        or payment.spend_event != value.event
        or audit is None
        or audit.kind != "m3.handler_advancement_spent"
        or audit.actor_id != handler.entity
    ):
        raise WorkflowError("Recover the actual original advancement and the borrowed Play")
    return True


class BorrowedHandlerService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)
        self.advancement = HandlerAdvancementService(store)

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        expected: int,
        play: str,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self.advancement._access(c, viewer, rules.RULE)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            _, state, handler, appointment, award = self.advancement._source(c, viewer, award_id)
            self.advancement._current(c, state, handler, appointment)
            if (
                award is None
                or award.phase != "held"
                or state.revision != expected
                or play != DRESS_RULE
                or not book_rule_available(self.game, play)
                or state.handler_persona is None
                or state.handler_persona.draft.playbook == "Dogrunner"
                or owned(self.game, c, state, handler, play)
                or not 1 <= len(account.strip()) <= 1200
            ):
                raise WorkflowError(
                    "Use an actual held award and an unowned Play from another book"
                )
            event = str(uuid4())
            value = rules.Acquisition(
                id="borrowed-handler:" + award.id,
                award=award.id,
                handler=handler,
                appointment=appointment,
                event=event,
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
            return dict(id=value.id, phase="held", play=value.rule)

        return self.store._write(
            viewer,
            key,
            "m3.handler_advancement_spent",
            dict(award_id=award_id, expected=expected, play=play, account=account, rule=rules.RULE),
            operation,
            authorize=access,
            auto_audit=False,
        )
