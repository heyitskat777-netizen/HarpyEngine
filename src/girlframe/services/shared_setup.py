"""Private participant agreement for starting Court and Mentor-chosen callsigns."""

import json
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.shared_setup import AcceptedSetup, CallsignChoice, CourtChoice, Kind
from girlframe.services.bonds import BondService, Decision
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class SharedSetupService:
    def __init__(self, store: OnboardingStore):
        self.store, self.bonds = store, BondService(store)

    def mentor_bond(
        self, connection: Connection, newgirl: int, mentor: int
    ) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in self.bonds._latest(connection, str(newgirl))
                if row["girl_playbook"] == "NEWGIRL"
                and row["source_id"] == str(newgirl)
                and row["target_id"] == str(mentor)
                and row["state"] == "accepted"
                and not self.bonds._stale(connection, row)
            ),
            None,
        )

    def _context(
        self, connection: Connection, source: int, target: int, kind: Kind
    ) -> dict[str, Any]:
        first, second = self.bonds._profiles(connection, source, target)
        token = None
        if kind == "court":
            if json.loads(first["public_json"])["frame_playbook"] != "THE RED QUEEN":
                raise WorkflowError("Only a Red Queen pilot proposes a starting Court assignment.")
        elif kind == "callsign":
            bond = self.mentor_bond(connection, target, source)
            if bond is None:
                raise WorkflowError(
                    "Only the current mutually accepted Mentor chooses this Newgirl callsign."
                )
            token = bond["id"] + ":" + str(bond["revision"]) + ":" + bond["mentor_assignment_id"]
        else:
            raise WorkflowError("Unsupported setup choice.")
        return {
            "source_revision": first["revision"],
            "target_revision": second["revision"],
            "constraint_token": token,
        }

    def prepare(self, viewer: GuildViewer, target: int, kind: Kind) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self.bonds._authorize(connection, viewer)
            return self._context(connection, viewer.user_id, target, kind)

    def _latest(self, connection: Connection, user: int) -> list[dict[str, Any]]:
        table = t.shared_setup_revisions
        latest = (
            sa.select(table.c.id, sa.func.max(table.c.revision).label("last"))
            .where(table.c.campaign_id == self.store.campaign_id)
            .group_by(table.c.id)
            .subquery()
        )
        return [
            dict(row)
            for row in connection.execute(
                sa.select(table)
                .join(latest, sa.and_(table.c.id == latest.c.id, table.c.revision == latest.c.last))
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    sa.or_(table.c.source_id == str(user), table.c.target_id == str(user)),
                )
            ).mappings()
        ]

    def _stale(self, connection: Connection, row: dict[str, Any]) -> bool:
        try:
            context = self._context(
                connection, int(row["source_id"]), int(row["target_id"]), row["kind"]
            )
        except WorkflowError:
            return True
        return any(
            context[key] != row[key]
            for key in ("source_revision", "target_revision", "constraint_token")
        )

    def _party(self, connection: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.bonds._authorize(connection, viewer)
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("This setup request is unavailable.") from None
        row = next(
            (x for x in self._latest(connection, viewer.user_id) if x["id"] == identity), None
        )
        if row is None:
            raise WorkflowError("This setup request is unavailable.")
        return row

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            row = self._party(connection, viewer, identity)
            return row | {"stale": self._stale(connection, row)}

    def list(self, viewer: GuildViewer, before: str | None = None) -> list[dict[str, Any]]:
        with self.store.engine.connect() as connection:
            self.bonds._authorize(connection, viewer)
            rows = sorted(
                (
                    x
                    for x in self._latest(connection, viewer.user_id)
                    if before is None or x["id"] < before
                ),
                key=lambda x: x["id"],
                reverse=True,
            )
            return [x | {"stale": self._stale(connection, x)} for x in rows[:20]]

    def accepted_for(self, connection: Connection, owner: int) -> tuple[AcceptedSetup, ...]:
        choices = []
        for row in self._latest(connection, owner):
            relevant = (
                row["source_id"] == str(owner)
                if row["kind"] == "court"
                else row["target_id"] == str(owner)
            )
            if relevant and row["state"] == "accepted" and not self._stale(connection, row):
                value = json.loads(row["choice_json"])[
                    "role" if row["kind"] == "court" else "callsign"
                ]
                choices.append(
                    AcceptedSetup(
                        id=row["id"],
                        revision=row["revision"],
                        kind=row["kind"],
                        source_id=int(row["source_id"]),
                        target_id=int(row["target_id"]),
                        value=value,
                    )
                )
        return tuple(sorted(choices, key=lambda x: x.token))

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        target: int,
        kind: Kind,
        prepared: dict[str, Any],
        choice: CourtChoice | CallsignChoice,
    ) -> dict[str, Any]:
        parsed = (CourtChoice if kind == "court" else CallsignChoice).model_validate_json(
            choice.model_dump_json()
        )

        def authorize(connection: Connection) -> None:
            self.bonds._authorize(connection, viewer)
            if self._context(connection, viewer.user_id, target, kind) != prepared:
                raise WorkflowError("STALE_PROFILE: profiles or authority changed.")

        def operation(connection: Connection) -> dict[str, Any]:
            current = self._context(connection, viewer.user_id, target, kind)
            if current != prepared:
                raise WorkflowError(
                    "STALE_PROFILE: reopen this choice; profiles or authority changed."
                )
            for row in self._latest(connection, viewer.user_id):
                same = (
                    row["source_id"] == str(viewer.user_id)
                    and row["kind"] == kind
                    and (kind == "court" or row["target_id"] == str(target))
                )
                if (
                    same
                    and row["state"] in ("pending", "accepted")
                    and not self._stale(connection, row)
                ):
                    raise WorkflowError(
                        "A current setup request exists; review or withdraw it first."
                    )
            result = {"id": str(uuid4()), "revision": 1, "state": "pending"}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.setup_proposed", result
            )
            connection.execute(
                t.shared_setup_revisions.insert().values(
                    campaign_id=self.store.campaign_id,
                    **result,
                    source_id=str(viewer.user_id),
                    target_id=str(target),
                    kind=kind,
                    **current,
                    choice_json=parsed.model_dump_json(),
                    event_id=event,
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.setup_proposed",
            {
                "target": target,
                "kind": kind,
                "prepared": prepared,
                "choice": parsed.model_dump(mode="json"),
            },
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def decide(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, decision: Decision
    ) -> dict[str, Any]:
        def authorize(connection: Connection) -> None:
            row = self._party(connection, viewer, identity)
            if decision == "accept" and (
                row["state"] not in ("pending", "accepted") or self._stale(connection, row)
            ):
                raise WorkflowError("STALE_SETUP: acceptance authority changed.")

        def operation(connection: Connection) -> dict[str, Any]:
            row = self._party(connection, viewer, identity)
            if row["revision"] != revision:
                raise WorkflowError("STALE_REVISION: reopen /character requests.")
            recipient = row["target_id"] == str(viewer.user_id)
            if decision == "accept" and recipient and row["state"] == "pending":
                if self._stale(connection, row):
                    raise WorkflowError("STALE_PROFILE: profiles or setup authority changed.")
                state = "accepted"
            elif decision == "decline" and recipient and row["state"] == "pending":
                state = "declined"
            elif decision == "withdraw" and (
                row["state"] == "accepted" or (row["state"] == "pending" and not recipient)
            ):
                state = "withdrawn"
            else:
                raise WorkflowError("This decision is not available for this request.")
            result = {"id": row["id"], "revision": revision + 1, "state": state}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.setup_decided", result
            )
            connection.execute(
                t.shared_setup_revisions.insert().values(**(row | result | {"event_id": event}))
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.setup_decided",
            {"id": identity, "revision": revision, "decision": decision},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def effective_status(self, viewer: GuildViewer, target: int) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self.bonds._authorize(connection, viewer)
            if viewer.user_id == target or not HandlerService(self.store)._member(
                connection, target
            ):
                raise WorkflowError("Choose another active campaign participant.")
            state = HandlerService(self.store).view(viewer)
            if state["handler_active"] and state["handler_id"] in (viewer.user_id, target):
                return {"higher": state["handler_id"] == viewer.user_id, "basis": "Handler"}
            forward = self.mentor_bond(connection, target, viewer.user_id) is not None
            reverse = self.mentor_bond(connection, viewer.user_id, target) is not None
            if forward and reverse:
                return {
                    "higher": None,
                    "basis": "UNSUPPORTED_RULE: reciprocal Mentor authority needs review",
                }
            if forward or reverse:
                return {"higher": forward, "basis": "Mentor exception"}
            order = [x["user_id"] for x in state["status_order"]]
            if not state["status_stale"] and viewer.user_id in order and target in order:
                return {
                    "higher": order.index(viewer.user_id) < order.index(target),
                    "basis": "starting Status",
                }
            return {"higher": None, "basis": "unresolved starting Status"}
