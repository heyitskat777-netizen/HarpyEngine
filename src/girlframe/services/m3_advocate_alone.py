"""Keep the question and original Girl's answer scoped to their actual scene."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_advocate_alone as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_frantic_breakdown import _history
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _private_scene(
    game: GameService, c: Connection, state: GameState, channel: int, handler: ActorRef
) -> tuple[dict[str, Any], ActorRef]:
    scene = game.scene(c, channel)
    handler_id = int(handler.entity)
    others = set(scene["participants"]) - {handler_id}
    if len(others) != 1 or handler_id not in scene["participants"]:
        raise WorkflowError("Join the actual one-on-one scene between the Advocate and a Girl")
    (owner,) = others
    if owner not in state.order or not HandlerService(game.store)._member(c, owner):
        raise WorkflowError("Only the original active Girl can be in this one-on-one scene")
    game.pilot_cast(c, state, scene, owners=(handler_id, owner))
    girl = current_ref(state, owner)
    game.character_binding(c, state, owner, require_current_profile=False)
    cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
    if cast is not None and tuple(x.actor for x in cast.roles) != (girl,):
        raise WorkflowError("Wait for a one-on-one scene with the original Girl alone")
    return scene, girl


def _current(
    game: GameService, c: Connection, state: GameState, identity: str, viewer: GuildViewer
) -> rules.Conversation:
    value = next((x for x in rules.records(state) if x.id == identity), None)
    if value is None or str(viewer.user_id) not in (value.handler.entity, value.girl.entity):
        raise WorkflowError("This conversation belongs to its original two participants")
    owned = active_book(game, c, state, book="Advocate", rule=rules.RULE)
    if owned is None or owned[0] != value.handler:
        raise WorkflowError("Recover the original Advocate and appointment")
    scene, girl = _private_scene(game, c, state, value.channel, value.handler)
    if scene["id"] != value.scene or girl != value.girl:
        raise WorkflowError("Reopen the original one-on-one scene with its original Girl")
    born = _history(game, c, value.event, "m3.advocate_question_asked")
    original = next((x for x in rules.records(born) if x.id == identity), None) if born else None
    if original != value.model_copy(update=dict(answer=None, effect=None)):
        raise WorkflowError("Recover the original privately asked question")
    return value


def stage_order(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    source: tuple[str, int, str],
    channel: int,
    target: int,
    text: str,
    order: str,
    event: str,
) -> None:
    identity, expected, tag = source
    Access(game.store).authorize(c, viewer, "plays")
    value = _current(game, c, state, identity, viewer)
    if (
        value.effect is not None
        or value.answer is None
        or state.revision != expected
        or value.handler.entity != str(viewer.user_id)
        or value.girl.entity != str(target)
        or value.channel != channel
        or (value.order == "silence" and text != "Do not tell anyone about this.")
        or not 1 <= len(tag.strip()) <= 120
    ):
        raise WorkflowError("Use the original owned answer and an unissued private order")
    answered = _history(game, c, value.answer.event, "m3.advocate_question_answered")
    if answered is None or value not in rules.records(answered):
        raise WorkflowError("Recover the original Girl's actual answer")
    token = ChoiceEngine(game).add_tag(
        state, {"data": {"participants": (viewer.user_id, target)}}, target, viewer.user_id, tag
    )
    token.giver_actor = value.handler
    rules.put(
        state,
        value.model_copy(update=dict(effect=rules.Effect(tag=token.id, order=order, event=event))),
    )


class AdvocateAloneService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)

        return self.store._write(
            viewer, key, kind, payload, operation, authorize=access, auto_audit=False
        )

    def ask(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        channel: int,
        question: str,
        order: rules.Order,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            canon = load_state(c, self.store.campaign_id)
            owned = active_book(self.game, c, canon, book="Advocate", rule=rules.RULE)
            if (
                owned is None
                or owned[0].entity != str(viewer.user_id)
                or canon.revision != expected
                or not 1 <= len(question.strip()) <= 1200
                or order not in ("amuse", "silence")
            ):
                raise WorkflowError(
                    "Only the original Advocate can choose these two private effects"
                )
            scene, girl = _private_scene(self.game, c, canon, channel, owned[0])
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("Finish the pending Play in this one-on-one scene")
            if any(
                x.scene == scene["id"] and x.handler == owned[0] and x.effect is None
                for x in rules.records(canon)
            ):
                raise WorkflowError("Continue the original unanswered or pending private Play")
            value = rules.Conversation(
                id=str(uuid4()),
                handler=owned[0],
                girl=girl,
                channel=channel,
                scene=scene["id"],
                event=str(uuid4()),
                question=question.strip(),
                order=order,
            )
            rules.put(canon, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.advocate_question_asked",
                canon,
                event_id=value.event,
                conversation=value.id,
            )
            return dict(id=value.id, revision=canon.revision)

        return self._write(
            viewer,
            key,
            "m3.advocate_question_asked",
            dict(expected=expected, channel=channel, question=question, order=order),
            operation,
        )

    def answer(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, text: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            canon = load_state(c, self.store.campaign_id)
            value = _current(self.game, c, canon, identity, viewer)
            if (
                value.girl.entity != str(viewer.user_id)
                or canon.revision != expected
                or value.answer is not None
                or not 1 <= len(text.strip()) <= 1200
            ):
                raise WorkflowError("Only the original Girl can supply her own answer once")
            event = str(uuid4())
            rules.put(
                canon,
                value.model_copy(update=dict(answer=rules.Answer(text=text.strip(), event=event))),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.advocate_question_answered",
                canon,
                event_id=event,
                conversation=identity,
            )
            return dict(id=identity, revision=canon.revision)

        return self._write(
            viewer,
            key,
            "m3.advocate_question_answered",
            dict(id=identity, expected=expected, text=text),
            operation,
        )

    def _tasks(
        self, c: Connection, viewer: GuildViewer, state: GameState
    ) -> list[tuple[str, bool]]:
        tasks = []
        for value in rules.records(state):
            owner = value.handler if value.answer else value.girl
            if value.effect is not None or owner.entity != str(viewer.user_id):
                continue
            try:
                _current(self.game, c, state, value.id, viewer)
            except WorkflowError:
                continue
            tasks.append((value.id, bool(value.answer)))
        return tasks

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "plays")
            canon = load_state(c, self.store.campaign_id)
            value = _current(self.game, c, canon, identity, viewer)
            return dict(
                revision=canon.revision,
                question=value.question,
                answer=value.answer.text if value.answer else None,
                issued=value.effect is not None,
                handler=value.handler.entity == str(viewer.user_id),
                channel=value.channel,
                target=int(value.girl.entity),
                order=value.order if value.handler.entity == str(viewer.user_id) else None,
            )

    def issue(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, message: str, tag: str
    ) -> dict[str, Any]:
        payload = self.get(viewer, identity)
        if not payload["handler"]:
            raise WorkflowError("Only the original Advocate issues this private order")
        if payload["order"] == "silence":
            if message:
                raise WorkflowError("Use the printed nondisclosure order")
            message = "Do not tell anyone about this."
        return self.game.issue_order(
            viewer,
            key,
            payload["channel"],
            payload["target"],
            message,
            advocate_conversation=(identity, expected, tag),
        )
