"""Daily original-Mentor companion and fictional callsign authority."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_mentor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.shared_setup import CallsignChoice
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_malleable import _audit
from girlframe.services.m3_mentorship import original_mentor
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _person(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if (
        actor.kind != "pilot"
        or actual.rules != "girl_frame"
        or actual.offstage_source is not None
        or actual.custody not in (None, "free")
    ):
        raise WorkflowError("Recover the actual original available native Girl role")
    return actual


def required_companions(
    game: GameService,
    c: Connection,
    state: GameState,
    participants: tuple[int, ...],
    *,
    present_actors: tuple[ActorRef, ...],
) -> tuple[int, ...]:
    """Only genuine participating Pilot people trigger their actual companion, never controllers."""
    people = list(participants)
    actual = set(present_actors)
    if any(
        x.kind != "pilot"
        or int(x.entity) not in participants
        or x != current_ref(state, int(x.entity))
        for x in present_actors
    ):
        raise WorkflowError("Bind actual original Pilot participants before Mentor companions")
    while True:
        added = False
        for sheet in state.sheets.values():
            if (
                not has_rule(sheet, rules.RULE, "NEWGIRL")
                or sheet.mentor is None
                or sheet.mentor not in {int(x.entity) for x in actual}
            ):
                continue
            learner = current_ref(state, sheet.owner)
            mentor, _ = original_mentor(game, c, state, learner)
            if mentor not in actual:
                raise WorkflowError("Recover the actual original Mentor role; no account alias")
            _person(game, c, state, mentor)
            _person(game, c, state, learner)
            if sheet.owner in people and learner not in actual:
                raise WorkflowError(
                    "MENTOR_COMPANION_ROLE_REQUIRED: bind the actual Newgirl Pilot role explicitly"
                )
            if learner not in actual:
                actual.add(learner)
                added = True
            if sheet.owner not in people:
                people.append(sheet.owner)
        if not added:
            return tuple(people)


def prove_naming(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Naming:
    value = next((x for x in rules.records(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the genuine original Mentor's actual name choice")
    born = _history(c, game, value.event)
    _audit(game, c, value.event, "m3.mentor_callsign", int(value.mentor.entity))
    mentor, source = original_mentor(game, c, born, value.learner)
    if (
        value not in rules.records(born)
        or mentor != value.mentor
        or source != value.assignment
        or born.sheets[value.learner.entity].callsign != value.callsign
    ):
        raise WorkflowError("Prove the actual original Mentor-authored fictional callsign")
    return value


class MentorService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def name(
        self, viewer: GuildViewer, key: str, learner: ActorRef, expected: int, callsign: str
    ) -> dict[str, Any]:
        chosen = CallsignChoice(callsign=callsign).callsign

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_recovery import pending as interrupted

            if (
                state.revision != expected
                or self.game.pending_actions(c)
                or interrupted(self.game, c, include_unrolled=True)
            ):
                raise WorkflowError("Finish pending Plays and reopen current Mentor name controls")
            mentor, assignment = original_mentor(self.game, c, state, learner)
            actual = _person(self.game, c, state, mentor)
            _person(self.game, c, state, learner)
            if viewer.user_id != actual.controller or current_ref(state, viewer.user_id) != mentor:
                raise WorkflowError(
                    "Only this actual original Mentor chooses its Newgirl's callsign"
                )
            event = str(uuid4())
            changed = rules.rename(state, learner, mentor, assignment, chosen, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mentor_callsign",
                changed,
                event_id=event,
                learner=learner.model_dump(mode="json"),
            )
            return dict(id=event, callsign=chosen)

        return self.store._write(
            viewer,
            key,
            "m3.mentor_callsign",
            dict(learner=learner.model_dump(mode="json"), expected=expected, callsign=chosen),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            learners = []
            own = None
            for sheet in state.sheets.values():
                if not has_rule(sheet, rules.RULE, "NEWGIRL"):
                    continue
                learner = current_ref(state, sheet.owner)
                try:
                    mentor, _ = original_mentor(self.game, c, state, learner)
                except (ValueError, WorkflowError):
                    continue
                if mentor.entity == str(viewer.user_id):
                    learners.append(dict(ref=learner.model_dump(mode="json"), label=sheet.callsign))
                if learner.entity == str(viewer.user_id):
                    own = dict(
                        ref=learner.model_dump(mode="json"),
                        callsign=sheet.callsign,
                        mentor=state.sheets[mentor.entity].callsign,
                    )
            return dict(
                revision=state.revision, learners=learners, own=own, history=self._tasks(c, viewer)
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove_naming(self.game, c, state, identity)
            if viewer.user_id not in (int(value.learner.entity), int(value.mentor.entity)):
                raise WorkflowError(
                    "Only the original Mentor and Newgirl read this private name history"
                )
            return dict(
                id=value.id,
                learner=value.learner.model_dump(mode="json"),
                before=value.before,
                callsign=value.callsign,
                can_sync=viewer.user_id == int(value.learner.entity)
                and value.learner == current_ref(state, viewer.user_id),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                label="Your original Mentor's callsign choice: " + x.callsign,
                revision=state.revision,
                pending=False,
            )
            for x in rules.records(state)
            if viewer.user_id in (int(x.learner.entity), int(x.mentor.entity))
        ]
