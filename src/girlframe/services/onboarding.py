"""Serialized campaign metadata, owner-bound drafts and resumable setup records.

No legacy-engine writes, rules or dice. Discord side effects happen outside SQLite.
"""

import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from girlframe.database import tables as t
from girlframe.discord_adapter.config import BotPolicy
from girlframe.engine.drafts import DraftInput
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.services.read_only_bot import GuildViewer


class WorkflowError(RuntimeError):
    """Safe, intentionally authored user feedback only."""


class OnboardingStore:
    def __init__(self, engine: Engine, policy: BotPolicy, clock: Callable[[], float] = time.time):
        self.engine = engine
        self.policy = policy
        self.campaign_id = str(policy.campaign_id)
        self.clock = clock
        if not set(t.metadata.tables).issubset(sa.inspect(engine).get_table_names()):
            raise WorkflowError("Run database migrations before enabling server onboarding.")

    def guild_member(self, viewer: GuildViewer) -> None:
        if viewer.guild_id != self.policy.guild_id or not viewer.is_member or viewer.user_id <= 0:
            raise WorkflowError("This action is unavailable here.")

    def administrator(self, viewer: GuildViewer) -> None:
        self.guild_member(viewer)
        if not viewer.is_administrator or not self.policy.allow_guild_administrators:
            raise WorkflowError("Server setup requires configured administrator access.")

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def _binding_matches(self, connection: Connection) -> bool:
        existing = (
            connection.execute(
                sa.select(t.campaigns).where(
                    sa.or_(
                        t.campaigns.c.id == self.campaign_id,
                        t.campaigns.c.guild_id == str(self.policy.guild_id),
                    )
                )
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["id"] != self.campaign_id or existing["guild_id"] != str(
                self.policy.guild_id
            ):
                raise WorkflowError("Existing guild/campaign binding conflicts with configuration.")
        return existing is not None

    def _bind(self, connection: Connection) -> None:
        if not self._binding_matches(connection):
            connection.execute(
                t.campaigns.insert().values(
                    id=self.campaign_id, guild_id=str(self.policy.guild_id), revision=0
                )
            )

    def _audit(
        self,
        connection: Connection,
        actor: int | str,
        key: str,
        kind: str,
        payload: dict[str, Any],
        *,
        event_index: int = 0,
        visibility: str = "private",
        event_id: str | None = None,
    ) -> str:
        identity = event_id or str(uuid4())
        revision = (
            connection.execute(
                sa.select(t.campaigns.c.revision).where(t.campaigns.c.id == self.campaign_id)
            ).scalar_one()
            + 1
        )
        connection.execute(
            t.campaigns.update()
            .where(t.campaigns.c.id == self.campaign_id)
            .values(revision=revision)
        )
        connection.execute(
            t.events.insert().values(
                campaign_id=self.campaign_id,
                seq=revision,
                command_key=key,
                event_index=event_index,
                actor_id=str(actor),
                kind=kind,
                payload_json=json.dumps(payload, sort_keys=True),
                id=identity,
                created_utc=datetime.now(UTC).isoformat(),
                visibility=visibility,
            )
        )
        return identity

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
        *,
        auto_audit: bool = True,
        authorize: Callable[[Connection], None] | None = None,
    ) -> dict[str, Any]:
        self.guild_member(viewer)
        digest = hashlib.sha256(
            json.dumps(
                {"actor": viewer.user_id, "kind": kind, "payload": payload}, sort_keys=True
            ).encode()
        ).hexdigest()
        with self.transaction() as connection:
            self._bind(connection)
            if authorize is not None:
                authorize(connection)
            existing = (
                connection.execute(
                    sa.select(t.commands).where(
                        t.commands.c.campaign_id == self.campaign_id,
                        t.commands.c.interaction_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                if existing["request_hash"] != digest:
                    raise WorkflowError("IDEMPOTENCY_CONFLICT: this request changed.")
                return dict(json.loads(existing["outcome_json"]))
            result = operation(connection)
            connection.execute(
                t.commands.insert().values(
                    campaign_id=self.campaign_id,
                    interaction_key=key,
                    request_hash=digest,
                    outcome_json=json.dumps(result, sort_keys=True),
                )
            )
            # Draft notes remain only in private storage; never in generic audit payloads.
            event_id = None
            if auto_audit:
                event_id = self._audit(
                    connection,
                    viewer.user_id,
                    key,
                    kind,
                    {k: v for k, v in result.items() if k not in {"notes", "private"}},
                )
            if kind == "character.draft_saved":
                row = (
                    connection.execute(
                        sa.select(t.characters).where(
                            t.characters.c.campaign_id == self.campaign_id,
                            t.characters.c.user_id == str(viewer.user_id),
                        )
                    )
                    .mappings()
                    .one()
                )
                connection.execute(
                    t.snapshots.insert().values(
                        campaign_id=self.campaign_id,
                        user_id=str(viewer.user_id),
                        revision=row["revision"],
                        character_id=row["id"],
                        event_id=event_id,
                        public_json=row["public_json"],
                        private_json=row["private_json"],
                    )
                )
            return result

    def join(self, viewer: GuildViewer, key: str) -> dict[str, Any]:
        def operation(connection: Connection) -> dict[str, Any]:
            if not connection.execute(
                sa.select(t.principals).where(t.principals.c.user_id == str(viewer.user_id))
            ).first():
                connection.execute(
                    t.principals.insert().values(
                        user_id=str(viewer.user_id),
                        id=str(uuid4()),
                        created_utc=datetime.now(UTC).isoformat(),
                    )
                )
            found = connection.execute(
                sa.select(t.members).where(
                    t.members.c.campaign_id == self.campaign_id,
                    t.members.c.user_id == str(viewer.user_id),
                )
            ).first()
            if not found:
                connection.execute(
                    t.members.insert().values(
                        campaign_id=self.campaign_id, user_id=str(viewer.user_id), role="player"
                    )
                )
            elif not found.active:
                raise WorkflowError("Campaign membership is inactive. Contact the administrator.")
            return {"joined": True}

        return self._write(viewer, key, "campaign.joined", {}, operation)

    def _membership(self, connection: Connection, viewer: GuildViewer) -> None:
        self._binding_matches(connection)
        if not connection.execute(
            sa.select(t.members).where(
                t.members.c.campaign_id == self.campaign_id,
                t.members.c.user_id == str(viewer.user_id),
                t.members.c.active.is_(True),
            )
        ).first():
            raise WorkflowError("Join this campaign before creating or viewing sheets.")

    def draft(self, viewer: GuildViewer, owner: int | None = None) -> dict[str, Any] | None:
        self.guild_member(viewer)
        owner = viewer.user_id if owner is None else owner
        with self.engine.connect() as connection:
            self._membership(connection, viewer)
            row = (
                connection.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.campaign_id,
                        t.characters.c.user_id == str(owner),
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            from girlframe.services.m2_state import load_state, public_sheet

            state = load_state(connection, self.campaign_id)
            sheet = state.sheets.get(str(owner))
            if sheet:
                result = public_sheet(sheet, state)
                result.update(id=row["id"], revision=row["revision"])
                if owner == viewer.user_id:
                    result["notes"] = json.loads(row["private_json"])["notes"]
                    result["canonical"] = sheet.model_dump(mode="json")
                return result
            result = dict(json.loads(row["public_json"]))
            result.update(id=row["id"], revision=row["revision"], status="draft_rules_unverified")
            if owner == viewer.user_id:
                result["notes"] = json.loads(row["private_json"])["notes"]
            return result

    def save_draft(
        self, viewer: GuildViewer, key: str, expected_revision: int, draft: DraftInput
    ) -> dict[str, Any]:
        # Check membership before idempotent replay too; revoked users cannot replay.
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._membership(connection, viewer)

        def operation(connection: Connection) -> dict[str, Any]:
            self._membership(connection, viewer)
            from girlframe.services.m2_state import active

            if active(connection, self.campaign_id, viewer.user_id):
                raise WorkflowError(
                    "ACTIVE_CHARACTER: creation editors cannot reset an activated character."
                )
            where = (
                t.characters.c.campaign_id == self.campaign_id,
                t.characters.c.user_id == str(viewer.user_id),
            )
            row = connection.execute(sa.select(t.characters).where(*where)).mappings().first()
            revision = row["revision"] if row else 0
            if expected_revision != revision:
                raise WorkflowError("STALE_REVISION: reopen your draft; nothing was overwritten.")
            identity = row["id"] if row else str(uuid4())
            values = {
                "revision": revision + 1,
                "public_json": json.dumps(draft.model_dump(exclude={"notes"})),
                "private_json": json.dumps({"notes": draft.notes}),
            }
            if row:
                connection.execute(t.characters.update().where(*where).values(**values))
            else:
                connection.execute(
                    t.characters.insert().values(
                        campaign_id=self.campaign_id,
                        user_id=str(viewer.user_id),
                        id=identity,
                        **values,
                    )
                )
            self._enqueue_sync(connection, viewer.user_id, revision + 1, draft)
            return {"id": identity, "revision": revision + 1, "status": "draft_rules_unverified"}

        return self._write(
            viewer,
            key,
            "character.draft_saved",
            {"expected_revision": expected_revision, **draft.model_dump()},
            operation,
        )

    def _enqueue_sync(
        self, connection: Connection, owner: int, revision: int, draft: DraftInput
    ) -> None:
        where = (
            t.character_sync.c.campaign_id == self.campaign_id,
            t.character_sync.c.user_id == str(owner),
        )
        values = {
            "revision": revision,
            "desired_json": json.dumps(draft.model_dump(exclude={"notes"})),
            "state": "pending",
            "warning": "",
        }
        if connection.execute(sa.select(t.character_sync).where(*where)).first():
            connection.execute(t.character_sync.update().where(*where).values(**values))
        else:
            connection.execute(
                t.character_sync.insert().values(
                    campaign_id=self.campaign_id, user_id=str(owner), **values
                )
            )

    def queue_sync(self, viewer: GuildViewer, key: str) -> dict[str, Any]:
        def operation(connection: Connection) -> dict[str, Any]:
            self._membership(connection, viewer)
            row = (
                connection.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkflowError("Save a draft first.")
            try:
                desired = DraftInput.model_validate(json.loads(row["public_json"]))
            except ValueError:
                raise WorkflowError(
                    "Reopen /character create and choose listed playbooks first."
                ) from None
            from girlframe.services.m2_state import load_state

            sheet = load_state(connection, self.campaign_id).sheets.get(str(viewer.user_id))
            if sheet:
                desired = desired.model_copy(update={"callsign": sheet.callsign})
            self._enqueue_sync(connection, viewer.user_id, row["revision"], desired)
            return {"id": row["id"], "revision": row["revision"]}

        return self._write(viewer, key, "character.discord_sync_requested", {}, operation)

    def sync_job(self, viewer: GuildViewer) -> dict[str, Any] | None:
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._membership(connection, viewer)
            row = (
                connection.execute(
                    sa.select(t.character_sync).where(
                        t.character_sync.c.campaign_id == self.campaign_id,
                        t.character_sync.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def pending_sync_users(self) -> list[int]:
        with self.engine.connect() as connection:
            self._binding_matches(connection)
            return [
                int(value)
                for value in connection.execute(
                    sa.select(t.character_sync.c.user_id)
                    .where(
                        t.character_sync.c.campaign_id == self.campaign_id,
                        t.character_sync.c.state == "pending",
                    )
                    .limit(100)
                ).scalars()
            ]

    def finish_sync(self, viewer: GuildViewer, revision: int, complete: bool, warning: str) -> bool:
        self.guild_member(viewer)
        with self.transaction() as connection:
            self._membership(connection, viewer)
            where = (
                t.character_sync.c.campaign_id == self.campaign_id,
                t.character_sync.c.user_id == str(viewer.user_id),
            )
            current = (
                connection.execute(sa.select(t.character_sync).where(*where)).mappings().first()
            )
            if not current or current["revision"] != revision:
                return False
            state = "complete" if complete else "pending"
            if current["state"] == state and current["warning"] == warning:
                return True
            result = connection.execute(
                t.character_sync.update()
                .where(
                    t.character_sync.c.campaign_id == self.campaign_id,
                    t.character_sync.c.user_id == str(viewer.user_id),
                    t.character_sync.c.revision == revision,
                )
                .values(state="complete" if complete else "pending", warning=warning)
            )
            if result.rowcount:
                self._audit(
                    connection,
                    viewer.user_id,
                    str(uuid4()),
                    "character.discord_sync_result",
                    {"revision": revision, "complete": complete},
                )
            return bool(result.rowcount)

    def invalidate_role(self, viewer: GuildViewer, key: str, expected: int) -> None:
        self.guild_member(viewer)
        with self.transaction() as connection:
            self._membership(connection, viewer)
            connection.execute(
                t.managed_roles.update()
                .where(
                    t.managed_roles.c.campaign_id == self.campaign_id,
                    t.managed_roles.c.key == key,
                    t.managed_roles.c.discord_id == str(expected),
                    t.managed_roles.c.state == "ready",
                )
                .values(state="pending", discord_id=None)
            )

    def claim_role(self, viewer: GuildViewer, key: str) -> tuple[str, int | None]:
        family, _, label = key.partition(":")
        if not (
            (family == "girl" and label in GIRL_TYPES)
            or (family == "frame" and label in FRAME_TYPES)
        ):
            raise WorkflowError("Only listed character-tag roles may be created.")
        self.guild_member(viewer)
        with self.transaction() as connection:
            self._membership(connection, viewer)
            where = (
                t.managed_roles.c.campaign_id == self.campaign_id,
                t.managed_roles.c.key == key,
            )
            row = connection.execute(sa.select(t.managed_roles).where(*where)).mappings().first()
            if row:
                if row["state"] == "ready":
                    return "ready", int(row["discord_id"])
                if row["state"] == "creating":
                    return "uncertain", None
                connection.execute(t.managed_roles.update().where(*where).values(state="creating"))
            else:
                connection.execute(
                    t.managed_roles.insert().values(
                        campaign_id=self.campaign_id, key=key, state="creating"
                    )
                )
            self._audit(
                connection, viewer.user_id, str(uuid4()), "character.role_reserved", {"key": key}
            )
            return "create", None

    def record_role(self, viewer: GuildViewer, key: str, identity: int | None) -> None:
        self.guild_member(viewer)
        with self.transaction() as connection:
            self._membership(connection, viewer)
            connection.execute(
                t.managed_roles.update()
                .where(
                    t.managed_roles.c.campaign_id == self.campaign_id, t.managed_roles.c.key == key
                )
                .values(
                    state="ready" if identity else "pending",
                    discord_id=str(identity) if identity else None,
                )
            )
            self._audit(
                connection, viewer.user_id, str(uuid4()), "character.role_recorded", {"key": key}
            )

    def managed_role_labels(self, viewer: GuildViewer) -> dict[int, str]:
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._membership(connection, viewer)
            return {
                int(row[0]): str(row[1]).split(":", 1)[1]
                for row in connection.execute(
                    sa.select(t.managed_roles.c.discord_id, t.managed_roles.c.key).where(
                        t.managed_roles.c.campaign_id == self.campaign_id,
                        t.managed_roles.c.state == "ready",
                    )
                )
            }

    def create_plan(self, viewer: GuildViewer, key: str) -> dict[str, Any]:
        self.administrator(viewer)

        def operation(connection: Connection) -> dict[str, Any]:
            identity = str(uuid4())
            connection.execute(
                t.plans.insert().values(
                    id=identity,
                    campaign_id=self.campaign_id,
                    actor_id=str(viewer.user_id),
                    expires=int(self.clock()) + 600,
                    template_version=1,
                )
            )
            return {"plan_id": identity, "template_version": 1}

        return self._write(viewer, key, "server.setup_planned", {}, operation)

    def _plan(
        self,
        connection: Connection,
        viewer: GuildViewer,
        identity: str,
        allow_expired: bool = False,
    ) -> None:
        self.administrator(viewer)
        self._binding_matches(connection)
        row = (
            connection.execute(
                sa.select(t.plans).where(
                    t.plans.c.id == identity,
                    t.plans.c.campaign_id == self.campaign_id,
                    t.plans.c.actor_id == str(viewer.user_id),
                )
            )
            .mappings()
            .first()
        )
        if not row or row["template_version"] != 1:
            raise WorkflowError("This setup confirmation does not belong to you or this campaign.")
        if not allow_expired and row["expires"] < self.clock():
            raise WorkflowError("Setup preview expired. Run /server setup again.")

    def claim_resource(self, viewer: GuildViewer, plan: str, key: str) -> tuple[str, int | None]:
        with self.transaction() as connection:
            self._plan(connection, viewer, plan)
            row = (
                connection.execute(
                    sa.select(t.resources).where(
                        t.resources.c.campaign_id == self.campaign_id, t.resources.c.key == key
                    )
                )
                .mappings()
                .first()
            )
            if row:
                if row["state"] == "ready":
                    return "ready", int(row["discord_id"])
                if row["state"] == "creating":
                    return "uncertain", None
                connection.execute(
                    t.resources.update()
                    .where(t.resources.c.campaign_id == self.campaign_id, t.resources.c.key == key)
                    .values(state="creating")
                )
            else:
                connection.execute(
                    t.resources.insert().values(
                        campaign_id=self.campaign_id, key=key, state="creating"
                    )
                )
            self._audit(
                connection,
                viewer.user_id,
                str(uuid4()),
                "server.resource_reserved",
                {"key": key, "plan_id": plan},
            )
            return "create", None

    def finish_resource(
        self, viewer: GuildViewer, plan: str, key: str, discord_id: int | None
    ) -> None:
        with self.transaction() as connection:
            self._plan(connection, viewer, plan, allow_expired=True)
            connection.execute(
                t.resources.update()
                .where(
                    t.resources.c.campaign_id == self.campaign_id,
                    t.resources.c.key == key,
                    t.resources.c.state == "creating",
                )
                .values(
                    state="ready" if discord_id else "pending",
                    discord_id=str(discord_id) if discord_id else None,
                )
            )
            self._audit(
                connection,
                viewer.user_id,
                str(uuid4()),
                "server.resource_recorded",
                {"key": key, "plan_id": plan, "state": "ready" if discord_id else "pending"},
            )
