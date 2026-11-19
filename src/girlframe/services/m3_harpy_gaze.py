"""Owned eye-contact choices and a Tag from a broken original promise."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_advancements import MANIC_PIXIE
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_advancements import advancement_source, scene_harpy
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "harpy_gaze"
CHOICES = {
    "hands": "Take the Harpy’s hands",
    "promise": "Make a promise",
    "focus": "Lose track of everything else",
}


class Gaze(Model):
    event: str
    scene: str
    channel: int
    harpy: ActorRef
    controller: int
    advancement: str
    target: ActorRef
    target_controller: int
    account: str
    choices: tuple[str, ...] = ()
    reply: str | None = None
    promise: str | None = None
    response: str | None = None
    broken: str | None = None
    tagged: str | None = None


def records(state: GameState) -> tuple[Gaze, ...]:
    return tuple(Gaze.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


class GazeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(MANIC_PIXIE)

    def _targets(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
        source: ActorView,
    ) -> dict[str, ActorView]:
        bound = profiles(c, self.store.campaign_id)
        result = {}
        for role in cast.roles:
            if role.actor.kind != "pilot":
                continue
            girl = resolve(state, role.actor, bound, require_current_profile=False)
            if (
                girl.alive
                and girl.rules == "girl_frame"
                and girl.controller == role.controller
                and girl.controller != source.controller
                and girl.offstage_source is None
                and girl.cell == source.cell
                and girl.inside_frame is False
            ):
                result[girl.ref.token] = girl
        return result

    def targets(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            source, _ = scene_harpy(self.game, c, state, viewer.user_id, cast, actor, MANIC_PIXIE)
            return dict(
                revision=state.revision,
                targets={
                    key: target.label
                    for key, target in self._targets(c, state, cast, source).items()
                },
            )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_gaze_choice",
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._gate(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _persist(
        self,
        c: Connection,
        state: GameState,
        case: Gaze,
        event: str,
        viewer: GuildViewer,
        key: str,
        step: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.event)]
        state.facts.append(dict(kind=KIND, id=case.event, body=case.model_dump_json()))
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.harpy_gaze_" + step,
            state,
            event_id=event,
            source=case.event,
        )
        return dict(id=case.event, event=event)

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or not 0 < len(account.strip()) <= 1200:
                raise WorkflowError("Reopen the actual gaze and describe the encounter")
            cast = _cast(self.game, c, state, channel)
            source, receipt = scene_harpy(
                self.game, c, state, viewer.user_id, cast, actor, MANIC_PIXIE
            )
            actual = self._targets(c, state, cast, source).get(target)
            if actual is None or any(
                x.harpy == actor and x.target == actual.ref and not x.response
                for x in records(state)
            ):
                raise WorkflowError("Use the actual present girl and original gaze")
            event = str(uuid4())
            case = Gaze(
                event=event,
                scene=cast.id,
                channel=channel,
                harpy=actor,
                controller=source.controller,
                advancement=receipt,
                target=actual.ref,
                target_controller=actual.controller,
                account=account.strip(),
            )
            return self._persist(c, state, case, event, viewer, key, "offered")

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                revision=revision,
                target=target,
                account=account,
            ),
            operation,
        )

    def _step(self, state: GameState, case: Gaze, viewer: GuildViewer) -> str | None:
        if viewer.user_id != case.target_controller and not (
            viewer.user_id == case.controller and case.broken and not case.tagged
        ):
            return None
        original = state.sheets.get(case.target.entity)
        if original is None or original.character_id != case.target.incarnation:
            return None
        if viewer.user_id == case.target_controller:
            return (
                "choose"
                if not case.response
                else "break"
                if case.promise and not case.broken
                else None
            )
        return "tag"

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[Gaze, str], ...]:
        pending = tuple((x, step) for x in records(state) if (step := self._step(state, x, viewer)))
        if pending:
            try:
                self._gate(c, viewer)
            except (WorkflowError, ValueError):
                return ()
        return pending

    def _case(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Gaze, str]:
        case = next((x for x in records(state) if x.event == identity), None)
        step = self._step(state, case, viewer) if case else None
        if case is None or step is None:
            raise WorkflowError("This private original gaze decision is unavailable")
        history = t.m2["m2_state_history"]

        def receipt(event: str, kind: str, author: int) -> Gaze | None:
            raw = c.scalar(
                sa.select(history.c.body_json)
                .join(t.events, t.events.c.id == history.c.event_id)
                .where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == event,
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "m3.harpy_gaze_" + kind,
                    t.events.c.actor_id == str(author),
                )
            )
            return (
                next(
                    (x for x in records(GameState.model_validate_json(raw)) if x.event == identity),
                    None,
                )
                if raw
                else None
            )

        original = case.model_copy(
            update=dict(
                choices=(), reply=None, promise=None, response=None, broken=None, tagged=None
            )
        )
        if (
            receipt(case.event, "offered", case.controller) != original
            or (
                case.response
                and receipt(case.response, "choose", case.target_controller)
                != case.model_copy(update=dict(broken=None, tagged=None))
            )
            or (
                case.broken
                and receipt(case.broken, "break", case.target_controller)
                != case.model_copy(update=dict(tagged=None))
            )
        ):
            raise WorkflowError("Recover the actual original gaze and promise receipts")
        return case, step

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case, step = self._case(c, state, viewer, identity)
            return dict(
                revision=state.revision, step=step, account=case.account, promise=case.promise
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        *,
        choices: tuple[str, ...] = (),
        account: str = "",
        promise: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            case, expected = self._case(c, state, viewer, identity)
            if state.revision != revision or step != expected:
                raise WorkflowError("Reopen the actual original choice")
            event = str(uuid4())
            if step == "choose":
                cast = _cast(self.game, c, state, case.channel)
                source, receipt = scene_harpy(
                    self.game,
                    c,
                    state,
                    case.controller,
                    cast,
                    case.harpy,
                    MANIC_PIXIE,
                )
                if (
                    len(set(choices)) != 2
                    or len(choices) != 2
                    or not set(choices) <= set(CHOICES)
                    or ("promise" in choices) != bool(promise.strip())
                    or not 0 < len(account.strip()) <= 1200
                    or len(promise.strip()) > 1200
                    or cast.id != case.scene
                    or receipt != case.advancement
                    or case.target.token not in self._targets(c, state, cast, source)
                ):
                    raise WorkflowError(
                        "Make two actual original gaze choices with the owned consequences"
                    )
                updated = case.model_copy(
                    update=dict(
                        choices=choices,
                        reply=account.strip(),
                        promise=promise.strip() or None,
                        response=event,
                    )
                )
            elif step == "break" and not (choices or account or promise):
                updated = case.model_copy(update=dict(broken=event))
            elif step == "tag" and not choices and not promise and 0 < len(account.strip()) <= 1200:
                harpy = resolve(
                    state,
                    case.harpy,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if (
                    not harpy.alive
                    or harpy.controller != case.controller
                    or advancement_source(
                        self.game,
                        c,
                        state,
                        case.harpy,
                        case.controller,
                        MANIC_PIXIE,
                    )
                    != case.advancement
                ):
                    raise WorkflowError(
                        "Use the original living Harpy that heard the broken promise"
                    )
                state = give_tag(
                    state,
                    case.target,
                    case.harpy,
                    account.strip(),
                    event,
                    "gaze:" + identity,
                    tuple(sorted({case.controller, case.target_controller})),
                )
                updated = case.model_copy(update=dict(tagged=event))
            else:
                raise WorkflowError("Use the original owned response to this gaze or promise")
            return self._persist(c, state, updated, event, viewer, key, step)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                step=step,
                choices=choices,
                account=account,
                promise=promise,
            ),
            operation,
        )
