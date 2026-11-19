"""Change the current Handler book and retain a proved original Play."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_borrowed as borrowed
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_play_state import DRESS_RULE
from girlframe.engine.m3_handler_state import BookChange
from girlframe.engine.m3_scientist_lab import steps
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_borrowed import owned
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "handler-advancement.handler-advancement.swap-playbook"


def change_sequence(
    game: GameService, c: Connection, handler: ActorRef, change: BookChange
) -> int | None:
    saved = _history(c, game, change.event)
    persona = saved.handler_persona
    if (
        active_handler(saved) != handler
        or persona is None
        or persona.book_change != change
        or not any(
            x.id == change.award
            and x.handler == handler
            and x.phase == "spent"
            and x.spend_event == change.event
            and x.acquired_rule == RULE
            and x.acquisition == change.id
            for x in awards.awards(saved)
        )
        or not any(
            x.id == change.retained and x.handler == handler for x in borrowed.acquisitions(saved)
        )
    ):
        return None
    return c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == change.event,
            t.events.c.kind == "m3.handler_advancement_spent",
            t.events.c.actor_id == handler.entity,
        )
    )


class HandlerBookSwapService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)
        self.advancement = HandlerAdvancementService(store)

    def swap(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        expected: int,
        playbook: str,
        retain: str,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.advancement._access(c, viewer, RULE)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            _, state, handler, appointment, payment = self.advancement._source(c, viewer, award_id)
            self.advancement._current(c, state, handler, appointment)
            persona = state.handler_persona
            if (
                payment is None
                or payment.phase != "held"
                or state.revision != expected
                or persona is None
                or persona.playbook != "Scientist"
                or persona.book_change is not None
                or playbook != "Frantic"
                or retain != DRESS_RULE
                or not 1 <= len(account.strip()) <= 1200
                or steps(state, handler)
                or not owned(self.game, c, state, handler, retain)
            ):
                raise WorkflowError(
                    "Use a fresh held award, an eligible current book and one actual retained Play"
                )
            (learned,) = (
                x for x in borrowed.acquisitions(state) if x.handler == handler and x.rule == retain
            )
            if any(
                same_handler_body(state, x.handler)
                and x.acquired_rule is not None
                and x.id != learned.award
                for x in awards.awards(state)
            ):
                raise WorkflowError(
                    "Review the other acquired Handler advancements before swapping"
                )
            event = str(uuid4())
            change = BookChange(
                id="handler-book-swap:" + payment.id,
                award=payment.id,
                event=event,
                playbook="Frantic",
                retained=learned.id,
            )
            state.handler_persona = persona.model_copy(update=dict(book_change=change))
            awards.put(
                state,
                payment.model_copy(
                    update=dict(
                        phase="spent",
                        acquired_rule=RULE,
                        acquisition=change.id,
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
                rule_id=RULE,
            )
            return dict(id=change.id, playbook=change.playbook, retained=retain)

        return self.store._write(
            viewer,
            key,
            "m3.handler_advancement_spent",
            dict(
                award_id=award_id,
                expected=expected,
                playbook=playbook,
                retain=retain,
                account=account,
                rule=RULE,
            ),
            operation,
            authorize=authorize,
            auto_audit=False,
        )
