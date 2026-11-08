"""Finite request notices and scoped permission restoration; delivery uncertainty is durable."""

import json
from typing import Any, Protocol
from uuid import uuid4

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameGateway
from girlframe.engine.m2_permissions import merge, records
from girlframe.engine.p1_facilitator import Recipient
from girlframe.services.m2_game import GameService
from girlframe.services.p1_facilitator import configured, pending


class FacilitatorGateway(GameGateway, Protocol):
    async def notice(self, channel: int, recipient: Recipient, request: str, nonce: str) -> int: ...
    async def find_notice(self, channel: int, nonce: str) -> int | None: ...
    async def register_notice(self, message: int, request: str) -> None: ...


class FacilitatorWorker:
    def __init__(self, game: GameService):
        self.game = game
        self.registered = False

    def _update(self, job: dict[str, Any], **values: Any) -> None:
        table = t.p1_notices
        with self.game.store.transaction() as c:
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == job["id"],
                    table.c.claim_token == job["claim_token"],
                )
                .values(**values)
            )

    def _claim(self) -> dict[str, Any] | None:
        table = t.p1_notices
        with self.game.store.transaction() as c:
            rows = list(
                c.execute(
                    sa.select(table).where(table.c.campaign_id == self.game.store.campaign_id)
                ).mappings()
            )
            for existing in rows:
                if existing["state"] in (
                    "paused",
                    "blocked_configuration",
                    "review",
                    "pending",
                    "uncertain",
                ) and not pending(self.game, c, int(existing["channel_id"])):
                    c.execute(
                        table.update()
                        .where(
                            table.c.campaign_id == self.game.store.campaign_id,
                            table.c.id == existing["id"],
                        )
                        .values(state="restoring")
                    )
            row = (
                c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.state.in_(("pending", "uncertain", "restoring")),
                        table.c.lease_until <= int(self.game.store.clock()),
                    )
                    .order_by(table.c.event_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            token = str(uuid4())
            c.execute(
                table.update()
                .where(table.c.campaign_id == self.game.store.campaign_id, table.c.id == row["id"])
                .values(
                    claim_token=token,
                    lease_until=int(self.game.store.clock()) + 120,
                    attempts=row["attempts"] + 1,
                )
            )
            return dict(row) | dict(claim_token=token)

    async def tick(self, gateway: FacilitatorGateway) -> bool:
        if not self.registered:
            with self.game.store.engine.connect() as c:
                saved = list(
                    c.execute(
                        sa.select(t.p1_notices.c.message_id, t.p1_notices.c.request_id).where(
                            t.p1_notices.c.campaign_id == self.game.store.campaign_id,
                            t.p1_notices.c.message_id.is_not(None),
                        )
                    ).mappings()
                )
            for item in saved:
                await gateway.register_notice(int(item["message_id"]), item["request_id"])
            self.registered = True
        job = self._claim()
        if job is None:
            return False
        channel = int(job["channel_id"])
        snapshot = json.loads(job["snapshot_json"])
        try:
            if job["state"] == "restoring":
                for record in snapshot.get("records", []):
                    current = await gateway.overwrite(channel, record)
                    desired = merge(record, current, restore=True)
                    if desired != current:
                        await gateway.set_overwrite(channel, record, desired)
                for record in snapshot.get("records", []):
                    current = await gateway.overwrite(channel, record)
                    if merge(record, current, restore=True) != current:
                        raise ValueError("Permission restoration is not acknowledged")
                self._update(job, state="closed", claim_token=None, lease_until=0, last_error="")
                return True
            with self.game.store.engine.connect() as c:
                requests = pending(self.game, c, channel)
                recipient = configured(self.game, c)
                lock = self.game.lock(c, channel)
                other = (
                    c.execute(
                        sa.select(t.p1_notices.c.id, t.p1_notices.c.snapshot_json).where(
                            t.p1_notices.c.campaign_id == self.game.store.campaign_id,
                            t.p1_notices.c.channel_id == str(channel),
                            t.p1_notices.c.id != job["id"],
                            t.p1_notices.c.state != "closed",
                        )
                    )
                    .mappings()
                    .all()
                )
                scene = self.game.scene(c, channel)
            if not requests:
                self._update(job, state="restoring", claim_token=None, lease_until=0)
                return True
            if not snapshot:
                owner = next(
                    (x for x in other if json.loads(x["snapshot_json"]).get("records")), None
                )
                if lock and lock["state"] != "released":
                    snapshot = dict(existing_action=lock["action_id"])
                elif owner:
                    snapshot = dict(shared_pause=owner["id"])
                else:
                    snapshot = dict(
                        records=records(await gateway.snapshot(channel, scene["participants"]))
                    )
                self._update(job, snapshot_json=json.dumps(snapshot))
            for record in snapshot.get("records", []):
                current = await gateway.overwrite(channel, record)
                desired = merge(record, current, restore=False)
                if desired != current:
                    await gateway.set_overwrite(channel, record, desired)
            for record in snapshot.get("records", []):
                current = await gateway.overwrite(channel, record)
                if current != merge(record, current, restore=False):
                    raise ValueError("Pause permission is not acknowledged")
            original = (
                Recipient.model_validate_json(job["recipient_json"])
                if job["recipient_json"] != "null"
                else None
            )
            if original is None:
                self._update(
                    job,
                    state="blocked_configuration",
                    claim_token=None,
                    lease_until=0,
                    last_error="No designated human facilitator; configuration required.",
                )
                return True
            if recipient != original:
                self._update(
                    job,
                    state="paused",
                    claim_token=None,
                    lease_until=0,
                    last_error="Recipient assignment superseded; current notice is separate.",
                )
                return True
            if job["state"] == "uncertain":
                message = await gateway.find_notice(channel, job["nonce"])
                if message is None:
                    self._update(
                        job,
                        state="review",
                        claim_token=None,
                        lease_until=0,
                        last_error="Delivery uncertain; reconcile before repeating the notice.",
                    )
                    return True
            else:
                self._update(job, state="uncertain")
                message = await gateway.notice(channel, original, job["request_id"], job["nonce"])
            await gateway.register_notice(message, job["request_id"])
            self._update(
                job,
                state="paused",
                message_id=str(message),
                claim_token=None,
                lease_until=0,
                last_error="",
            )
        except Exception:
            self._update(
                job,
                state="review",
                claim_token=None,
                lease_until=0,
                last_error="Channel permission or delivery needs review; request remains pending.",
            )
        return True
