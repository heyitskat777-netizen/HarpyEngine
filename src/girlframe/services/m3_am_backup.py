"""Private genuine backup recovery and original-AM-owned transactional reversion."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_backup as rules
from girlframe.engine import m3_am_code as code
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_am_memory import losses
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Backup:
    from girlframe.services.m3_am_scrutinized import _history

    value = rules.backup(state, identity)
    original = _history(game, c, value.event)
    saved = rules.backup(original, identity)
    maintenance = code.session(state, value.maintenance)
    created = code.session(original, value.maintenance)
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    response = c.execute(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == value.event,
            responses.c.actor_id == str(maintenance.controller),
            choices.c.kind == "am_code_options",
            choices.c.action_id == value.action,
        )
    ).first()
    baseline = rules.latest(original, value.actor)
    if (
        value != saved
        or maintenance.backup != value.id
        or created.backup != value.id
        or maintenance.actor != value.actor
        or maintenance.operator != value.operator
        or maintenance.action != value.action
        or value.captured_revision != original.revision - 1
        or value.identities != tuple(original.sheets[value.actor.entity].identities)
        or value.memory_losses != losses(original, value.actor)
        or value.memory_baseline != (baseline.id if baseline else None)
        or response is None
        or "backup" not in json.loads(response.answer_json).get("options", ())
        or game.action(c, value.action)["data"]["result"]["tier"] not in ("mid", "high")
    ):
        raise WorkflowError(
            "Recover the actual operator-created immutable Identity/memory snapshot"
        )
    return value


def prove_reversion(
    game: GameService, c: Connection, state: GameState, value: rules.Reversion
) -> None:
    from girlframe.services.m3_am_scrutinized import _history

    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    original = _history(game, c, value.event)
    if (
        event is None
        or event.kind != "m3.am_backup_reverted"
        or event.actor_id != str(value.owner)
        or value not in rules.reversions(original, value.actor)
        or value.through_revision != original.revision - 1
        or value.actor != rules.backup(state, value.backup).actor
    ):
        raise WorkflowError("Recover the original AM's actual immutable reversion event")


class BackupService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _get(
        self, c: Connection, viewer: GuildViewer, state: GameState, identity: str, *, owner: bool
    ) -> rules.Backup:
        from girlframe.services.m3_am_code import source

        value = rules.backup(state, identity)
        maintenance = code.session(state, value.maintenance)
        allowed = (maintenance.owner,) if owner else (maintenance.owner, maintenance.controller)
        if viewer.user_id not in allowed:
            raise WorkflowError("This genuine backup belongs to its original AM and source humans")
        value = prove(self.game, c, state, identity)
        source(self.game, c, state, value.maintenance)
        for previous in rules.reversions(state, value.actor):
            prove_reversion(self.game, c, state, previous)
        if owner:
            actual = resolve(state, value.actor, profiles(c, self.store.campaign_id))
            if actual.girl != "AM" or not has_rule(
                state.sheets[value.actor.entity], code.RULE, "AM"
            ):
                raise WorkflowError("Only this same current original native AM can revert")
        return value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = self._get(c, viewer, state, identity, owner=False)
            return dict(
                id=value.id,
                actor=value.actor.model_dump(mode="json"),
                captured_revision=value.captured_revision,
                identities=[x.model_dump(mode="json") for x in value.identities],
                memory_losses=[x.model_dump(mode="json") for x in value.memory_losses],
                memory_baseline=value.memory_baseline,
                event=value.event,
            )

    def preview(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = self._get(c, viewer, state, identity, owner=True)
            identities, retained = rules.plan(state, value)
            last = rules.latest(state, value.actor)
            return dict(
                id=value.id,
                revision=state.revision,
                captured_revision=value.captured_revision,
                identities=[x.model_dump(mode="json") for x in identities],
                retained=[x.model_dump(mode="json") for x in retained],
                latest_reversion=last.model_dump(mode="json") if last else None,
            )

    def restore(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._get(c, viewer, state, identity, owner=True)
            locks = t.m2["m2_locks"]
            locked = c.scalar(
                sa.select(locks.c.channel_id)
                .where(
                    locks.c.campaign_id == self.store.campaign_id,
                    locks.c.state != "released",
                )
                .limit(1)
            )
            if state.revision != expected or self.game.pending_actions(c) or locked:
                raise WorkflowError(
                    "Recover current owned actions/scene locks and the exact backup preview first"
                )
            event = str(uuid4())
            changed, reversion = rules.restore(state, value.id, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_backup_reverted",
                changed,
                event_id=event,
                backup=value.id,
                reversion=reversion.id,
            )
            return dict(
                id=reversion.id,
                backup=value.id,
                captured_revision=value.captured_revision,
                retained=[x.model_dump(mode="json") for x in reversion.retained],
            )

        return self.store._write(
            viewer,
            key,
            "m3.am_backup_reverted",
            dict(id=identity, expected=expected),
            operation,
            authorize=lambda c: access(self.game, c, viewer),
            auto_audit=False,
        )
