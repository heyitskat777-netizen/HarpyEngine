"""Private shelving intake only. No availability change until a safe freeze exists.

The event projection deliberately has no active/shelved status: requests cannot be
mistaken for an actor freeze, a rules answer, or a completed obligation.
"""

import json
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_incarnations import proof
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import configured, recipient_is
from girlframe.services.read_only_bot import GuildViewer

KIND = "p1.shelving_intake"
BLOCKED = (
    "SHELVING_UNAVAILABLE: no player has been frozen. Safe actor mutation guards and "
    "parked shared-action recovery are not implemented. This request changes no gameplay "
    "status, consent, obligations or scene locks. Use the existing safety pause if needed."
)


class ShelvingService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _rows(self, c: Connection) -> dict[str, dict[str, Any]]:
        rows = c.execute(
            sa.select(t.events.c.payload_json)
            .where(t.events.c.campaign_id == self.store.campaign_id, t.events.c.kind == KIND)
            .order_by(t.events.c.seq)
        )
        result = {}
        for (body,) in rows:
            value = json.loads(body)
            result[value["id"]] = value
        return result

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        self.game.authorize(c, viewer, game=False)

    def _gm(self, c: Connection, viewer: GuildViewer) -> str:
        recipient = configured(self.game, c)
        if not recipient_is(viewer, recipient):
            raise WorkflowError(
                "Only the currently configured human facilitator may review shelving."
            )
        assert recipient is not None
        return recipient.event

    @staticmethod
    def _actor_context(state: GameState, row: dict[str, Any]) -> str:
        # Presentation only: do not resolve private names or expose incarnation/proof IDs.
        # A missing current actor must not prevent reviewing or withdrawing old intake.
        try:
            actor = current_ref(state, row["owner"])
        except ValueError:
            return "saved actor"
        return (
            "current actor"
            if actor.model_dump(mode="json") == row["original_actor"]
            else "previous actor"
        )

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            gm = recipient_is(viewer, configured(self.game, c))
            state = load_state(c, self.store.campaign_id)
            return [
                dict(
                    row,
                    can_review=gm,
                    own=row["owner"] == viewer.user_id,
                    actor_context=self._actor_context(state, row),
                )
                for row in self._rows(c).values()
                if (gm or row["owner"] == viewer.user_id) and row["status"] == "requested"
            ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            row = self._rows(c).get(identity)
            gm = recipient_is(viewer, configured(self.game, c))
            if row is None or (not gm and row["owner"] != viewer.user_id):
                raise WorkflowError("Shelving request is unavailable.")
            return dict(
                row,
                can_review=gm,
                own=row["owner"] == viewer.user_id,
                actor_context=self._actor_context(load_state(c, self.store.campaign_id), row),
            )

    def _target(
        self, c: Connection, owner: int
    ) -> tuple[GameState, ActorRef, dict[str, Any] | None]:
        """Resolve intake identity from existing canon, never from request metadata.

        Pilot proof includes the saved profile snapshot and original career binding.
        It is NOT an availability generation, resource incidence or dispatch permit.
        Handler intake retains its existing current-body contract.
        """
        if not c.scalar(
            sa.select(t.members.c.user_id).where(
                t.members.c.campaign_id == self.store.campaign_id,
                t.members.c.user_id == str(owner),
                t.members.c.active.is_(True),
            )
        ):
            raise WorkflowError("The player must be an active campaign member.")
        state = load_state(c, self.store.campaign_id)
        try:
            actor = current_ref(state, owner)
        except ValueError as error:
            raise WorkflowError(
                "Shelving intake requires the player's current original actor."
            ) from error
        evidence = None
        if actor.kind == "pilot":
            original = proof(c, self.store.campaign_id, state, owner)
            if original.character != actor.incarnation:
                raise WorkflowError("STALE_CHARACTER: recover the actual original actor.")
            evidence = original.model_dump(mode="json")
        return state, actor, evidence

    def request(self, viewer: GuildViewer, key: str, owner: int | None = None) -> dict[str, Any]:
        """Players request themselves; current GM may propose another player's shelving."""
        from girlframe.services.p1_guarded_intake import request_intake

        return request_intake(self, viewer, key, owner)

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        operation: Literal["withdraw", "decline", "activate"],
    ) -> dict[str, Any]:
        if operation in ("withdraw", "decline"):
            from girlframe.services.p1_guarded_intake import change_intake

            return change_intake(self, viewer, key, identity, expected, operation)

        def authorize(c: Connection) -> None:
            self._authorize(c, viewer)
            if operation in ("decline", "activate"):
                self._gm(c, viewer)  # Cached outcomes do not retain revoked GM access.
            elif operation == "withdraw":
                row = self._rows(c).get(identity)
                if row is None or row["owner"] != viewer.user_id:
                    raise WorkflowError("Only the original player may withdraw this request.")
            else:
                raise WorkflowError("Unknown shelving intake action.")

        def apply(c: Connection) -> dict[str, Any]:
            row = self._rows(c).get(identity)
            if row is None:
                raise WorkflowError("Shelving request is unavailable.")
            gm_event = None
            if operation == "withdraw":
                if row["owner"] != viewer.user_id:
                    raise WorkflowError("Only the original player may withdraw this request.")
            elif operation in ("decline", "activate"):
                gm_event = self._gm(c, viewer)
            else:
                raise WorkflowError("Unknown shelving intake action.")
            if row["revision"] != expected or row["status"] != "requested":
                raise WorkflowError("STALE_SHELVING_REQUEST: reopen the saved request.")
            if operation == "activate":
                raise WorkflowError(BLOCKED)
            updated = dict(
                row,
                revision=row["revision"] + 1,
                status="withdrawn" if operation == "withdraw" else "declined",
                reviewer=viewer.user_id,
                configuration_event=gm_event,
            )
            self.game.event(c, viewer.user_id, key, KIND, **updated)
            return updated

        return self.store._write(
            viewer,
            key,
            KIND,
            dict(id=identity, expected=expected, operation=operation),
            apply,
            auto_audit=False,
            authorize=authorize,
        )
