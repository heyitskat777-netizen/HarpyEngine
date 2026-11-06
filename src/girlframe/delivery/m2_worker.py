"""Durable scene lock, safe publication and recovery worker; never chooses for humans."""

import asyncio
import json
from typing import Any, Protocol
from uuid import uuid4

import sqlalchemy as sa

from girlframe.database import tables as t
from girlframe.engine.m2_permissions import LOCK_MASK, merge, records
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class GameGateway(Protocol):
    async def snapshot(self, channel: int, participants: list[int]) -> dict[str, Any]: ...
    async def overwrite(self, channel: int, target: dict[str, Any]) -> dict[str, int] | None: ...
    async def set_overwrite(
        self, channel: int, target: dict[str, Any], value: dict[str, int] | None
    ) -> None: ...
    async def publish(self, channel: int, payload: dict[str, Any], nonce: str) -> int: ...
    async def find(self, channel: int, nonce: str) -> int | None: ...
    async def publish_private(self, recipient: int, payload: dict[str, Any], nonce: str) -> int: ...
    async def find_private(self, recipient: int, nonce: str) -> int | None: ...
    async def actor(self, identity: int) -> GuildViewer: ...


class GameWorker:
    def __init__(self, game: GameService):
        self.game = game

    def claim(self, table_name: str, states: tuple[str, ...]) -> dict[str, Any] | None:
        table = t.m2[table_name]
        now = int(self.game.store.clock())
        with self.game.store.transaction() as c:
            row = (
                c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.state.in_(states),
                        table.c.lease_until <= now,
                    )
                    .order_by(sa.literal_column("rowid"))
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            token = str(uuid4())
            identity = row["channel_id"] if table_name == "m2_locks" else row["id"]
            column = table.c.channel_id if table_name == "m2_locks" else table.c.id
            c.execute(
                table.update()
                .where(table.c.campaign_id == self.game.store.campaign_id, column == identity)
                .values(claim_token=token, lease_until=now + 120)
            )
            return dict(row) | {"claim_token": token}

    def update_lock(self, job: dict[str, Any], state: str, body: dict[str, Any]) -> bool:
        table = t.m2["m2_locks"]
        with self.game.store.transaction() as c:
            result = c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.channel_id == job["channel_id"],
                    table.c.action_id == job["action_id"],
                    table.c.claim_token == job["claim_token"],
                )
                .values(
                    state=state,
                    body_json=json.dumps(body, sort_keys=True),
                    claim_token=None,
                    lease_until=0,
                )
            )
            return bool(result.rowcount)

    def save_lock_body(self, job: dict[str, Any], body: dict[str, Any]) -> None:
        table = t.m2["m2_locks"]
        with self.game.store.transaction() as c:
            result = c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.channel_id == job["channel_id"],
                    table.c.claim_token == job["claim_token"],
                )
                .values(body_json=json.dumps(body, sort_keys=True))
            )
            if not result.rowcount:
                raise WorkflowError("A newer lock worker owns this recovery job.")

    def action(self, identity: str) -> dict[str, Any]:
        with self.game.store.engine.connect() as c:
            return self.game.action(c, identity)

    async def acquire(self, job: dict[str, Any], gateway: GameGateway) -> None:
        body = json.loads(job["body_json"])
        channel = int(job["channel_id"])
        try:
            action = self.action(job["action_id"])
            if action["state"] == "aborted":
                self.update_lock(job, "releasing", body)
                return
            self.game.gate()
            if "records" not in body:
                snapshot = await gateway.snapshot(channel, action["data"]["participants"])
                body = {
                    "records": records(snapshot),
                    "prompt_nonce": str(int(uuid4()) % (2**63 - 1)),
                    "prompt_state": "pending",
                }
                self.save_lock_body(job, body)
            for record in body["records"]:
                current = await gateway.overwrite(channel, record)
                desired = merge(record, current, restore=False)
                if desired != current:
                    await gateway.set_overwrite(channel, record, desired)
            # Confirm every owned bit before allowing a spend or roll.
            for record in body["records"]:
                current = await gateway.overwrite(channel, record)
                mask = record["mask"]
                if current is None or any(
                    (current[k] & mask) != (record["applied"][k] & mask) for k in ("allow", "deny")
                ):
                    raise ValueError("The channel lock was not acknowledged")
            if body["prompt_state"] == "uncertain":
                message = await gateway.find(channel, body["prompt_nonce"])
                if message is None:
                    body["issue"] = "Control-message delivery needs staff reconciliation."
                    self.update_lock(job, "review", body)
                    return
                body["message_id"] = message
                body["prompt_state"] = "sent"
            if body["prompt_state"] == "pending":
                body["prompt_state"] = "uncertain"
                self.save_lock_body(job, body)
                message = await gateway.publish(
                    channel, {"kind": "control", "action_id": action["id"]}, body["prompt_nonce"]
                )
                body["message_id"] = message
                body["prompt_state"] = "sent"
            self.update_lock(job, "held", body)
        except Exception:
            # Unknown API outcomes are reconciled from persisted intent, never guessed.
            body["issue"] = "Lock acquisition needs staff review; no new RNG/spend was authorized."
            self.update_lock(job, "review", body)

    async def restore(self, job: dict[str, Any], gateway: GameGateway) -> None:
        body = json.loads(job["body_json"])
        channel = int(job["channel_id"])
        try:
            for record in body.get("records", []):
                current = await gateway.overwrite(channel, record)
                desired = merge(record, current, restore=True)
                if desired != current:
                    await gateway.set_overwrite(channel, record, desired)
            for record in body.get("records", []):
                current = await gateway.overwrite(channel, record)
                if merge(record, current, restore=True) != current:
                    raise ValueError("Restoration was not acknowledged")
            self.update_lock(job, "released", body)
        except Exception:
            body["issue"] = (
                "Permission restoration conflicts with staff edits; manual recovery required."
            )
            self.update_lock(job, "review", body)

    def delivery_result(self, job: dict[str, Any], state: str, message: int | None) -> None:
        table = t.m2["m2_outbox"]
        with self.game.store.transaction() as c:
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.game.store.campaign_id,
                    table.c.id == job["id"],
                    table.c.claim_token == job["claim_token"],
                )
                .values(
                    state=state,
                    message_id=str(message) if message else None,
                    lease_until=0,
                    claim_token=None,
                    attempts=job["attempts"] + 1,
                )
            )

    async def deliver(self, job: dict[str, Any], gateway: GameGateway) -> None:
        try:
            payload = json.loads(job["body_json"])
            recipient = payload.get("private_recipient")
            if job["state"] in ("uncertain", "sending"):
                message = (
                    await gateway.find_private(int(recipient), job["nonce"])
                    if recipient is not None
                    else await gateway.find(int(job["channel_id"]), job["nonce"])
                )
                self.delivery_result(job, "sent" if message else "review", message)
                return
            table = t.m2["m2_outbox"]
            with self.game.store.transaction() as c:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == self.game.store.campaign_id,
                        table.c.id == job["id"],
                        table.c.claim_token == job["claim_token"],
                    )
                    .values(state="sending")
                )
            payload["action_id"] = job["action_id"]
            message = (
                await gateway.publish_private(int(recipient), payload, job["nonce"])
                if recipient is not None
                else await gateway.publish(int(job["channel_id"]), payload, job["nonce"])
            )
            self.delivery_result(job, "sent", message)
        except Exception:
            self.delivery_result(job, "uncertain", None)

    def roots_ready(self) -> None:
        with self.game.store.transaction() as c:
            locks = t.m2["m2_locks"]
            actions = t.m2["m2_actions"]
            outbox = t.m2["m2_outbox"]
            rows = [
                dict(x)
                for x in c.execute(
                    sa.select(actions).where(actions.c.campaign_id == self.game.store.campaign_id)
                ).mappings()
            ]
            for lock in (
                c.execute(
                    sa.select(locks).where(
                        locks.c.campaign_id == self.game.store.campaign_id, locks.c.state == "held"
                    )
                )
                .mappings()
                .all()
            ):
                root = next((x for x in rows if x["id"] == lock["action_id"]), None)
                if root is None or root["state"] not in ("complete", "aborted"):
                    continue
                ids = {root["id"]}
                while True:
                    expanded = ids | {x["id"] for x in rows if x["parent_id"] in ids}
                    if expanded == ids:
                        break
                    ids = expanded
                if any(x["state"] not in ("complete", "aborted") for x in rows if x["id"] in ids):
                    continue
                if c.execute(
                    sa.select(outbox.c.id).where(
                        outbox.c.campaign_id == self.game.store.campaign_id,
                        outbox.c.action_id.in_(ids),
                        outbox.c.state != "sent",
                    )
                ).first():
                    continue
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.game.store.campaign_id,
                        locks.c.channel_id == lock["channel_id"],
                    )
                    .values(state="releasing")
                )

    async def advance(self, gateway: GameGateway) -> None:
        self.game.gate()
        with self.game.store.engine.connect() as c:
            rows = [
                dict(x)
                for x in c.execute(
                    sa.select(t.m2["m2_actions"]).where(
                        t.m2["m2_actions"].c.campaign_id == self.game.store.campaign_id,
                        t.m2["m2_actions"].c.state.in_(("acquiring", "ready_to_roll")),
                    )
                ).mappings()
            ]
        for row in rows:
            action = self.action(row["id"])
            with self.game.store.engine.connect() as c:
                lock = self.game.lock(c, row["channel_id"])
                if not lock or lock["state"] != "held":
                    continue
            try:
                if action["data"]["play"] in ("flirt_followthrough", "reject_tag"):
                    from girlframe.services.m2_choices import ChoiceEngine

                    with self.game.store.transaction() as c:
                        self.game.unpaused(c)
                        current = self.game.action(c, row["id"])
                        if current["state"] != "acquiring":
                            continue
                        from girlframe.services.m2_state import load_state

                        state = load_state(c, self.game.store.campaign_id)
                        item = next(
                            x
                            for x in state.obligations
                            if x.id == current["data"]["obligation_id"] and x.state == "pending"
                        )
                        cute_rejection_event = None
                        if item.kind == "flirt_followthrough":
                            self.game.request(c, current, item.target, "followthrough_confirm")
                            self.game.save_action(c, current, state="awaiting_choices")
                        else:
                            sheet = state.sheets[str(item.owner)]
                            from girlframe.engine.m3_control_ritual import tags as ritual_tags
                            from girlframe.services.m3_cute_uniforms import reject as reject_uniform
                            from girlframe.services.m3_cute_uniforms import tags as uniform_tags

                            tag = next(
                                x
                                for x in sheet.tags
                                + ritual_tags(state, item.owner)
                                + uniform_tags(state, item.owner)
                                if x.id == item.details["tag"]
                            )
                            cute_rejection_event = str(uuid4())
                            if not reject_uniform(
                                self.game, c, state, current, cute_rejection_event
                            ):
                                if sheet.girl == "NEWGIRL" and tag.giver == sheet.mentor:
                                    raise WorkflowError("A Newgirl cannot reject its Mentor's Tag.")
                                sheet.tags = [x for x in sheet.tags if x.id != tag.id]
                            sheet.revision += 1
                            ChoiceEngine(self.game).tag_resolved(state, item.owner, tag.id)
                            ChoiceEngine(self.game).finish(c, state, current)
                            self.game.save_action(c, current)
                        ready_event = self.game.event(
                            c,
                            "system:confirmed_followthrough",
                            "m2.followthrough_ready:" + row["id"],
                            "m2.followthrough_ready",
                            state,
                            action_id=row["id"],
                            event_id=cute_rejection_event,
                        )
                        if current["data"].get("cute_uniform_rejection"):
                            from girlframe.services.m3_cute_uniforms import synchronize_rejection

                            synchronize_rejection(self.game, c, current, ready_event)
                elif action["data"]["play"] == "am_code_maintenance":
                    with self.game.store.transaction() as c:
                        self.game.unpaused(c)
                        current = self.game.action(c, row["id"])
                        if current["state"] != "acquiring":
                            continue
                        self.game.request(
                            c,
                            current,
                            int(row["actor_id"]),
                            "am_code_prepare",
                            dict(
                                maintenance=current["data"]["am_code_source"]["maintenance"],
                                target=current["data"]["am_code_source"]["target"],
                            ),
                        )
                        self.game.save_action(c, current, state="awaiting_choices")
                        self.game.event(
                            c,
                            "system:confirmed_am_code",
                            "am.code.ready:" + row["id"],
                            "m3.am_code_preparation_ready",
                            action_id=row["id"],
                        )
                elif action["data"]["play"] == "am_discovery":
                    with self.game.store.transaction() as c:
                        self.game.unpaused(c)
                        current = self.game.action(c, row["id"])
                        if current["state"] != "acquiring":
                            continue
                        self.game.request(
                            c,
                            current,
                            int(row["actor_id"]),
                            "am_prepare",
                            dict(
                                discovery=current["data"]["am_source"]["discovery"],
                                target=current["data"]["am_source"]["target"],
                            ),
                        )
                        self.game.save_action(c, current, state="awaiting_choices")
                        self.game.event(
                            c,
                            "system:confirmed_am_discovery",
                            "am.ready:" + row["id"],
                            "m3.am_preparation_ready",
                            action_id=row["id"],
                        )
                elif action["data"]["play"] == "receive_orders":
                    with self.game.store.transaction() as c:
                        self.game.unpaused(c)
                        current = self.game.action(c, row["id"])
                        if current["state"] != "acquiring":
                            continue
                        self.game.request(c, current, int(row["actor_id"]), "order_response")
                        self.game.save_action(c, current, state="awaiting_choices")
                        self.game.event(
                            c,
                            "system:confirmed_order",
                            "m2.order_ready:" + row["id"],
                            "m2.order_response_ready",
                            action_id=row["id"],
                        )
                else:
                    viewer = await gateway.actor(int(row["actor_id"]))
                    await asyncio.to_thread(
                        self.game.roll, viewer, "m2.confirmed_roll:" + row["id"], row["id"]
                    )
            except WorkflowError:
                continue  # Paused/stale inputs stay recoverable and cannot spend or reroll.

    async def check_held(self, gateway: GameGateway) -> None:
        with self.game.store.engine.connect() as c:
            table = t.m2["m2_locks"]
            rows = [
                dict(x)
                for x in c.execute(
                    sa.select(table).where(
                        table.c.campaign_id == self.game.store.campaign_id, table.c.state == "held"
                    )
                ).mappings()
            ]
        for row in rows:
            body = json.loads(row["body_json"])
            try:
                action = self.action(row["action_id"])
                snapshot = await gateway.snapshot(
                    int(row["channel_id"]), action["data"]["participants"]
                )
                known = {(x["kind"], str(x["id"])) for x in body["records"]}
                for overwrite in snapshot["overwrites"]:
                    if (overwrite["kind"], str(overwrite["id"])) not in known and int(
                        overwrite["allow"]
                    ) & LOCK_MASK:
                        raise ValueError("New channel send allow conflicts with lock")
                for record in body["records"]:
                    current = await gateway.overwrite(int(row["channel_id"]), record)
                    if current is None or any(
                        (current[k] & record["mask"]) != (record["applied"][k] & record["mask"])
                        for k in ("allow", "deny")
                    ):
                        raise ValueError("Channel lock drift")
            except Exception:
                body["issue"] = (
                    "Channel lock drift or unavailable permissions; staff reconciliation required."
                )
                with self.game.store.transaction() as c:
                    c.execute(
                        table.update()
                        .where(
                            table.c.campaign_id == self.game.store.campaign_id,
                            table.c.channel_id == row["channel_id"],
                            table.c.action_id == row["action_id"],
                            table.c.state == "held",
                        )
                        .values(state="review", body_json=json.dumps(body))
                    )

    async def tick(self, gateway: GameGateway) -> None:
        lock = await asyncio.to_thread(self.claim, "m2_locks", ("acquiring", "releasing"))
        if lock:
            if lock["state"] == "acquiring":
                await self.acquire(lock, gateway)
            else:
                await self.restore(lock, gateway)
        await self.check_held(gateway)
        try:
            await self.advance(gateway)
        except WorkflowError:
            pass
        job = await asyncio.to_thread(self.claim, "m2_outbox", ("pending", "uncertain", "sending"))
        if job:
            await self.deliver(job, gateway)
        await asyncio.to_thread(self.roots_ready)
