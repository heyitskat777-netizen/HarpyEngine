"""Own the Dogrunner's physical and delegated steps before applying their Status effects."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_dogrunner_dress as rules
from girlframe.engine import m3_handler_plays as handler_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_play_state import DRESS_CONTACTS, DRESS_RULE, Effect, HandlerPlay
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import Access
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_handler_plays import (
    HandlerPlayService,
    _authority,
    _ordinary_scene_idle,
    _source,
    source_labels,
)
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.dogrunner_dress_performance"


def _delegate_owner(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay, effect: Effect
) -> int | None:
    assert effect.target is not None
    scenes = t.m2["m2_scenes"]
    channel = c.scalar(
        sa.select(scenes.c.channel_id).where(
            scenes.c.campaign_id == game.store.campaign_id,
            scenes.c.id == grant.scope.scene_id,
            scenes.c.open.is_(True),
        )
    )
    if channel is None:
        raise WorkflowError("Recover this Dress Them Down's original scene")
    cast = _cast(game, c, state, int(channel))
    subject = next((role for role in cast.roles if role.actor == effect.target), None)
    setup = HandlerService(game.store)
    if (
        subject is None
        or subject.controller != int(effect.target.entity)
        or not setup._member(c, subject.controller)
    ):
        raise WorkflowError("Recover the original Girl and her controller in this scene")
    if effect.dress_delegate is None:
        return None
    part = next((role for role in cast.roles if role.actor == effect.dress_delegate), None)
    if (
        part is None
        or part.controller in (grant.chooser_controller, subject.controller)
        or not setup._member(c, part.controller)
        or not _visible(state, part.actor, grant.chooser_controller)
    ):
        raise WorkflowError(
            "Choose a visible separate participant with their own original controller"
        )
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    if (
        resolve(
            state, part.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller
        != part.controller
    ):
        raise WorkflowError("Recover the delegated participant's original controller")
    return part.controller


def require_performed(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay, effect: Effect
) -> None:
    record = rules.performances(state).get(grant.id)
    if not effect.dress_needs_performance and (record is None or record.phase == "declined"):
        return
    if (
        record is None
        or record.phase != "ready"
        or record.effect != effect
        or rules.performances(_history(c, game, record.event)).get(grant.id) != record
    ):
        raise WorkflowError(
            "Resume this exact Dress Them Down after the participants finish their steps"
        )
    if _delegate_owner(game, c, state, grant, effect) != record.delegate_owner:
        raise WorkflowError("Recover the actual original delegated controller")


class DressPerformanceService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, EVENT, payload, operation, auto_audit=False, authorize=authorize
            )
        except ValueError as exc:
            raise WorkflowError(str(exc)) from None

    def propose(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, effect: Effect
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, grant = _source(c, self.game, identity)
            _authority(c, self.game, state, grant)
            _ordinary_scene_idle(c, self.game)
            existing = rules.performances(state).get(identity)
            if (
                state.revision != expected
                or grant.clause != DRESS_RULE
                or grant.state != "pending"
                or grant.chooser_controller != viewer.user_id
                or not effect.dress_needs_performance
                or (existing is not None and existing.phase != "declined")
                or (
                    effect.source_label is not None
                    and effect.source_label not in dict(source_labels(state, grant))
                )
            ):
                raise WorkflowError(
                    "Reopen the original Dogrunner Play or its pending performances"
                )
            event = str(uuid4())
            proposed = handler_rules.select(state, identity, "dress_them_down", effect, event)
            handler_rules.direct(
                proposed, identity, event
            )  # Validate the rank and Tag before asking.
            from girlframe.services.m3_wyvern_combat import require_targetable

            assert effect.target is not None
            require_targetable(self.game, c, state, effect.target)
            delegate = _delegate_owner(self.game, c, state, grant, effect)
            record = rules.Performance(
                grant=identity,
                effect=effect,
                event=event,
                phase="delegate" if delegate is not None else "contact",
                delegate_owner=delegate,
            )
            rules.save(state, record)
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event, grant=identity)
            return dict(id=identity, state="awaiting_performers", phase=record.phase)

        return self._write(
            viewer,
            key,
            dict(id=identity, expected=expected, effect=effect.model_dump(mode="json")),
            operation,
        )

    def _details(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Performance]:
        state, grant = _source(c, self.game, identity)
        _authority(c, self.game, state, grant)
        record = rules.performances(state).get(identity)
        if (
            grant.state != "pending"
            or record is None
            or record.phase == "declined"
            or rules.performances(_history(c, self.game, record.event)).get(identity) != record
        ):
            raise WorkflowError("This original Dress Them Down performance is unavailable")
        delegate = _delegate_owner(self.game, c, state, grant, record.effect)
        if delegate != record.delegate_owner:
            raise WorkflowError("Recover the actual original delegated controller")
        target = record.effect.target
        assert target is not None
        owner = (
            delegate
            if record.phase == "delegate"
            else int(target.entity)
            if record.phase == "contact"
            else grant.chooser_controller
        )
        if owner != viewer.user_id:
            raise WorkflowError("Only the original participant owns this performance choice")
        return state, record

    def tasks(self, c: Connection, viewer: GuildViewer, state: GameState) -> list[str]:
        visible = []
        for identity in rules.performances(state):
            try:
                self._details(c, viewer, identity)
            except WorkflowError:
                continue
            visible.append(identity)
        return visible

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state, record = self._details(c, viewer, identity)
            contacts = tuple(
                key
                for key in (record.effect.dress_contact, record.delegate_choice)
                if key in dict(DRESS_CONTACTS)
            )
            target = record.effect.target
            assert target is not None
            return dict(
                revision=state.revision,
                phase=record.phase,
                contacts=contacts,
                target=state.sheets[target.entity].callsign,
            )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, step: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, record = self._details(c, viewer, identity)
            _ordinary_scene_idle(c, self.game)
            if state.revision != expected or record.phase == "ready":
                raise WorkflowError("Reopen your exact current performance choice")
            if step == "decline" and not account.strip():
                update: dict[str, Any] = dict(phase="declined")
            elif not 1 <= len(account.strip()) <= 1200:
                raise WorkflowError("Describe the actual performed step")
            elif record.phase == "delegate" and step in dict(rules.DELEGATE_OPTIONS):
                phase = (
                    "contact"
                    if record.effect.dress_contact or step in dict(DRESS_CONTACTS)
                    else "ready"
                )
                update = dict(phase=phase, delegate_choice=step, delegate_account=account.strip())
            elif record.phase == "contact" and step == "performed":
                update = dict(phase="ready", contact_account=account.strip())
            else:
                raise WorkflowError("Use the exact option for this owned performance")
            event = str(uuid4())
            rules.save(state, record.model_copy(update=update | dict(event=event)))
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event, grant=identity)
            return dict(id=identity, phase=update["phase"])

        return self._write(
            viewer, key, dict(id=identity, expected=expected, step=step, account=account), operation
        )

    def finish(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        # The actual transactional Play path rechecks the accepted original plan.
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state, grant = _source(c, self.game, identity)
            record = rules.performances(state).get(identity)
            if (
                grant.chooser_controller != viewer.user_id
                or record is None
                or record.phase != "ready"
            ):
                raise WorkflowError("Only the original Dogrunner can finish this performed Play")
        return HandlerPlayService(self.store).submit(
            viewer,
            key,
            identity,
            expected,
            "dress_them_down",
            record.effect,
            performed=True,
        )
