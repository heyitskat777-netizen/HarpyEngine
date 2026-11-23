"""Harpy-owned human appearance with explicit original-scene facilitation."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_mask as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_advancements import MASK
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_harpy_advancements import scene_harpy
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer


def _proof(c: Connection, game: GameService, mask: rules.Mask) -> None:
    history = t.m2["m2_state_history"]
    offered = mask.model_copy(update=dict(approval=None, review=None, ended=None))
    for identity, actor, kind, expected in (
        (mask.event, mask.controller, "offered", offered),
        (mask.approval, mask.facilitator, "approved", mask.model_copy(update=dict(ended=None))),
    ):
        if identity is None:
            continue
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.event_id == identity,
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "m3.harpy_mask_" + kind,
                t.events.c.actor_id == str(actor),
            )
        )
        if not raw or expected not in rules.records(GameState.model_validate_json(raw)):
            raise WorkflowError("Recover the original human appearance and source review")


def active(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, channel: int, scene: str
) -> rules.Mask | None:
    value = rules.active(state, actor, scene)
    if value is None:
        return None
    try:
        Access(game.store).require_specialist_rule(MASK)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    _proof(c, game, value)
    cast = _cast(game, c, state, channel)
    _, advancement = scene_harpy(game, c, state, value.controller, cast, actor, MASK)
    if (
        cast.id != value.scene
        or cast.facilitator != value.facilitator
        or advancement != value.advancement
        or MedicalService(game.store)._handler(c) != (value.facilitator, value.appointment)
    ):
        raise WorkflowError("Recover the original active Human Mask and cast")
    return value


class MaskService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.require_specialist_rule(MASK)

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
                "m3.harpy_mask",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        appearance: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            _, advance = scene_harpy(self.game, c, state, viewer.user_id, cast, actor, MASK)
            gm, appointment = MedicalService(self.store)._handler(c)
            if (
                state.revision != revision
                or cast.facilitator != gm
                or not 0 < len(appearance.strip()) <= 120
                or not 0 < len(account.strip()) <= 1200
                or any(
                    x.actor == actor and x.scene == cast.id and not x.ended
                    for x in rules.records(state)
                )
            ):
                raise WorkflowError(
                    "Describe a fresh original appearance in this facilitated scene"
                )
            event = str(uuid4())
            value = rules.Mask(
                event=event,
                scene=cast.id,
                channel=channel,
                actor=actor,
                controller=viewer.user_id,
                advancement=advance,
                appearance=appearance.strip(),
                account=account.strip(),
                facilitator=gm,
                appointment=appointment,
            )
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.harpy_mask_offered", state, event_id=event)
            return dict(id=event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.token,
                revision=revision,
                appearance=appearance,
                account=account,
            ),
            operation,
        )

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[rules.Mask, str], ...]:
        items = tuple(
            (x, "end" if x.approval else "review")
            for x in rules.records(state)
            if not x.ended
            and (viewer.user_id == x.controller if x.approval else viewer.user_id == x.facilitator)
        )
        if items:
            try:
                self._gate(c, viewer)
            except (ValueError, WorkflowError):
                return ()
        return items

    def _pending(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[rules.Mask, str]:
        item = next((x for x in self.tasks(c, state, viewer) if x[0].event == identity), None)
        if item is None:
            raise WorkflowError("This original Human Mask choice is unavailable")
        value, step = item
        if MedicalService(self.store)._handler(c) != (value.facilitator, value.appointment):
            raise WorkflowError("Recover the actual Human Mask facilitator")
        _proof(c, self.game, value)
        return value, step

    def get(
        self, viewer: GuildViewer, *, channel: int | None = None, identity: str | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity is None and channel is not None:
                return dict(step="offer", revision=state.revision)
            if identity is None:
                raise WorkflowError("Choose the original Human Mask")
            value, step = self._pending(c, state, viewer, identity)
            return dict(
                step=step,
                revision=state.revision,
                appearance=value.appearance,
                account=value.account,
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        step: str,
        allow: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            value, expected = self._pending(c, state, viewer, identity)
            if (
                revision != state.revision
                or step != expected
                or type(allow) is not bool
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Record the original Mask review or ending")
            event = str(uuid4())
            if step == "review" and allow:
                cast = _cast(self.game, c, state, value.channel)
                _, advance = scene_harpy(
                    self.game, c, state, value.controller, cast, value.actor, MASK
                )
                require_scene_clear(self.game, c, value.channel)
                if (
                    cast.id != value.scene
                    or cast.facilitator != value.facilitator
                    or advance != value.advancement
                ):
                    raise WorkflowError("Recover the original Harpy and source encounter")
                value = value.model_copy(update=dict(approval=event, review=account.strip()))
                kind = "approved"
            elif step == "review" or step == "end" and allow:
                value = value.model_copy(update=dict(ended=event))
                kind = "ended"
            else:
                raise WorkflowError("Choose to end the original appearance")
            rules.put(state, value)
            self.game.event(c, viewer.user_id, key, "m3.harpy_mask_" + kind, state, event_id=event)
            return dict(id=identity, event=event)

        return self._write(
            viewer,
            key,
            dict(id=identity, revision=revision, step=step, allow=allow, account=account),
            operation,
        )
