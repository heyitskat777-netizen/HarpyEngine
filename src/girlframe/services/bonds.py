"""Private, two-party starting-Bond setup agreements with immutable revisions."""

import json
from typing import Any, Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.bonds import PROMPTS, BondProposal
from girlframe.services.handler_setup import HandlerService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

Decision = Literal["accept", "decline", "withdraw"]


class BondService:
    def __init__(self, store: OnboardingStore):
        self.store = store

    def _authorize(self, connection: Connection, viewer: GuildViewer) -> None:
        self.store.guild_member(viewer)
        self.store._membership(connection, viewer)

    def authorize(self, viewer: GuildViewer) -> None:
        with self.store.engine.connect() as connection:
            self._authorize(connection, viewer)

    def _profile(self, connection: Connection, user: str) -> dict[str, Any] | None:
        row = (
            connection.execute(
                sa.select(t.characters)
                .join(
                    t.members,
                    sa.and_(
                        t.characters.c.campaign_id == t.members.c.campaign_id,
                        t.characters.c.user_id == t.members.c.user_id,
                    ),
                )
                .where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == user,
                    t.members.c.active.is_(True),
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def _profiles(
        self, connection: Connection, source: int, target: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if source == target:
            raise WorkflowError("Choose another joined player with a saved character profile.")
        handler = HandlerService(self.store).current(connection)[1].handler_id
        if handler in (source, target):
            raise WorkflowError(
                "Starting player Bonds require Pilot accounts; Handler is outside that roster."
            )
        own, other = self._profile(connection, str(source)), self._profile(connection, str(target))
        if own is None or other is None:
            raise WorkflowError("Both players must be active campaign members with saved profiles.")
        return own, other

    def prepare(self, viewer: GuildViewer, target: int) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            self._authorize(connection, viewer)
            own, other = self._profiles(connection, viewer.user_id, target)
            girl = json.loads(own["public_json"])["girl_playbook"]
            assignment = (
                HandlerService(self.store).mentor_for(connection, viewer.user_id)
                if girl == "NEWGIRL"
                else None
            )
            if girl == "NEWGIRL" and (assignment is None or assignment.mentor.user_id != target):
                raise WorkflowError(
                    "UNSUPPORTED_RULE: propose only to your currently Handler-assigned Mentor."
                )
            return {
                "source_revision": own["revision"],
                "target_revision": other["revision"],
                "girl_playbook": girl,
            }

    def _latest(self, connection: Connection, user: str) -> list[dict[str, Any]]:
        table = t.bond_revisions
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
                    sa.or_(table.c.source_id == user, table.c.target_id == user),
                )
            ).mappings()
        ]

    def _stale(self, connection: Connection, row: dict[str, Any]) -> bool:
        handler = HandlerService(self.store).current(connection)[1].handler_id
        if handler is not None and str(handler) in (row["source_id"], row["target_id"]):
            return True
        if row["girl_playbook"] == "NEWGIRL":
            assignment = HandlerService(self.store).mentor_for(connection, int(row["source_id"]))
            if assignment is None or assignment.assignment_id != row["mentor_assignment_id"]:
                return True
        for party in ("source", "target"):
            profile = self._profile(connection, row[party + "_id"])
            if profile is None or profile["revision"] != row[party + "_revision"]:
                return True
        return False

    def _party(self, connection: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self._authorize(connection, viewer)
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("This proposal is unavailable.") from None
        row = next(
            (row for row in self._latest(connection, str(viewer.user_id)) if row["id"] == identity),
            None,
        )
        if row is None or str(viewer.user_id) not in (row["source_id"], row["target_id"]):
            raise WorkflowError("This proposal is unavailable.")
        return row

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as connection:
            row = self._party(connection, viewer, identity)
            return row | {"stale": self._stale(connection, row)}

    def list(self, viewer: GuildViewer, before: str | None = None) -> list[dict[str, Any]]:
        with self.store.engine.connect() as connection:
            self._authorize(connection, viewer)
            rows = [
                row
                for row in self._latest(connection, str(viewer.user_id))
                if str(viewer.user_id) in (row["source_id"], row["target_id"])
                and (before is None or row["id"] < before)
            ]
            rows.sort(key=lambda row: row["id"], reverse=True)
            return [row | {"stale": self._stale(connection, row)} for row in rows[:20]]

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        source_revision: int,
        target_revision: int,
        proposal: BondProposal,
    ) -> dict[str, Any]:
        self.prepare(viewer, proposal.target_id)  # Recheck membership even on inbox replay.
        proposal = BondProposal.model_validate_json(proposal.model_dump_json())

        def operation(connection: Connection) -> dict[str, Any]:
            self._authorize(connection, viewer)
            own, other = self._profiles(connection, viewer.user_id, proposal.target_id)
            if (own["revision"], other["revision"]) != (source_revision, target_revision):
                raise WorkflowError("STALE_REVISION: reopen the proposal; profiles changed.")
            girl = json.loads(own["public_json"])["girl_playbook"]
            assignment = (
                HandlerService(self.store).mentor_for(connection, viewer.user_id)
                if girl == "NEWGIRL"
                else None
            )
            if girl == "NEWGIRL" and (
                assignment is None or assignment.mentor.user_id != proposal.target_id
            ):
                raise WorkflowError(
                    "UNSUPPORTED_RULE: propose only to your currently Handler-assigned Mentor."
                )
            if proposal.prompt >= len(PROMPTS[girl]):
                raise WorkflowError("Choose a starting prompt from your current Girl playbook.")
            source, target = str(viewer.user_id), str(proposal.target_id)
            for row in self._latest(connection, str(viewer.user_id)):
                if row["state"] in ("pending", "accepted") and not self._stale(connection, row):
                    if row["source_id"] == source or {row["source_id"], row["target_id"]} == {
                        source,
                        target,
                    }:
                        raise WorkflowError(
                            "An active starting proposal exists; review or withdraw it first."
                        )
            result = {"id": str(uuid4()), "revision": 1, "state": "pending"}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.bond_proposed", result
            )
            connection.execute(
                t.bond_revisions.insert().values(
                    campaign_id=self.store.campaign_id,
                    **result,
                    source_id=source,
                    target_id=target,
                    source_revision=source_revision,
                    target_revision=target_revision,
                    girl_playbook=girl,
                    mentor_assignment_id=assignment.assignment_id if assignment else None,
                    prompt=proposal.prompt,
                    context=proposal.context,
                    event_id=event,
                )
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.bond_proposed",
            {
                "source_revision": source_revision,
                "target_revision": target_revision,
                "proposal": proposal.model_dump(mode="json"),
            },
            operation,
            auto_audit=False,
        )

    def decide(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, decision: Decision
    ) -> dict[str, Any]:
        self.get(viewer, identity)  # Includes current membership on idempotent replay.

        def operation(connection: Connection) -> dict[str, Any]:
            row = self._party(connection, viewer, identity)
            if row["revision"] != revision:
                raise WorkflowError("STALE_REVISION: reopen /character bonds; proposal preserved.")
            target = row["target_id"] == str(viewer.user_id)
            state = row["state"]
            if decision == "accept" and target and state == "pending":
                if self._stale(connection, row):
                    raise WorkflowError("STALE_PROFILE: profiles changed; request a new proposal.")
                new_state = "accepted"
            elif decision == "decline" and target and state == "pending":
                new_state = "declined"
            elif decision == "withdraw" and (
                state == "accepted" or (state == "pending" and not target)
            ):
                new_state = "withdrawn"
            else:
                raise WorkflowError("This decision is not available to you for this proposal.")
            result = {"id": row["id"], "revision": revision + 1, "state": new_state}
            event = self.store._audit(
                connection, viewer.user_id, key, "character.bond_decided", result
            )
            connection.execute(
                t.bond_revisions.insert().values(**(row | result | {"event_id": event}))
            )
            return result

        return self.store._write(
            viewer,
            key,
            "character.bond_decided",
            {
                "id": identity,
                "revision": revision,
                "decision": decision,
            },
            operation,
            auto_audit=False,
        )
