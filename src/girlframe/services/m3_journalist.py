"""A private native job question with an actual source-owned refusal Tag."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_journalist as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_battle import _cast
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ASKED = "m3.journalist_asked"
ANSWERED = "m3.journalist_answered"
FAMILY_ASKED = "m3.family_discrepancy_raised"
FAMILY_ANSWERED = "m3.family_discrepancy_answered"


def eligible(
    state: GameState, cast: SceneCast, reporter: ActorRef, controller: int, job: rules.Job
) -> tuple[ActorRef, ...]:
    actual = (
        next((x for x in state.world.npcs if x.id == reporter.entity), None)
        if state.world
        else None
    )
    if (
        reporter.kind != "npc"
        or actual is None
        or not actual.alive
        or job not in actual.jobs
        or actual.controller != controller
        or not any(x.actor == reporter and x.controller == controller for x in cast.roles)
    ):
        return ()
    return tuple(
        x.actor
        for x in cast.roles
        if x.actor.kind == "pilot"
        and x.controller != controller
        and str(x.controller) == x.actor.entity
        and x.actor.entity in state.sheets
        and state.sheets[x.actor.entity].character_id == x.actor.incarnation
    )


class JournalistService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer, job: rules.Job) -> None:
        if job not in rules.RULES:
            raise WorkflowError("Choose the actual original NPC job")
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.authorize(c, viewer, "world", director_response=True)
        assert access.registry is not None
        try:
            access.registry.require_available(rules.RULES[job])
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        self.game.unpaused(c)

    def targets(
        self,
        viewer: GuildViewer,
        channel: int,
        reporter: ActorRef,
        *,
        job: rules.Job = "journalist",
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer, job)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            girls = eligible(state, cast, reporter, viewer.user_id, job)
            return dict(
                revision=state.revision,
                targets=tuple((x.entity, state.sheets[x.entity].callsign) for x in girls),
            )

    def ask(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        reporter: ActorRef,
        girl: int,
        question: str,
        tag: str,
        *,
        job: rules.Job = "journalist",
    ) -> dict[str, Any]:
        if not 0 < len(question.strip()) <= 1200 or not 0 < len(tag.strip()) <= 120:
            raise WorkflowError("Provide the actual prompt and its conditional Tag")
        kind = FAMILY_ASKED if job == "family" else ASKED

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("STALE_QUESTION: reopen this actual scene after pending Plays")
            recipient = next(
                (
                    x
                    for x in eligible(state, cast, reporter, viewer.user_id, job)
                    if x.entity == str(girl)
                ),
                None,
            )
            if recipient is None:
                raise WorkflowError("Choose an original Girl addressed by your current NPC role")
            if any(
                x.scene == cast.id
                and x.reporter == reporter
                and x.girl == recipient
                and x.job == job
                and x.response is None
                for x in rules.questions(state)
            ):
                raise WorkflowError("Resume this NPC's actual unresolved request to this Girl")
            event = str(uuid4())
            rules.save(
                state,
                rules.Question(
                    id=event,
                    scene=cast.id,
                    channel=channel,
                    reporter=reporter,
                    controller=viewer.user_id,
                    girl=recipient,
                    question=question.strip(),
                    tag=tag.strip(),
                    job=job,
                ),
            )
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, scene_id=cast.id)
            return dict(id=event, state="pending")

        return self.store._write(
            viewer,
            key,
            kind,
            dict(
                channel=channel,
                expected=expected,
                reporter=reporter.model_dump(mode="json"),
                girl=girl,
                question=question,
                tag=tag,
            )
            | (dict(job=job) if job != "journalist" else {}),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer, job),
        )

    def _owned(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Question]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        value = next((x for x in rules.questions(state) if x.id == identity), None)
        if value is None or viewer.user_id not in (value.controller, int(value.girl.entity)):
            raise WorkflowError("Only the original NPC controller and Girl own this request")
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(
                t.events,
                (t.events.c.campaign_id == history.c.campaign_id)
                & (t.events.c.id == history.c.event_id),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == identity,
                t.events.c.kind == (FAMILY_ASKED if value.job == "family" else ASKED),
                t.events.c.actor_id == str(value.controller),
            )
        )
        first = GameState.model_validate_json(raw) if raw else None
        if first is None or value.model_copy(
            update=dict(response=None, reply=None, response_event=None)
        ) not in rules.questions(first):
            raise WorkflowError("Recover the actual original NPC request source")
        return state, value

    def live(self, c: Connection, state: GameState, value: rules.Question) -> bool:
        try:
            cast = _cast(self.game, c, state, value.channel)
        except (ValueError, WorkflowError):
            return False
        return cast.id == value.scene and value.girl in eligible(
            state, cast, value.reporter, value.controller, value.job
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value = self._owned(c, viewer, identity)
            return dict(
                revision=state.revision,
                question=value.question,
                job=value.job,
                response=value.response,
                reply=value.reply,
                can_answer=value.response is None
                and value.girl.entity == str(viewer.user_id)
                and self.live(c, state, value),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        response: rules.Response,
        reply: str,
    ) -> dict[str, Any]:
        if (
            response not in ("answer", "decline")
            or (response == "answer" and not reply.strip())
            or len(reply) > 1200
        ):
            raise WorkflowError("Record the original Girl's actual answer or in-character refusal")

        def authorize(c: Connection) -> None:
            _, value = self._owned(c, viewer, identity)
            self._access(c, viewer, value.job)
            if value.girl.entity != str(viewer.user_id):
                raise WorkflowError("Only the actual addressed Girl chooses her response")

        def operation(c: Connection) -> dict[str, Any]:
            state, value = self._owned(c, viewer, identity)
            if (
                state.revision != expected
                or value.response is not None
                or self.game.pending_actions(c)
                or not self.live(c, state, value)
            ):
                raise WorkflowError("STALE_QUESTION: recover the unchanged original NPC and Girl")
            event = str(uuid4())
            rules.save(
                state,
                value.model_copy(
                    update=dict(response=response, reply=reply.strip(), response_event=event)
                ),
            )
            if response == "decline":
                sheet = state.sheets[value.girl.entity]
                sheet.tags.append(
                    TagState(
                        id=identity + ":tag",
                        label=value.tag,
                        giver=value.controller,
                        giver_actor=value.reporter,
                        observers=(value.controller, viewer.user_id),
                    )
                )
                sheet.revision += 1
            self.game.event(
                c,
                viewer.user_id,
                key,
                FAMILY_ANSWERED if value.job == "family" else ANSWERED,
                state,
                event_id=event,
                question_id=identity,
            )
            return dict(id=identity, response=response)

        return self.store._write(
            viewer,
            key,
            ANSWERED,
            dict(id=identity, expected=expected, response=response, reply=reply),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
