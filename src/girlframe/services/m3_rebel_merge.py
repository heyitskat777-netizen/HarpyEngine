"""Source-bound original Handler selects the receiving real Rebel Group once."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_merge as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class MergerService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, str]:
        Access(self.store).authorize(c, viewer, "strain")
        Access(self.store).authorize(c, viewer, "world")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        state = load_state(c, self.store.campaign_id)
        handler = active_handler(original)
        chosen = (
            next((x for x in original.strain.endgames if x.rule_id == rules.RULE), None)
            if original.strain
            else None
        )
        if (
            handler is None
            or int(handler.entity) != viewer.user_id
            or row["owner_id"] != str(viewer.user_id)
            or not same_handler_body(state, handler)
            or chosen is None
            or chosen.faction is None
            or original.world is None
            or not any(
                x.id == chosen.faction and x.active and x.kind == "rebel"
                for x in original.world.factions
            )
        ):
            raise WorkflowError(
                "Recover the actual original Endgame Handler and selected active Rebel Group"
            )
        return row, state, chosen.faction

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, source = self._source(c, viewer, identity)
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                source=source,
                receiving=[
                    dict(id=x.id, label=x.name)
                    for x in state.world.factions
                    if x.active and x.kind == "rebel" and x.id != source
                ]
                if state.world
                else [],
            )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        receiving: str,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual funding loss and merger")

        def authorize(c: Connection) -> None:
            self._source(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, source = self._source(c, viewer, identity)
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or state.revision != expected
                or self.game.pending_actions(c)
            ):
                raise WorkflowError(
                    "STALE_MERGER: finish pending Plays and reopen the actual source"
                )
            event = str(uuid4())
            state = rules.merge(state, source, receiving, identity, event, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.rebel_groups_merged",
                state,
                event_id=event,
                work_id=identity,
                source=source,
                receiving=receiving,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **(
                        row
                        | dict(
                            revision=row["revision"] + 1,
                            state="resolved",
                            event_id=event,
                        )
                    )
                )
            )
            return dict(id=identity, state="resolved", source=source, receiving=receiving)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.rebel_groups_merged",
                dict(
                    id=identity,
                    revision=revision,
                    expected=expected,
                    receiving=receiving,
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
