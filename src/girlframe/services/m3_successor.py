"""Actual Successor acquisition, original advice, and the first Gold Star milestone."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancements
from girlframe.engine import m3_successor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_handler_play_state import HandlerPlay
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def owned(
    game: GameService, c: Connection, state: GameState, handler: ActorRef | None
) -> rules.Acquisition | None:
    if handler is None or handler != active_handler(state):
        return None
    matches = [x for x in rules.acquisitions(state) if x.handler == handler]
    if not matches:
        return None
    if len(matches) != 1:
        raise WorkflowError("Recover the original Handler's one actual Successor acquisition")
    value = matches[0]
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    original = _history(c, game, value.event)
    award = next((x for x in advancements.awards(original) if x.id == value.award), None)
    if (
        audit is None
        or audit.kind != "m3.handler_advancement_spent"
        or audit.actor_id != handler.entity
        or value not in rules.acquisitions(original)
        or award is None
        or award.phase != "spent"
        or award.acquisition != value.id
        or award.acquired_rule != rules.RULE
        or award.handler != handler
        or award.appointment != value.appointment
        or award.spend_event != value.event
    ):
        raise WorkflowError("Recover the actual paid source of this Successor advancement")
    return value


def _sequence(
    game: GameService, c: Connection, event: str | None, action: str | None = None
) -> int | None:
    audit = c.execute(
        sa.select(t.events.c.seq, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if (
        audit is None
        or action is not None
        and json.loads(audit.payload_json).get("action_id") != action
    ):
        return None
    return int(audit.seq)


def _matches(
    game: GameService,
    c: Connection,
    state: GameState,
    advice: HandlerPlay,
    lesson: dict[str, Any],
) -> bool:
    target = advice.targets[0]
    info = lesson["data"]
    if (
        lesson["state"] != "complete"
        or lesson["scene_id"] != advice.scope.scene_id
        or lesson["actor_id"] != target.entity
        or not info.get("receipt")
        or advice.chooser_actor is None
        or int(advice.chooser_actor.entity) not in info.get("participants", ())
        or info.get("character_ids", {}).get(target.entity) != target.incarnation
        or target.entity not in state.sheets
        or current_ref(state, int(target.entity)) != target
    ):
        return False
    advice_seq = _sequence(game, c, advice.completed_event)
    lesson_seq = _sequence(game, c, info.get("response_event"), lesson["id"])
    return advice_seq is not None and lesson_seq is not None and lesson_seq > advice_seq


class SuccessorService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)
        self.advancement = HandlerAdvancementService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        self.advancement._access(c, viewer, rules.RULE)
        self.game.unpaused(c)

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        expected: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            _, state, handler, appointment, award = self.advancement._source(c, viewer, award_id)
            self.advancement._current(c, state, handler, appointment)
            if (
                award is None
                or award.phase != "held"
                or state.revision != expected
                or not 1 <= len(account.strip()) <= 1200
                or owned(self.game, c, state, handler)
            ):
                raise WorkflowError(
                    "Spend one actual held award on the original Successor advancement"
                )
            event = str(uuid4())
            value = rules.Acquisition(
                id="successor:" + award.id,
                award=award.id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put_acquisition(state, value)
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
            return dict(id=value.id, phase="held")

        return self.store._write(
            viewer,
            key,
            "m3.handler_advancement_spent",
            dict(award_id=award_id, expected=expected, account=account, rule=rules.RULE),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def _original(
        self, c: Connection, viewer: GuildViewer, state: GameState, *, removal: bool = False
    ) -> rules.Acquisition:
        value = owned(self.game, c, state, active_handler(state))
        if value is None or value.handler.entity != str(viewer.user_id):
            raise WorkflowError("The original Successor advancement belongs to its Handler")
        if removal:
            if (
                HandlerCreationService(self.store)._appointment_source(c, viewer.user_id)
                != value.appointment
            ):
                raise WorkflowError("This Gold Star decision belongs to the original appointment")
        else:
            self.advancement._current(c, state, value.handler, value.appointment)
        return value

    def judge(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        advice_id: str,
        lesson_id: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = self._original(c, viewer, state)
            if (
                state.revision != expected
                or value.id != identity
                or not 1 <= len(account.strip()) <= 1200
            ):
                raise WorkflowError("Reopen the original Successor before judging this lesson")
            from girlframe.services.m3_handler_plays import _source

            _, advice = _source(c, self.game, advice_id)
            if (
                advice.clause != rules.RULE
                or advice.chooser_actor != value.handler
                or advice.selected != "successor_advice"
                or advice.state != "complete"
                or advice.scope.scene_id is None
                or len(advice.targets) != 1
            ):
                raise WorkflowError("Use an actual completed Successor advice Play")
            lesson = self.game.action(c, lesson_id)
            if not _matches(self.game, c, state, advice, lesson):
                raise WorkflowError("Use a later real Play by the same Girl in the original scene")
            event = str(uuid4())
            star = rules.Star(
                id=event,
                acquisition=value.id,
                handler=value.handler,
                girl=advice.targets[0],
                advice=advice.id,
                lesson=lesson_id,
                event=event,
                account=account.strip(),
            )
            rules.award(state, star)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.successor_star_awarded",
                state,
                event_id=event,
                acquisition=identity,
                star=star.id,
            )
            return dict(id=star.id, revision=state.revision, girl=star.girl.entity)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.successor_star_awarded",
                dict(
                    id=identity,
                    expected=expected,
                    advice=advice_id,
                    lesson=lesson_id,
                    account=account,
                ),
                operation,
                authorize=lambda c: self._access(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def remove(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        star_id: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = self._original(c, viewer, state, removal=True)
            star = next(
                (
                    x
                    for x in rules.stars(state)
                    if x.id == star_id and x.acquisition == value.id and x.removed_event is None
                ),
                None,
            )
            if star is None or value.id != identity or state.revision != expected:
                raise WorkflowError(
                    "Choose one actual unremoved Gold Star of this original Successor"
                )
            event = str(uuid4())
            rules.put_star(state, star.model_copy(update=dict(removed_event=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.successor_star_removed",
                state,
                event_id=event,
                acquisition=identity,
                star=star_id,
            )
            return dict(id=star_id, revision=state.revision, state="removed")

        return self.store._write(
            viewer,
            key,
            "m3.successor_star_removed",
            dict(id=identity, expected=expected, star=star_id),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def menu(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = owned(self.game, c, state, active_handler(state))
            if value is None or value.id != identity or value.handler.entity != str(viewer.user_id):
                raise WorkflowError("This owned Successor belongs to its original Handler")
            awarded = tuple(x for x in rules.stars(state) if x.acquisition == value.id)
            used_advice, used_lessons = {x.advice for x in awarded}, {x.lesson for x in awarded}
            advice = tuple(
                x
                for x in state.handler_plays
                if x.clause == rules.RULE
                and x.chooser_actor == value.handler
                and x.state == "complete"
                and x.id not in used_advice
                and x.targets[0].entity in state.sheets
            )
            table = t.m2["m2_actions"]
            sessions = {x.scope.scene_id for x in advice}
            lessons = (
                tuple(
                    self.game.action(c, identity)
                    for identity in c.scalars(
                        sa.select(table.c.id).where(
                            table.c.campaign_id == self.store.campaign_id,
                            table.c.state == "complete",
                            table.c.scene_id.in_(sessions),
                            table.c.id.not_in(used_lessons),
                        )
                    )
                )
                if sessions
                else ()
            )
            available = {
                grant.id: tuple(
                    (x["id"], x["data"]["play"].replace("_", " ").capitalize())
                    for x in lessons
                    if _matches(self.game, c, state, grant, x)
                )
                for grant in advice
            }
            return dict(
                id=value.id,
                revision=state.revision,
                advice=tuple(
                    (
                        x.id,
                        state.sheets[x.targets[0].entity].callsign + " — " + x.effect.account[:36],
                    )
                    for x in advice
                    if available[x.id] and x.effect
                ),
                lessons=available,
                stars=tuple((x.id, x.girl.entity) for x in awarded if x.removed_event is None),
            )
