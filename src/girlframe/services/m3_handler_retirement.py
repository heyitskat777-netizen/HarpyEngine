"""Commit the actual Endgame medal, owning Handler and later retirement."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_retirement as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.handler_retirement_awarded"


def require_successor(state: GameState) -> None:
    if any(x.retired for x in rules.awards(state)) and active_handler(state) is None:
        raise WorkflowError(
            "Activate an actual successor Handler before starting the next campaign phase"
        )


class RetirementService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, ActorRef]:
        Access(self.store).authorize(c, viewer, "strain")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        handler = active_handler(original)
        state = load_state(c, self.store.campaign_id)
        if (
            handler is None
            or handler.entity != row["owner_id"]
            or handler.entity != str(viewer.user_id)
        ):
            raise WorkflowError("Only the original Endgame Handler owns the medal and retirement")
        return row, state, handler

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, _ = self._source(c, viewer, identity)
            return dict(
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                award=next((x for x in rules.awards(state) if x.id == identity), None),
            )

    def award(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        medal: str,
        safe_home: str,
        account: str,
    ) -> dict[str, Any]:
        if not (
            0 < len(medal.strip()) <= 120
            and 0 < len(safe_home.strip()) <= 300
            and 0 < len(account.strip()) <= 1200
        ):
            raise WorkflowError(
                "Record the actual award, safe Quadrant home and retirement account"
            )

        def authorize(c: Connection) -> None:
            self.game.unpaused(c)
            self._source(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row, state, handler = self._source(c, viewer, identity)
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or state.revision != expected
                or self.game.pending_actions(c)
                or not same_handler_body(state, handler)
            ):
                raise WorkflowError("STALE_HANDLER_RETIREMENT: reopen the original source")
            _, appointment = MedicalService(self.store)._handler(c)
            event = str(uuid4())
            rules.save(
                state,
                rules.Retirement(
                    id=identity,
                    source=row["event_id"],
                    awarded=event,
                    period=row["off_duty_id"],
                    handler=handler,
                    appointment=appointment,
                    medal=medal.strip(),
                    safe_home=safe_home.strip(),
                    account=account.strip(),
                ),
            )
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event, work_id=identity)
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
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
            dict(
                id=identity,
                revision=revision,
                expected=expected,
                medal=medal,
                safe_home=safe_home,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
