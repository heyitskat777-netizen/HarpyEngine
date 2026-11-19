"""Private native NPC requests and their source-bound mechanical consequences."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_journalist as rules
from girlframe.engine.m2 import GameState, IdentityState, PilotSheet, TagState
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
PSYCHOLOGIST_DIRECTIVE = "m3.psychologist_directive"
PSYCHOLOGIST_IDENTITY = "m3.psychologist_identity_received"
EXPECTATION_SET = "m3.public_relations_expectation_set"
EXPECTATION_ANSWERED = "m3.public_relations_expectation_answered"
SOURCE_EVENTS: dict[rules.Job, str] = {
    "journalist": ASKED,
    "family": FAMILY_ASKED,
    "psychologist": PSYCHOLOGIST_DIRECTIVE,
    "public_relations": EXPECTATION_SET,
}
RESULT_EVENTS: dict[rules.Job, str] = {
    "journalist": ANSWERED,
    "family": FAMILY_ANSWERED,
    "psychologist": PSYCHOLOGIST_IDENTITY,
    "public_relations": EXPECTATION_ANSWERED,
}


def identity_slots(sheet: PilotSheet) -> tuple[bool, tuple[tuple[str, str], ...]]:
    ordinary = sum(not x.protected or x.paired or bool(x.am_limiter) for x in sheet.identities)
    allowed = tuple(
        (x.id, x.name)
        for x in sheet.identities
        if not (
            x.protected
            or x.paired
            or x.am_limiter
            or x.obsession_sources
            or x.id in sheet.sedation_locked
        )
    )
    return ordinary >= 4, allowed if ordinary >= 4 else ()


def marked_identities(state: GameState, sheet: PilotSheet) -> tuple[tuple[str, str], ...]:
    from girlframe.engine.m3_clone_am import additional_identities
    from girlframe.engine.m3_oldgen import marked_maxims

    return (
        tuple(
            (x.id, x.name)
            for x in sheet.identities
            if x.marked and x.id not in sheet.sedation_locked
        )
        + tuple((x.id, x.name) for x in additional_identities(state, sheet.owner) if x.marked)
        + marked_maxims(state, sheet.owner)
    )


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
        identity_label: str | None = None,
    ) -> dict[str, Any]:
        if job not in SOURCE_EVENTS:
            raise WorkflowError("Choose the actual original NPC job")
        if job == "psychologist":
            if tag or identity_label is None or not 0 < len(identity_label.strip()) <= 120:
                raise WorkflowError(
                    "Record the actual new Identity for the Psychologist's directive"
                )
        elif identity_label is not None or not 0 < len(tag.strip()) <= 120:
            raise WorkflowError("Provide the actual prompt and its conditional Tag")
        if not 0 < len(question.strip()) <= 1200:
            raise WorkflowError("Record the actual original NPC's instruction or prompt")
        kind = SOURCE_EVENTS[job]

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
                    tag=tag.strip() if tag else None,
                    job=job,
                    identity_label=identity_label.strip() if identity_label is not None else None,
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
            | (dict(job=job) if job != "journalist" else {})
            | (dict(identity_label=identity_label) if identity_label is not None else {}),
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
                t.events.c.kind == SOURCE_EVENTS[value.job],
                t.events.c.actor_id == str(value.controller),
            )
        )
        first = GameState.model_validate_json(raw) if raw else None
        if first is None or value.model_copy(
            update=dict(
                response=None,
                reply=None,
                response_event=None,
                replaced_identity=None,
                unmarked_identity=None,
            )
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
            can_answer = (
                value.response is None
                and value.girl.entity == str(viewer.user_id)
                and self.live(c, state, value)
            )
            needs_replacement, replacements = (
                identity_slots(state.sheets[value.girl.entity])
                if (value.job == "psychologist" and can_answer)
                else (False, ())
            )
            return dict(
                revision=state.revision,
                question=value.question,
                job=value.job,
                response=value.response,
                reply=value.reply,
                can_answer=can_answer,
                identity_label=value.identity_label,
                needs_replacement=needs_replacement,
                replacements=replacements,
                marked_identities=(
                    marked_identities(state, state.sheets[value.girl.entity])
                    if value.job == "public_relations" and can_answer
                    else ()
                ),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        response: rules.Response,
        reply: str,
        *,
        replace: str | None = None,
        unmark: str | None = None,
    ) -> dict[str, Any]:
        if response not in ("answer", "decline") or len(reply) > 1200:
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
            if unmark is not None and (value.job != "public_relations" or response != "answer"):
                raise WorkflowError("Only meeting the actual expectation unmarks an Identity")
            event = str(uuid4())
            if value.job == "psychologist":
                if response != "answer":
                    raise WorkflowError(
                        "The original Identity request remains pending for human review"
                    )
                assert value.identity_label is not None
                self._receive_identity(state, value, replace)
            elif replace is not None or (
                (response == "answer" or value.job == "public_relations") and not reply.strip()
            ):
                raise WorkflowError(
                    "Record the original Girl's actual answer or in-character refusal"
                )
            if value.job == "public_relations" and response == "answer":
                from girlframe.services.m2_choices import ChoiceEngine

                sheet = state.sheets[value.girl.entity]
                if unmark is None or unmark not in dict(marked_identities(state, sheet)):
                    raise WorkflowError("Choose an eligible marked Identity owned by this Girl")
                ChoiceEngine(self.game).unmark(c, state, sheet, (unmark,), 1)
                sheet.revision += 1
            rules.save(
                state,
                value.model_copy(
                    update=dict(
                        response=response,
                        reply=reply.strip(),
                        response_event=event,
                        replaced_identity=replace,
                        unmarked_identity=unmark,
                    )
                ),
            )
            if response == "decline":
                sheet = state.sheets[value.girl.entity]
                assert value.tag is not None
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
                RESULT_EVENTS[value.job],
                state,
                event_id=event,
                question_id=identity,
            )
            return dict(id=identity, response=response)

        return self.store._write(
            viewer,
            key,
            ANSWERED,
            dict(id=identity, expected=expected, response=response, reply=reply)
            | (dict(replace=replace) if replace is not None else {})
            | (dict(unmark=unmark) if unmark is not None else {}),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def _receive_identity(
        self, state: GameState, value: rules.Question, replace: str | None
    ) -> None:
        from girlframe.engine.m3_identity_slots import replacement_slot
        from girlframe.services.m2_choices import ChoiceEngine
        from girlframe.services.m3_ankou_support import erase_identity

        sheet = state.sheets[value.girl.entity]
        needs_replacement, candidates = identity_slots(sheet)
        if (needs_replacement and replace not in dict(candidates)) or (
            not needs_replacement and replace is not None
        ):
            raise WorkflowError("Use an eligible own Identity slot only when capacity requires it")
        label = value.identity_label
        assert label is not None
        if not ChoiceEngine(self.game).duplicate_labels() and any(
            x.id != replace and x.name.casefold() == label.casefold() for x in sheet.identities
        ):
            raise WorkflowError("Duplicate Identity labels require the approved campaign ruling")
        slot = replacement_slot(sheet, replace)
        if replace is not None:
            erase_identity(state, value.girl, replace)
        sheet.identities.append(IdentityState(id=value.id + ":identity", name=label, slot=slot))
        sheet.revision += 1
