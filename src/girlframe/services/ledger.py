"""Campaign-scoped M1 transactions. No legacy-engine state or official Plays."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.rolls import DiceSource, OsDice, RollReceipt
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class CampaignLedger(OnboardingStore):
    def __init__(self, store: OnboardingStore, *, dice: DiceSource | None = None):
        super().__init__(store.engine, store.policy, store.clock)
        self.dice = dice if dice is not None else OsDice()
        self.rng_source = "os" if dice is None else "test_injected"

    def _revision(self, connection: Connection, expected: int) -> int:
        current = int(
            connection.scalar(
                sa.select(t.campaigns.c.revision).where(t.campaigns.c.id == self.campaign_id)
            )
            or 0
        )
        if type(expected) is not int or expected != current:
            raise WorkflowError("STALE_REVISION: campaign changed; retry with refreshed status.")
        return current

    def _paused(self, connection: Connection) -> bool:
        return (
            connection.execute(
                sa.select(t.pauses).where(t.pauses.c.campaign_id == self.campaign_id)
            ).first()
            is not None
        )

    def status(self, viewer: GuildViewer) -> dict[str, Any]:
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._binding_matches(connection)
            if not (viewer.is_administrator and self.policy.allow_guild_administrators):
                self._membership(connection, viewer)
            row = (
                connection.execute(
                    sa.select(t.campaigns).where(t.campaigns.c.id == self.campaign_id)
                )
                .mappings()
                .first()
            )
            return {
                "name": row["name"] if row else "Private campaign",
                "initialized": bool(row and row["initialized"]),
                "revision": row["revision"] if row else 0,
                "paused": self._paused(connection),
                "members": connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(t.members)
                    .where(
                        t.members.c.campaign_id == self.campaign_id, t.members.c.active.is_(True)
                    )
                ),
            }

    def create_campaign(
        self, viewer: GuildViewer, key: str, expected_revision: int, name: str
    ) -> dict[str, Any]:
        self.administrator(viewer)
        name = name.strip()
        if not 1 <= len(name) <= 80 or any(ord(char) < 32 for char in name):
            raise WorkflowError("Use a campaign name of 1–80 characters on one line.")

        def operation(connection: Connection) -> dict[str, Any]:
            revision = self._revision(connection, expected_revision)
            row = (
                connection.execute(
                    sa.select(t.campaigns).where(t.campaigns.c.id == self.campaign_id)
                )
                .mappings()
                .one()
            )
            if row["initialized"]:
                raise WorkflowError("Campaign already initialized. Existing data was preserved.")
            connection.execute(
                t.campaigns.update()
                .where(t.campaigns.c.id == self.campaign_id)
                .values(name=name, initialized=True)
            )
            return {"name": name, "revision": revision + 1}

        return self._write(viewer, key, "campaign.created", {"name": name}, operation)

    def safety(
        self, viewer: GuildViewer, key: str, expected_revision: int, *, pause: bool
    ) -> dict[str, Any]:
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._membership(connection, viewer)

        def operation(connection: Connection) -> dict[str, Any]:
            self._membership(connection, viewer)
            # An OOC pause must not lose a race against an unrelated metadata update.
            if not pause:
                self._revision(connection, expected_revision)
            where = (
                t.pauses.c.campaign_id == self.campaign_id,
                t.pauses.c.user_id == str(viewer.user_id),
            )
            exists = connection.execute(sa.select(t.pauses).where(*where)).first()
            if pause and not exists:
                connection.execute(
                    t.pauses.insert().values(
                        campaign_id=self.campaign_id, user_id=str(viewer.user_id)
                    )
                )
            elif not pause:
                connection.execute(t.pauses.delete().where(*where))
            return {"paused": self._paused(connection), "your_pause": pause}

        return self._write(viewer, key, "safety.changed", {"pause": pause}, operation)

    def ledger_channel(self, connection: Connection) -> str | None:
        return connection.scalar(
            sa.select(t.resources.c.discord_id).where(
                t.resources.c.campaign_id == self.campaign_id,
                t.resources.c.key == "ledger",
                t.resources.c.state == "ready",
            )
        )

    def roll_basic(
        self, viewer: GuildViewer, key: str, expected_revision: int, *, publish: bool = False
    ) -> RollReceipt:
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._membership(connection, viewer)

        def operation(connection: Connection) -> dict[str, Any]:
            self._membership(connection, viewer)
            revision = self._revision(connection, expected_revision)
            if self._paused(connection):
                raise WorkflowError("SAFETY_PAUSED: new rolls are paused. No dice were sampled.")
            character = (
                connection.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.campaign_id,
                        t.characters.c.user_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if not character:
                raise WorkflowError("Save your own draft before using the raw dice test.")
            channel = self.ledger_channel(connection) if publish else None
            if publish and not channel:
                raise WorkflowError("Run /server setup before publishing rolls.")
            # Every precondition precedes RNG. Inbox replay bypasses this operation.
            faces = self.dice.roll()
            identity, event_id = str(uuid4()), str(uuid4())
            receipt = RollReceipt(
                id=identity,
                campaign_id=self.campaign_id,
                event_id=event_id,
                actor_id=str(viewer.user_id),
                character_id=character["id"],
                callsign=json.loads(character["public_json"])["callsign"],
                faces=faces,
                total=sum(faces),
                rolled_utc=datetime.now(UTC).isoformat(),
                revision=revision + 2,
                visibility="campaign" if publish else "private",
                rng_source="os" if self.rng_source == "os" else "test_injected",
                idempotency_key=f"discord:{key}",
            )
            self._audit(
                connection,
                viewer.user_id,
                key,
                "dice.rolled",
                {"roll_id": identity},
                event_id=event_id,
                visibility=receipt.visibility,
            )
            connection.execute(
                t.rolls.insert().values(
                    id=identity,
                    campaign_id=self.campaign_id,
                    event_id=event_id,
                    user_id=str(viewer.user_id),
                    character_id=character["id"],
                    command_key=key,
                    visibility=receipt.visibility,
                    receipt_json=receipt.model_dump_json(),
                )
            )
            recorded = self._audit(
                connection,
                viewer.user_id,
                key,
                "dice.recorded",
                {"roll_id": identity},
                event_index=1,
                visibility=receipt.visibility,
            )
            if channel:
                connection.execute(
                    t.outbox.insert().values(
                        id=str(uuid4()),
                        campaign_id=self.campaign_id,
                        event_id=recorded,
                        roll_id=identity,
                        channel_id=channel,
                        nonce=uuid4().hex[:24],
                    )
                )
            return receipt.model_dump(mode="json")

        result = self._write(
            viewer, key, "dice.basic_requested", {"publish": publish}, operation, auto_audit=False
        )
        return RollReceipt.model_validate_json(json.dumps(result))

    def get_roll_receipt(self, viewer: GuildViewer, identity: str) -> RollReceipt:
        self.guild_member(viewer)
        with self.engine.connect() as connection:
            self._membership(connection, viewer)
            row = (
                connection.execute(
                    sa.select(t.rolls).where(
                        t.rolls.c.campaign_id == self.campaign_id,
                        t.rolls.c.id == identity,
                        sa.or_(
                            t.rolls.c.visibility == "campaign",
                            t.rolls.c.user_id == str(viewer.user_id),
                        ),
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkflowError("Receipt unavailable to you in this campaign.")
            return RollReceipt.model_validate_json(row["receipt_json"])

    def list_events(
        self, viewer: GuildViewer, *, before: int | None = None, limit: int = 8
    ) -> list[dict[str, Any]]:
        self.guild_member(viewer)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise WorkflowError("Ledger page size must be 1–20.")
        with self.engine.connect() as connection:
            self._membership(connection, viewer)
            rows = connection.execute(
                sa.select(t.events)
                .where(
                    t.events.c.campaign_id == self.campaign_id,
                    t.events.c.seq < (before if before is not None else 2**63 - 1),
                    sa.or_(
                        t.events.c.visibility == "campaign",
                        t.events.c.actor_id == str(viewer.user_id),
                    ),
                )
                .order_by(t.events.c.seq.desc())
                .limit(limit)
            ).mappings()
            # Explicit fields only. Snapshot bodies and generic payloads never escape here.
            return [
                {
                    "seq": row["seq"],
                    "id": row["id"],
                    "kind": row["kind"],
                    "roll_id": json.loads(row["payload_json"]).get("roll_id")
                    if row["kind"] in {"dice.rolled", "dice.recorded"}
                    else None,
                }
                for row in rows
            ]

    def claim_delivery(self) -> dict[str, Any] | None:
        now = int(self.clock())
        with self.transaction() as connection:
            self._binding_matches(connection)
            row = (
                connection.execute(
                    sa.select(t.outbox)
                    .where(
                        t.outbox.c.campaign_id == self.campaign_id,
                        t.outbox.c.state != "sent",
                        t.outbox.c.not_before <= now,
                        t.outbox.c.lease_until <= now,
                    )
                    .order_by(t.outbox.c.id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if self.ledger_channel(connection) != row["channel_id"]:
                return None  # Never redirect previously queued data to a different channel.
            token = str(uuid4())
            connection.execute(
                t.outbox.update()
                .where(t.outbox.c.id == row["id"])
                .values(
                    state="inflight",
                    attempts=row["attempts"] + 1,
                    claim_token=token,
                    lease_until=now + 120,
                )
            )
            receipt_json = connection.scalar(
                sa.select(t.rolls.c.receipt_json).where(
                    t.rolls.c.id == row["roll_id"],
                    t.rolls.c.campaign_id == self.campaign_id,
                    t.rolls.c.visibility == "campaign",
                )
            )
            if receipt_json is None:
                raise WorkflowError("Invalid delivery reference.")
            return {
                **dict(row),
                "claim_token": token,
                "receipt_json": receipt_json,
                "attempts": row["attempts"] + 1,
            }

    def mark_delivery(self, job: dict[str, Any], message_id: int | None) -> bool:
        with self.transaction() as connection:
            result = connection.execute(
                t.outbox.update()
                .where(
                    t.outbox.c.campaign_id == self.campaign_id,
                    t.outbox.c.id == job["id"],
                    t.outbox.c.claim_token == job["claim_token"],
                    t.outbox.c.state == "inflight",
                )
                .values(
                    state="sent" if message_id is not None else "pending",
                    message_id=str(message_id) if message_id is not None else None,
                    lease_until=0,
                    claim_token=None,
                    not_before=int(self.clock()) + min(300, 2 ** min(job["attempts"], 8)),
                    last_error="" if message_id is not None else "DELIVERY_UNAVAILABLE",
                )
            )
            return bool(result.rowcount)

    def rebuild_projections(self) -> int:
        """Trusted local operator only; no Discord identity impersonation or RNG."""
        with self.transaction() as connection:
            if not self._binding_matches(connection):
                raise WorkflowError("Campaign is not initialized.")
            rows = connection.execute(
                sa.select(t.snapshots)
                .where(t.snapshots.c.campaign_id == self.campaign_id)
                .order_by(t.snapshots.c.revision)
            ).mappings()
            latest = {row["user_id"]: dict(row) for row in rows}
            current = (
                connection.execute(
                    sa.select(t.characters).where(t.characters.c.campaign_id == self.campaign_id)
                )
                .mappings()
                .all()
            )
            if any(row["user_id"] not in latest for row in current):
                raise WorkflowError("Missing snapshot; restore a verified backup instead.")
            for owner, row in latest.items():
                values = dict(
                    id=row["character_id"],
                    revision=row["revision"],
                    public_json=row["public_json"],
                    private_json=row["private_json"],
                )
                where = (
                    t.characters.c.campaign_id == self.campaign_id,
                    t.characters.c.user_id == owner,
                )
                if connection.execute(sa.select(t.characters).where(*where)).first():
                    connection.execute(t.characters.update().where(*where).values(**values))
                else:
                    connection.execute(
                        t.characters.insert().values(
                            campaign_id=self.campaign_id, user_id=owner, **values
                        )
                    )
            self._audit(
                connection,
                "system:local_operator",
                str(uuid4()),
                "projections.rebuilt",
                {"characters": len(latest)},
            )
            return len(latest)

    def public_export(self) -> dict[str, Any]:
        """Trusted operator export, deliberately excludes private receipts and identities."""
        with self.engine.connect() as connection:
            self._binding_matches(connection)
            sheets = connection.execute(
                sa.select(t.characters.c.user_id, t.characters.c.public_json).where(
                    t.characters.c.campaign_id == self.campaign_id
                )
            ).all()
            receipts = connection.execute(
                sa.select(t.rolls.c.receipt_json).where(
                    t.rolls.c.campaign_id == self.campaign_id, t.rolls.c.visibility == "campaign"
                )
            ).scalars()
            safe = {"id", "callsign", "faces", "total", "rolled_utc", "kind", "visibility"}
            from girlframe.services.m2_state import load_state, public_sheet

            state = load_state(connection, self.campaign_id)
            public = [
                public_sheet(state.sheets[uid], state) if uid in state.sheets else json.loads(body)
                for uid, body in sheets
            ]
            return {
                "schema_version": 1,
                "sheets": public,
                "rolls": [{k: v for k, v in json.loads(r).items() if k in safe} for r in receipts],
            }
