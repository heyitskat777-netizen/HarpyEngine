"""Restore a diceless source's actual permission snapshot after its nested work releases."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameGateway
from girlframe.engine.m2_permissions import merge, records
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.p1_source_pause import active


class SourcePauseWorker:
    def __init__(self, game: GameService):
        self.game = game

    def _claim(self) -> dict[str, Any] | None:
        table = t.p1_source_pauses
        with self.game.store.transaction() as c:
            state = load_state(c, self.game.store.campaign_id)
            rows = (
                c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.state != "closed",
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                if row["state"] != "held" or active(state, row["id"]):
                    continue
                lock = self.game.lock(c, int(row["channel_id"]))
                layered_notice = c.scalar(
                    sa.select(t.p1_notices.c.id).where(
                        t.p1_notices.c.campaign_id == self.game.store.campaign_id,
                        t.p1_notices.c.channel_id == row["channel_id"],
                        t.p1_notices.c.state != "closed",
                    )
                )
                if (lock and lock["state"] != "released") or layered_notice:
                    continue
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.id == row["id"],
                    )
                    .values(state="restoring")
                )
            claimed = (
                c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.state.in_(("acquiring", "restoring")),
                        table.c.lease_until <= int(self.game.store.clock()),
                    )
                    .order_by(table.c.event_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if claimed is None:
                return None
            token = str(uuid4())
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == claimed["id"],
                )
                .values(claim_token=token, lease_until=int(self.game.store.clock()) + 120)
            )
            return dict(claimed) | dict(claim_token=token)

    def _update(self, job: dict[str, Any], **values: Any) -> None:
        table = t.p1_source_pauses
        with self.game.store.transaction() as c:
            result = c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == job["id"],
                    table.c.claim_token == job["claim_token"],
                )
                .values(**values)
            )
            if result.rowcount != 1:
                raise RuntimeError("Source pause lease is no longer owned")

    async def tick(self, gateway: GameGateway) -> bool:
        job = self._claim()
        if job is None:
            return False
        channel = int(job["channel_id"])
        try:
            snapshot = json.loads(job["snapshot_json"])
            restore = job["state"] == "restoring"
            if not snapshot and not restore:
                with self.game.store.engine.connect() as c:
                    scene = self.game.scene(c, channel)
                if scene["id"] != job["scene_id"]:
                    raise ValueError("The original source scene changed")
                snapshot = dict(
                    records=records(await gateway.snapshot(channel, scene["participants"]))
                )
                # Save the real original permissions before attempting any write.
                self._update(job, snapshot_json=json.dumps(snapshot))
            for record in snapshot.get("records", ()):
                current = await gateway.overwrite(channel, record)
                desired = merge(record, current, restore=restore)
                if desired != current:
                    await gateway.set_overwrite(channel, record, desired)
            for record in snapshot.get("records", ()):
                current = await gateway.overwrite(channel, record)
                if merge(record, current, restore=restore) != current:
                    raise ValueError("Source permission transition is not acknowledged")
            self._update(
                job,
                state="closed" if restore else "held",
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
                last_error=(
                    "Source channel permission delivery needs review; "
                    "saved choices and original snapshot are retained."
                ),
            )
        return True
