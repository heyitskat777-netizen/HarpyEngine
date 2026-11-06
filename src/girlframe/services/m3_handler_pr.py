"""Owned performed PR, true public outcomes and capped/deferred genuine advancement."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_handler_pr as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_handler_advancements import (
    HandlerAdvancementService,
    _appointment_at,
    _history,
)
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService, _session
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _audit(game: GameService, c: Connection, event: str, kind: str, actor: str) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != kind or row["actor_id"] != actor:
        raise WorkflowError("Recover the actual PR source actor and immutable event")


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Event:
    value = next((x for x in rules.events(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original public-relations event")
    plan = next(
        (x for x in rules.events(_history(c, game, value.plan_event)) if x.id == identity), None
    )
    _audit(game, c, value.plan_event, "m3.handler_pr_planned", value.host.entity)
    if plan is None or any(
        getattr(plan, k) != getattr(value, k)
        for k in (
            "id",
            "host",
            "appointment",
            "planned_session",
            "plan_event",
            "objective",
            "context",
            "people",
        )
    ):
        raise WorkflowError("Preserve the original host, objective, Cadre and planning Session")
    session = _session(game, c, _history(c, game, value.plan_event), value.planned_session)
    if (
        session.end_event
        or session.facilitator != int(value.host.entity)
        or session.appointment != value.appointment
    ):
        raise WorkflowError("Recover the actual original Session and hosting authority")
    for activity in ((value.hosting,) if value.hosting else ()) + value.activities:
        kind = "m3.handler_pr_hosted" if activity.actor == value.host else "m3.handler_pr_activity"
        _audit(game, c, activity.event, kind, activity.actor.entity)
        recorded = next(
            (x for x in rules.events(_history(c, game, activity.event)) if x.id == identity), None
        )
        if (
            recorded is None
            or activity
            not in ((recorded.hosting,) if recorded.hosting else ()) + recorded.activities
        ):
            raise WorkflowError("Recover each original actor's actual performed PR activity")
        if activity.action:
            action = game.action(c, activity.action)
            if (
                action["actor_id"] != activity.actor.entity
                or action["state"] != "complete"
                or action["data"].get("character_ids", {}).get(activity.actor.entity)
                != activity.actor.incarnation
            ):
                raise WorkflowError(
                    "A referenced Play must be this original actor's real completed action"
                )
    if value.result_event:
        result = next(
            (x for x in rules.events(_history(c, game, value.result_event)) if x.id == identity),
            None,
        )
        _audit(game, c, value.result_event, "m3.handler_pr_resolved", str(value.judge))
        if (
            result is None
            or any(
                getattr(result, k) != getattr(value, k)
                for k in (
                    "hosting",
                    "activities",
                    "submitted_event",
                    "result_event",
                    "successful",
                    "public_result",
                    "judge",
                    "judge_appointment",
                )
            )
            or value.phase != "complete"
            or value.hosting is None
            or not value.activities
            or value.successful is None
            or not value.public_result
        ):
            raise WorkflowError("Preserve the actual performed event and its true public result")
    return value


def _slot(
    game: GameService, c: Connection, state: GameState, host: ActorRef
) -> tuple[ordinary.Session | None, str | None]:
    if not same_handler_body(state, host):
        return None, "original_host_unavailable"
    if game.pending_actions(c):
        return None, "finish_pending_play"
    marks = [x for x in ordinary.marks(state) if same_handler_body(state, x.handler)]
    if any(x.trigger == "public_relations" for x in marks):
        return None, "criterion_marked"
    session = next(
        (
            x
            for x in ordinary.sessions(state)
            if x.end_event is None and x.facilitator == int(host.entity)
        ),
        None,
    )
    if session is None:
        return None, "no_active_session"
    _session(game, c, state, session.id)
    if any(x.session == session.id for x in marks):
        return None, "session_slot_used"
    return session, None


def _award(
    state: GameState, value: rules.Event, session: ordinary.Session, event: str
) -> rules.Event:
    identity = "ordinary:" + value.id
    ordinary.put(
        state,
        ordinary.Mark(
            id="pr-mark:" + value.host.token,
            handler=value.host,
            session=session.id,
            review=value.id,
            award=identity,
            event=event,
            trigger="public_relations",
        ),
    )
    advancement.grant(
        state,
        advancement.Award(
            id=identity,
            rule=ordinary.RULE,
            handler=value.host,
            appointment=value.appointment,
            source_work=None,
            source_event=value.result_event or event,
            award_event=event,
            account=value.public_result or "",
            ordinary_source=ordinary.AwardSource(
                session=session.id, review=value.id, trigger="public_relations"
            ),
        ),
    )
    return value.model_copy(
        update=dict(award=identity, award_session=session.id, award_event=event, award_blocked=None)
    )


def prove_award(
    game: GameService, c: Connection, state: GameState, award: advancement.Award
) -> None:
    declared = award.ordinary_source
    if (
        declared is None
        or declared.trigger != "public_relations"
        or award.rule != ordinary.RULE
        or award.source_work is not None
    ):
        raise WorkflowError("Recover the exact real PR ordinary-award origin")
    birth = _history(c, game, award.award_event)
    value = source(game, c, birth, declared.review)
    born = next((x for x in advancement.awards(birth) if x.id == award.id), None)
    session = _session(game, c, birth, declared.session)
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == award.award_event
            )
        )
        .mappings()
        .first()
    )
    if (
        born is None
        or born.phase != "held"
        or any(
            getattr(born, k) != getattr(award, k)
            for k in (
                "id",
                "rule",
                "handler",
                "appointment",
                "source_work",
                "ordinary_source",
                "source_event",
                "award_event",
                "account",
            )
        )
        or value.successful is not True
        or (value.award, value.award_event, value.award_session)
        != (award.id, award.award_event, declared.session)
        or value.host != award.handler
        or value.appointment != award.appointment
        or session.end_event
        or session.facilitator != int(value.host.entity)
        or row is None
        or row["kind"] not in ("m3.handler_pr_resolved", "m3.handler_pr_claimed")
        or row["actor_id"] != value.host.entity
        or _appointment_at(c, game, session.start_event, value.host) != value.appointment
    ):
        raise WorkflowError("Recover true successful PR and its actual capped award Session")
    marks = [x for x in ordinary.marks(birth) if x.handler == value.host]
    if (
        len([x for x in marks if x.session == declared.session]) != 1
        or len([x for x in marks if x.trigger == "public_relations"]) != 1
        or not any(
            x.award == award.id and x.review == value.id and x.event == award.award_event
            for x in marks
        )
    ):
        raise WorkflowError("Preserve the shared ordinary cap and separate permanent PR mark-off")


class HandlerPRService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)
        self.ordinary = HandlerOrdinaryService(store)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        return self.ordinary._write(viewer, key, kind, payload, operation)

    def _host(
        self, c: Connection, state: GameState, viewer: GuildViewer, value: rules.Event
    ) -> None:
        if value.host.entity != str(viewer.user_id):
            raise WorkflowError("Only this actual original Handler hosts or claims this event")
        HandlerAdvancementService(self.store)._current(c, state, value.host, value.appointment)

    def plan(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        objective: str,
        context: str,
        people: tuple[ActorRef, ...],
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            host = active_handler(state)
            session = next(
                (
                    x
                    for x in ordinary.sessions(state)
                    if x.end_event is None and x.facilitator == viewer.user_id
                ),
                None,
            )
            if (
                host is None
                or host.entity != str(viewer.user_id)
                or state.revision != revision
                or session is None
                or not people
                or len(set(people)) != len(people)
                or any(x.kind != "pilot" or current_ref(state, int(x.entity)) != x for x in people)
            ):
                raise WorkflowError(
                    "Plan actual Foundation PR with an original Handler, real Session and Cadre"
                )
            HandlerAdvancementService(self.store)._current(c, state, host, session.appointment)
            event = str(uuid4())
            value = rules.Event(
                id="pr-event:" + event,
                host=host,
                appointment=session.appointment,
                planned_session=session.id,
                plan_event=event,
                objective=objective.strip(),
                context=context.strip(),
                people=people,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_pr_planned",
                state,
                event_id=event,
                pr_event=value.id,
            )
            return dict(id=value.id, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_pr_planned",
            dict(
                revision=revision,
                objective=objective,
                context=context,
                people=[x.model_dump(mode="json") for x in people],
            ),
            operation,
        )

    def activity(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        description: str,
        action: str | None = None,
        *,
        hosting: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if state.revision != revision or value.phase not in ("planned", "conduct"):
                raise WorkflowError(
                    "Reopen the actual PR conduct before recording performed activity"
                )
            if not hosting and str(viewer.user_id) not in state.sheets:
                raise WorkflowError(
                    "Only an actual original participating Girl records this activity"
                )
            actor = value.host if hosting else current_ref(state, viewer.user_id)
            if hosting:
                self._host(c, state, viewer, value)
                if value.hosting is not None:
                    raise WorkflowError("This actual hosting has already been recorded")
            elif actor not in value.people:
                raise WorkflowError("Record only your own original Girl's actual PR activity")
            if action:
                played = self.game.action(c, action)
                if (
                    played["actor_id"] != actor.entity
                    or played["state"] != "complete"
                    or played["data"].get("character_ids", {}).get(actor.entity)
                    != actor.incarnation
                ):
                    raise WorkflowError("Reference only your actual completed original-body Play")
            event = str(uuid4())
            actual = rules.Activity(
                actor=actor, event=event, description=description.strip(), action=action
            )
            value = (
                value.model_copy(update=dict(phase="conduct", hosting=actual))
                if hosting
                else value.model_copy(
                    update=dict(phase="conduct", activities=value.activities + (actual,))
                )
            )
            rules.put(state, value)
            kind = "m3.handler_pr_hosted" if hosting else "m3.handler_pr_activity"
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, pr_event=identity)
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_pr_activity",
            dict(
                id=identity,
                revision=revision,
                description=description,
                action=action,
                hosting=hosting,
            ),
            operation,
        )

    def submit_result(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            self._host(c, state, viewer, value)
            if (
                state.revision != revision
                or value.phase != "conduct"
                or value.hosting is None
                or not value.activities
                or not account.strip()
            ):
                raise WorkflowError(
                    "Only an actually hosted PR event with real Cadre activity reaches results"
                )
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        phase="result", submitted_event=event, submitted_account=account.strip()
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_pr_submitted",
                state,
                event_id=event,
                pr_event=identity,
            )
            return dict(id=identity, phase="result")

        return self._write(
            viewer,
            key,
            "m3.handler_pr_submitted",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def resolve(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        successful: bool,
        public_result: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            human, appointment = MedicalService(self.store)._handler(c)
            if (
                viewer.user_id != human
                or state.revision != revision
                or value.phase != "result"
                or not public_result.strip()
            ):
                raise WorkflowError(
                    "The authorized human GM records this performed event's actual public result"
                )
            event = str(uuid4())
            value = value.model_copy(
                update=dict(
                    phase="complete",
                    result_event=event,
                    successful=successful,
                    public_result=public_result.strip(),
                    judge=human,
                    judge_appointment=appointment,
                )
            )
            if (
                successful
                and same_handler_body(state, value.host)
                and appointment == value.appointment
            ):
                session, blocked = _slot(self.game, c, state, value.host)
                if session is not None:
                    value = _award(state, value, session, event)
                else:
                    value = value.model_copy(update=dict(award_blocked=blocked))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_pr_resolved",
                state,
                event_id=event,
                pr_event=identity,
                successful=successful,
                award_id=value.award,
            )
            return dict(id=identity, phase="complete", successful=successful, award=value.award)

        return self._write(
            viewer,
            key,
            "m3.handler_pr_resolved",
            dict(
                id=identity, revision=revision, successful=successful, public_result=public_result
            ),
            operation,
        )

    def claim(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            self._host(c, state, viewer, value)
            session, blocked = _slot(self.game, c, state, value.host)
            if (
                state.revision != revision
                or value.phase != "complete"
                or value.successful is not True
                or value.award is not None
                or session is None
            ):
                raise WorkflowError(
                    "Claim needs its original Handler and a free Session slot: "
                    + str(blocked or "already awarded")
                )
            event = str(uuid4())
            value = _award(state, value, session, event)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_pr_claimed",
                state,
                event_id=event,
                pr_event=identity,
                award_id=value.award,
                session_id=session.id,
            )
            return dict(id=identity, phase="complete", award=value.award)

        return self._write(
            viewer, key, "m3.handler_pr_claimed", dict(id=identity, revision=revision), operation
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.ordinary._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            human, _ = MedicalService(self.store)._handler(c)
            if identity:
                value = source(self.game, c, state, identity)
                own = value.host.entity == str(viewer.user_id)
                participant = any(x.entity == str(viewer.user_id) for x in value.people)
                if not (own or participant or viewer.user_id == human):
                    raise WorkflowError("This PR history belongs to its actual participants and GM")
                session, blocked = _slot(self.game, c, state, value.host) if own else (None, None)
                return dict(
                    id=identity,
                    revision=state.revision,
                    phase=value.phase,
                    host=own,
                    participant=participant,
                    judge=viewer.user_id == human,
                    objective=value.objective,
                    context=value.context,
                    hosting=value.hosting is not None,
                    activities=[
                        dict(actor=x.actor.model_dump(mode="json"), description=x.description)
                        for x in value.activities
                    ],
                    successful=value.successful,
                    public_result=value.public_result,
                    award=value.award,
                    claimable=own
                    and value.successful is True
                    and value.award is None
                    and session is not None,
                    blocked=blocked,
                )
            return dict(
                revision=state.revision,
                host=human == viewer.user_id,
                people=[
                    dict(
                        actor=current_ref(state, uid).model_dump(mode="json"),
                        token=current_ref(state, uid).token,
                        label=state.sheets[str(uid)].callsign,
                    )
                    for uid in state.order
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        values = rules.events(state)
        if not values:
            return []
        human, _ = MedicalService(self.store)._handler(c)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Public fundraiser/photoshoot — " + x.phase,
                phase=x.phase,
                pending=x.phase == "result" and viewer.user_id == human,
            )
            for x in values
            if x.host.entity == str(viewer.user_id)
            or any(y.entity == str(viewer.user_id) for y in x.people)
            or viewer.user_id == human
        ]
