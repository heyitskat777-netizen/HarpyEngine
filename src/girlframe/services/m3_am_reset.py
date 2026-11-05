"""Owned fourth-Limiter endpoint, reusing real career and source-work authorities."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am as am
from girlframe.engine import m3_am_reset as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def schedule(state: GameState, identity: str) -> bool:
    """Allocate source work before its installation event; no fabricated result or dice."""
    value = am.discovery(state, identity)
    if len(am.limiters(state, value.actor)) != 4:
        return False
    if not rules.eligible(state, value.actor) or value.reset_work or value.factory_reset:
        raise WorkflowError(
            "AM_RESET_REQUIRED: this actual body needs its supported transfer source"
        )
    am.put(state, value.model_copy(update=dict(phase="reset_pending", reset_work=str(uuid4()))))
    return True


def materialize(
    game: GameService, c: Connection, state: GameState, identity: str, event: str
) -> None:
    from girlframe.services.m3_work import related

    value = am.discovery(state, identity)
    if value.phase != "reset_pending" or value.reset_work is None:
        return
    work = t.m3["m3_required_work"]
    if c.scalar(
        sa.select(work.c.id).where(
            work.c.campaign_id == game.store.campaign_id, work.c.id == value.reset_work
        )
    ):
        return
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, scene_id=value.cast.id),
        value.reset_work,
        value.handler_controller,
        value.caster,
        "am_factory_reset",
        dict(
            discovery=identity,
            character=value.actor.incarnation,
            immediate=True,
            actor=value.actor.model_dump(mode="json"),
        ),
        event,
    )


class FactoryResetService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _pending(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, am.Discovery, dict[str, Any], am.Limiter]:
        from girlframe.services.m3_am_scrutinized import _access, _history, _prove_effect, source

        _access(self.game, c, viewer)
        state = load_state(c, self.store.campaign_id)
        value = source(self.game, c, state, identity)
        _prove_effect(self.game, c, value)
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == self.store.campaign_id, work.c.id == value.reset_work)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if (
            viewer.user_id != value.handler_controller
            or viewer.user_id != state.handler
            or value.phase != "reset_pending"
            or value.factory_reset
            or not value.limiter
            or row is None
            or row["state"] != "pending"
            or row["kind"] != "am_factory_reset"
            or row["owner_id"] != str(viewer.user_id)
            or json.loads(row["body_json"]).get("discovery") != identity
            or len(am.limiters(state, value.actor)) != 4
            or not rules.eligible(state, value.actor)
        ):
            raise WorkflowError("Only the actual Handler takes this original fourth-Limited NPC")
        installation = next(x for x in am.limiters(state, value.actor) if x.id == value.limiter)
        actual_event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == installation.source_event,
            )
        ).first()
        if (
            actual_event is None
            or actual_event.kind not in ("m3.choice_resolved", "m3.am_report_limiter_installed")
            or actual_event.actor_id != str(value.controller)
        ):
            raise WorkflowError("Only an actual owned fourth-Limiter installation can reset")
        saved = _history(self.game, c, installation.source_event)
        incident = am.discovery(saved, identity)
        if (
            incident.phase != "reset_pending"
            or incident.reset_work != value.reset_work
            or row["event_id"] != installation.source_event
            or len(am.limiters(saved, value.actor)) != 4
        ):
            raise WorkflowError("Recover the actual fourth installation and original reset source")
        return state, value, dict(row), installation

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value, _, _ = self._pending(c, viewer, identity)
            return dict(
                id=identity,
                revision=state.revision,
                jobs=rules.JOBS,
                callsign=state.sheets[value.actor.entity].callsign,
                channel=value.cast.channel,
                controller=viewer.user_id,
            )

    def complete(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, job: str, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200 or job not in rules.JOBS:
            raise WorkflowError("Choose the actual printed NPC role and record the real reset")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m2_choices import ChoiceEngine
            from girlframe.services.m3_careers import end_in_transaction, synchronize_end

            self.game.unpaused(c)
            state, value, work, installation = self._pending(c, viewer, identity)
            if state.revision != expected:
                raise WorkflowError("STALE_RESET: reopen the actual original source")
            action = self.game.action(c, value.action) if value.action else None
            pending = []
            if action is not None and action["state"] != "complete":
                pending = [
                    x
                    for x in self.game.pending(c, action["id"])
                    if x["kind"] == "am_factory_reset" and x["actor_id"] == str(viewer.user_id)
                ]
                lock = self.game.lock(c, value.cast.channel)
                if (
                    len(pending) != 1
                    or not lock
                    or lock["state"] != "held"
                    or action["data"].get("am_scrutinized", {}).get("discovery") != identity
                ):
                    raise WorkflowError("Recover the actual known source and original held scene")
            elif self.game.pending_actions(c):
                raise WorkflowError("Finish the actual current Play before this reported reset")
            event, archive, npc = str(uuid4()), str(uuid4()), str(uuid4())
            ended = end_in_transaction(
                c,
                self.game,
                state,
                value.actor,
                reason="factory_reset",
                source_event=event,
                account=account,
                archive_id=archive,
            )
            changed = rules.convert(
                state,
                ended,
                value.actor,
                identity=npc,
                discovery=identity,
                installation_event=installation.source_event,
                archive=archive,
                event=event,
                controller=viewer.user_id,
                job=job,
                account=account,
            )
            if pending and action is not None:
                choices = t.m2["m2_choices"]
                row = pending[0]
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == self.store.campaign_id, choices.c.id == row["id"]
                    )
                    .values(state="completed_by_work", revision=row["revision"] + 1)
                )
                action["data"]["result"]["factory_reset"] = npc
                ChoiceEngine(self.game).finish(c, changed, action)
                self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_factory_reset",
                changed,
                event_id=event,
                discovery=identity,
                npc=npc,
                archive=archive,
            )
            works = t.m3["m3_required_work"]
            c.execute(
                works.insert().values(
                    **{
                        k: v
                        for k, v in work.items()
                        if k not in ("state", "revision", "event_id", "body_json")
                    },
                    state="resolved",
                    revision=work["revision"] + 1,
                    event_id=event,
                    body_json=json.dumps(
                        json.loads(work["body_json"])
                        | dict(
                            resolution="actual_factory_reset", resulting_npc=npc, archive=archive
                        )
                    ),
                )
            )
            synchronize_end(
                c,
                self.game,
                next(x for x in changed.career_archives if x.id == archive),
                exclude_work=(work["id"],),
            )
            return dict(
                id=identity,
                actor=ActorRef(kind="npc", entity=npc).model_dump(mode="json"),
                archive=archive,
            )

        from girlframe.services.m3_am_scrutinized import _access

        return self.store._write(
            viewer,
            key,
            "m3.am_factory_reset",
            dict(id=identity, expected=expected, job=job, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )
