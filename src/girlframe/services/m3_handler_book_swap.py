"""Change the current Handler book and retain one proved ability."""

from typing import Any, Literal, NamedTuple
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_borrowed as borrowed
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_state import PLAYBOOKS, BookChange
from girlframe.engine.m3_scientist_lab import steps
from girlframe.services.m2_game import GameService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.m3_handler_borrowed import acquired
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "handler-advancement.handler-advancement.swap-playbook"


class Retention(NamedTuple):
    identity: str
    label: str
    kind: Literal["native", "borrowed", "advancement"]


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
    ):
        return None
    if change.retained_advancement:
        retained = next(
            (
                x
                for x in awards.awards(saved)
                if x.id == change.retained
                and x.handler == handler
                and x.phase == "spent"
                and x.acquired_rule not in (None, borrowed.RULE, RULE)
            ),
            None,
        )
        if retained is None or change.native_rule is not None:
            return None
        HandlerAdvancementService(game.store)._spent(c, retained, handler)
    elif change.native_rule is not None:
        option = borrowed.PLAYS.get(change.native_rule)
        if option is None or change.retained != change.native_rule:
            return None
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.revision == saved.revision - 1,
            )
        )
        if raw is None:
            return None
        before = GameState.model_validate_json(raw)
        former = active_book(game, c, before, book=option[0], rule=change.native_rule)
        if former is None or former[0] != handler:
            return None
    elif not any(
        x.id == change.retained and x.handler == handler for x in borrowed.acquisitions(saved)
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

    def _retentions(
        self, c: Connection, state: GameState, handler: ActorRef
    ) -> dict[str, Retention]:
        from girlframe.services.m3_access import Access

        persona = state.handler_persona
        if persona is None:
            return {}
        other = [
            x
            for x in awards.awards(state)
            if same_handler_body(state, x.handler)
            and x.acquired_rule not in (None, borrowed.RULE, RULE)
        ]
        if other:
            if len(other) != 1:
                raise WorkflowError(
                    "Review the competing acquired advancements before changing books"
                )
            (retained,) = other
            registry = Access(self.store).registry
            if not retained.acquired_rule or registry is None:
                return {}
            self.advancement._spent(c, retained, handler)
            label = registry.entry(retained.acquired_rule).title
            return {"award:" + retained.id: Retention(retained.id, label, "advancement")}
        choices = {}
        for rule, (book, label) in borrowed.PLAYS.items():
            role = active_book(self.game, c, state, book=book, rule=rule)
            if role is None or role[0] != handler:
                continue
            retained_native = persona.playbook == book or (
                persona.book_change is not None and persona.book_change.native_rule == rule
            )
            if retained_native:
                choices[rule] = Retention(rule, label, "native")
            elif learned := acquired(self.game, c, state, handler, rule):
                choices[rule] = Retention(learned[0].id, label, "borrowed")
        return choices

    def _settled(self, c: Connection, state: GameState, handler: ActorRef) -> None:
        from girlframe.engine.m3_advocate_alone import records as conversations
        from girlframe.engine.m3_frantic_breakdown import phase
        from girlframe.engine.m3_frantic_breakdown import records as breakdowns
        from girlframe.engine.m3_handler_private_scene import records as private_scenes
        from girlframe.services.m3_handler_private_scene import HandlerPrivateSceneService

        private = HandlerPrivateSceneService(self.store, self.game)
        if (
            steps(state, handler)
            or any(x.handler == handler and x.effect is None for x in conversations(state))
            or any(
                x.handler == handler and phase(state, x) != "complete" for x in breakdowns(state)
            )
            or any(
                x.handler == handler and private._pending(c, state, x)
                for x in private_scenes(state)
            )
        ):
            raise WorkflowError(
                "Review current obligations and other acquired advancements before changing books"
            )

    def options(
        self, viewer: GuildViewer, award_id: str
    ) -> tuple[int, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
        with self.store.engine.connect() as c:
            self.advancement._access(c, viewer, RULE)
            _, state, handler, appointment, payment = self.advancement._source(c, viewer, award_id)
            persona = state.handler_persona
            if payment is None or payment.phase != "held" or persona is None:
                return state.revision, (), ()
            self.advancement._current(c, state, handler, appointment)
            self._settled(c, state, handler)
            return (
                state.revision,
                tuple((book, book) for book in PLAYBOOKS if book != persona.playbook),
                tuple(
                    (rule, option.label)
                    for rule, option in self._retentions(c, state, handler).items()
                ),
            )

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
            kept = self._retentions(c, state, handler).get(retain)
            next_book = next((book for book in PLAYBOOKS if book == playbook), None)
            if (
                payment is None
                or payment.phase != "held"
                or state.revision != expected
                or persona is None
                or next_book is None
                or next_book == persona.playbook
                or kept is None
                or not 1 <= len(account.strip()) <= 1200
            ):
                raise WorkflowError(
                    "Use a fresh held award, an eligible current book "
                    "and one actual retained Play or advancement"
                )
            self._settled(c, state, handler)
            event = str(uuid4())
            change = BookChange(
                id="handler-book-swap:" + payment.id,
                award=payment.id,
                event=event,
                playbook=next_book,
                retained=kept.identity,
                native_rule=retain if kept.kind == "native" else None,
                retained_advancement=kept.kind == "advancement",
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
