"""Actual chooser authority for private Princess and Vatgrown setup choices."""

import json
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.creation_details import (
    AcceptedCoordination,
    DesireChoice,
    Role,
    StandardChoice,
)
from girlframe.services.bonds import BondService, Decision
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class CoordinationService:
    def __init__(self, store: OnboardingStore):
        self.store, self.bonds = store, BondService(store)

    def _context(
        self, connection: Connection, author: int, owner: int, role: Role
    ) -> dict[str, Any]:
        if role not in ("princess_peer", "princess_handler", "vatgrown_handler") or author == owner:
            raise WorkflowError("Choose a supported role and another active character owner.")
        target = self.bonds._profile(connection, str(owner))
        if target is None:
            raise WorkflowError(
                "The character owner must be an active joined Pilot with a profile."
            )
        handler = HandlerService(self.store)
        if handler.current(connection)[1].handler_id == owner:
            raise WorkflowError("The Handler account is outside Pilot creation.")
        expected_girl = "VATGROWN" if role == "vatgrown_handler" else "PRINCESS"
        if json.loads(target["public_json"])["girl_playbook"] != expected_girl:
            raise WorkflowError("This choice belongs to a different Girl playbook.")
        token = ""
        if role == "princess_peer":
            source, _ = self.bonds._profiles(connection, author, owner)
            bond = next(
                (
                    x
                    for x in self.bonds._latest(connection, str(owner))
                    if {x["source_id"], x["target_id"]} == {str(author), str(owner)}
                    and x["state"] == "accepted"
                    and not self.bonds._stale(connection, x)
                ),
                None,
            )
            if bond is None:
                raise WorkflowError("A currently bonded Girl chooses this Princess standard.")
            token = bond["id"] + ":" + str(bond["revision"])
            author_revision = source["revision"]
        else:
            if handler.current(connection)[1].handler_id != author or not handler._member(
                connection, author
            ):
                raise WorkflowError("Only the currently appointed Handler chooses this value.")
            appointment = connection.execute(
                sa.select(t.events.c.id)
                .where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "campaign.handler_appointed",
                )
                .order_by(t.events.c.seq.desc())
                .limit(1)
            ).scalar_one_or_none()
            if appointment is None:
                raise WorkflowError("A current explicit Handler appointment is required.")
            token, author_revision = str(appointment), 0
        return {
            "owner_revision": target["revision"],
            "author_revision": author_revision,
            "authority_token": token,
            "role": role,
        }

    def prepare(self, viewer: GuildViewer, owner: int, role: Role) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            self.bonds._authorize(connection, viewer)
            return self._context(connection, viewer.user_id, owner, role)

    def _latest(self, connection: Connection, party: int | None = None) -> list[dict[str, Any]]:
        table = t.coordination_revisions
        latest = (
            sa.select(table.c.id, sa.func.max(table.c.revision).label("last"))
            .where(table.c.campaign_id == self.store.campaign_id)
            .group_by(table.c.id)
            .subquery()
        )
        query = (
            sa.select(table)
            .join(latest, sa.and_(table.c.id == latest.c.id, table.c.revision == latest.c.last))
            .where(table.c.campaign_id == self.store.campaign_id)
        )
        if party is not None:
            query = query.where(
                sa.or_(table.c.author_id == str(party), table.c.owner_id == str(party))
            )
        return [dict(x) for x in connection.execute(query).mappings()]

    def _stale(self, connection: Connection, row: dict[str, Any]) -> bool:
        try:
            return bool(
                self._context(connection, int(row["author_id"]), int(row["owner_id"]), row["role"])
                != json.loads(row["context_json"])
            )
        except WorkflowError:
            return True

    def _party(self, connection: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.bonds._authorize(connection, viewer)
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("This playbook request is unavailable.") from None
        row = next(
            (x for x in self._latest(connection, viewer.user_id) if x["id"] == identity), None
        )
        if row is None:
            raise WorkflowError("This playbook request is unavailable.")
        return row

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            row = self._party(connection, viewer, identity)
            return row | {"stale": self._stale(connection, row)}

    @staticmethod
    def parsed(row: dict[str, Any]) -> AcceptedCoordination:
        standard = (
            StandardChoice.model_validate_json(row["choice_json"])
            if row["role"] != "vatgrown_handler"
            else None
        )
        desires = (
            DesireChoice.model_validate_json(row["choice_json"])
            if row["role"] == "vatgrown_handler"
            else None
        )
        return AcceptedCoordination(
            id=row["id"],
            revision=row["revision"],
            role=row["role"],
            author=int(row["author_id"]),
            owner=int(row["owner_id"]),
            standard=standard,
            desires=desires,
        )

    def accepted(self, connection: Connection, owner: int) -> tuple[AcceptedCoordination, ...]:
        return tuple(
            self.parsed(x)
            for x in sorted(self._latest(connection, owner), key=lambda x: x["id"])
            if x["owner_id"] == str(owner)
            and x["state"] == "accepted"
            and not self._stale(connection, x)
        )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        owner: int,
        role: Role,
        context: dict[str, Any],
        choice: StandardChoice | DesireChoice,
    ) -> dict[str, Any]:
        parsed = (
            DesireChoice if role == "vatgrown_handler" else StandardChoice
        ).model_validate_json(choice.model_dump_json())

        def authorize(connection: Connection) -> None:
            self.bonds._authorize(connection, viewer)
            if self._context(connection, viewer.user_id, owner, role) != context:
                raise WorkflowError("STALE_AUTHORITY: reopen this playbook choice.")

        def operation(connection: Connection) -> dict[str, Any]:
            if any(
                x["owner_id"] == str(owner)
                and x["role"] == role
                and x["state"] in ("pending", "accepted")
                and not self._stale(connection, x)
                for x in self._latest(connection, owner)
            ):
                raise WorkflowError(
                    "A current request already covers this choice; review or withdraw it."
                )
            result = {"id": str(uuid4()), "revision": 1, "state": "pending"}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.coordination_proposed", result
            )
            connection.execute(
                t.coordination_revisions.insert().values(
                    campaign_id=self.store.campaign_id,
                    **result,
                    author_id=str(viewer.user_id),
                    owner_id=str(owner),
                    role=role,
                    context_json=json.dumps(context, sort_keys=True),
                    choice_json=parsed.model_dump_json(),
                    event_id=event,
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.coordination_proposed",
            {
                "owner": owner,
                "role": role,
                "context": context,
                "choice": parsed.model_dump(mode="json"),
            },
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def decide(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, decision: Decision
    ) -> dict[str, Any]:
        def operation(connection: Connection) -> dict[str, Any]:
            row = self._party(connection, viewer, identity)
            if row["revision"] != revision:
                raise WorkflowError("STALE_REVISION: refresh this playbook request.")
            recipient = row["owner_id"] == str(viewer.user_id)
            state = row["state"]
            if decision == "accept" and recipient and state == "pending":
                if self._stale(connection, row):
                    raise WorkflowError("STALE_AUTHORITY: a fresh choice is required.")
                next_state = "accepted"
            elif decision == "decline" and recipient and state == "pending":
                next_state = "declined"
            elif decision == "withdraw" and (
                state == "accepted" or (state == "pending" and not recipient)
            ):
                next_state = "withdrawn"
            else:
                raise WorkflowError(
                    "This decision is unavailable for your role and the current state."
                )
            result = {"id": row["id"], "revision": revision + 1, "state": next_state}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.coordination_decided", result
            )
            values = {k: v for k, v in row.items() if k not in ("event_id", "revision", "state")}
            connection.execute(
                t.coordination_revisions.insert().values(
                    **values, revision=revision + 1, state=next_state, event_id=event
                )
            )
            return result

        def authorize(connection: Connection) -> None:
            row = self._party(connection, viewer, identity)
            if decision == "accept" and self._stale(connection, row):
                raise WorkflowError("STALE_AUTHORITY: a fresh choice is required.")

        return self.store._write(
            viewer,
            key,
            "character.coordination_decided",
            {"id": identity, "revision": revision, "decision": decision},
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def tasks(self, connection: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        handler = HandlerService(self.store)
        targets: set[tuple[int, Role]] = set()
        if handler.current(connection)[1].handler_id == viewer.user_id:
            for owner, profile in handler._roster(connection).items():
                if profile["girl_playbook"] in ("PRINCESS", "VATGROWN"):
                    role: Role = (
                        "princess_handler"
                        if profile["girl_playbook"] == "PRINCESS"
                        else "vatgrown_handler"
                    )
                    targets.add((owner, role))
        for bond in self.bonds._latest(connection, str(viewer.user_id)):
            if bond["state"] == "accepted" and not self.bonds._stale(connection, bond):
                owner = int(
                    bond["target_id"]
                    if bond["source_id"] == str(viewer.user_id)
                    else bond["source_id"]
                )
                counterpart_profile = self.bonds._profile(connection, str(owner))
                if (
                    counterpart_profile
                    and json.loads(counterpart_profile["public_json"])["girl_playbook"]
                    == "PRINCESS"
                ):
                    targets.add((owner, "princess_peer"))
        result = []
        for owner, role in sorted(targets):
            try:
                context = self._context(connection, viewer.user_id, owner, role)
            except WorkflowError:
                continue
            if not any(
                x["owner_id"] == str(owner)
                and x["role"] == role
                and x["state"] in ("pending", "accepted")
                and not self._stale(connection, x)
                for x in self._latest(connection, owner)
            ):
                result.append({"owner": owner, "role": role, "context": context})
        return result
