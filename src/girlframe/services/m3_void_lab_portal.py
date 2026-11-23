"""Open the actual laboratory portal atomically with the selected Void Endgame."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_lab_portal as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.void_lab_portal_opened"


class LabPortalService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, ActorRef]:
        access = Access(self.store)
        access.authorize(c, viewer, "strain")
        access.authorize(c, viewer, "world")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        handler = active_handler(original)
        state = load_state(c, self.store.campaign_id)
        if (
            handler is None
            or handler.entity != row["owner_id"]
            or handler.entity != str(viewer.user_id)
            or not same_handler_body(state, handler)
        ):
            raise WorkflowError("Only the original Endgame Handler opens this laboratory portal")
        return row, state, handler

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, _ = self._source(c, viewer, identity)
            return dict(
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                sites=tuple((x.id, x.name) for x in rules.sites(state)),
                portal=next((x for x in rules.projection(state) if x["id"] == identity), None),
            )

    def open(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        site: str,
        laboratory: str,
        account: str,
    ) -> dict[str, Any]:
        if not 0 < len(laboratory.strip()) <= 120 or not 0 < len(account.strip()) <= 1200:
            raise WorkflowError("Name the actual laboratory and record the opening")

        def authorize(c: Connection) -> None:
            self.game.unpaused(c)
            self._source(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row, state, handler = self._source(c, viewer, identity)
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or state.revision != expected
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("STALE_LAB_PORTAL: reopen the actual original Endgame")
            lab_site = next((x for x in rules.sites(state) if x.id == site), None)
            if lab_site is None:
                raise WorkflowError("Choose an actual available Foundation laboratory location")
            event = str(uuid4())
            portal = rules.Portal(
                id=identity,
                source=row["event_id"],
                opened=event,
                handler=handler,
                site=site,
                cell=lab_site.cell,
                laboratory=laboratory.strip(),
                account=account.strip(),
            )
            rules.open_portal(state, portal)
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
                site=site,
                laboratory=laboratory,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
