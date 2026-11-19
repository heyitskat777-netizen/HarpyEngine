"""Source-owned Endgame concealment and recipient-safe observations."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_privacy as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_handler_void import HandlerVoidService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.handler_void_concealment_granted"


class ConcealmentService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, ActorRef]:
        Access(self.store).authorize(c, viewer, "strain")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        handler = active_handler(original)
        if (
            handler is None
            or handler.entity != str(viewer.user_id)
            or row["owner_id"] != handler.entity
        ):
            raise WorkflowError("Only the original Endgame Handler owns the concealment")
        return row, load_state(c, self.store.campaign_id), handler

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, _ = self._source(c, viewer, identity)
            return dict(
                revision=row["revision"],
                game_revision=state.revision,
                grant=next((x for x in rules.grants(state) if x.id == identity), None),
            )

    def arm(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, expected: int
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.game.unpaused(c)
            self._source(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row, state, handler = self._source(c, viewer, identity)
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or state.revision != expected
                or not same_handler_body(state, handler)
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("STALE_CONCEALMENT: reopen the actual original Endgame source")
            event = str(uuid4())
            rules.save_grant(
                state,
                rules.Concealment(
                    id=identity, handler=handler, source=row["event_id"], granted=event
                ),
            )
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event, work_id=identity)
            work = t.m3["m3_required_work"]
            c.execute(
                work.insert().values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=revision + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, state="resolved")

        return self.store._write(
            viewer,
            key,
            EVENT,
            dict(id=identity, revision=revision, expected=expected),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def observed(self, viewer: GuildViewer, identity: str) -> rules.Notice:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            notice = next((x for x in rules.notices(state) if x.id == identity), None)
            if notice is None or not any(x.controller == viewer.user_id for x in notice.witnesses):
                raise WorkflowError("This observation belongs to its original witnesses")
            history = t.m2["m2_state_history"]
            raw = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == notice.event,
                )
            )
            original = GameState.model_validate_json(raw) if raw else None
            _, first, episode = HandlerVoidService(self.store, self.game)._proof(c, identity)
            if (
                original is None
                or notice not in rules.notices(original)
                or episode.body != notice.handler
                or episode.source_event != notice.event
                or first["kind"] != "void_spread_handler_void"
            ):
                raise WorkflowError("Recover the actual original marked observation")
            return notice.model_copy(
                update={
                    "witnesses": tuple(
                        x for x in notice.witnesses if x.controller == viewer.user_id
                    )
                }
            )
