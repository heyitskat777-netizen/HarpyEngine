"""Best-effort Discord DMs for newly filed, recipient-owned Inbox items."""

import asyncio
import logging
import secrets
import sqlite3
from contextlib import closing
from hashlib import sha256
from time import time
from uuid import UUID

import discord
from sqlalchemy.exc import SQLAlchemyError

from girlframe.services.onboarding import WorkflowError

logger = logging.getLogger("harpy_activity.discord")
DELIVERY_WINDOW = 120
NOTICES = {
    "bond": "A pilot filed a starting Bond proposal for your response.",
    "mission": "The Handler filed a mission offer for your response.",
    "mission_review": "A mission is ready for your Handler review.",
    "scene_invite": "A scene host invited you to join a scene.",
    "play": "HarpyEngine assigned you a Play choice.",
    "play_work": "HarpyEngine assigned you a Play follow-up.",
    "enrollment": "An enrollment choice needs your response.",
    "off_duty": "An Off-Duty assignment needs your response.",
    "battlefield": "Battlefield is waiting on your turn or review.",
}
DESTINATIONS = {
    "play": "Open HarpyEngine to review the choice in the scene or on the Battlefield.",
    "battlefield": "Open the Battlefield tab in HarpyEngine.",
    "off_duty": "Open Off-Duty in HarpyEngine.",
    "mission_review": "Open the Missions tab in HarpyEngine.",
}


class InboxNotices:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS notices (
                campaign TEXT NOT NULL, kind TEXT NOT NULL, record TEXT NOT NULL,
                recipient TEXT NOT NULL, created REAL NOT NULL, next_attempt REAL NOT NULL,
                finished INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (campaign, kind, record, recipient)
            )""")

            db.execute("CREATE TABLE IF NOT EXISTS observed_campaigns (campaign TEXT PRIMARY KEY)")
            db.execute("BEGIN IMMEDIATE")
            if "outcome" not in {column[1] for column in db.execute("PRAGMA table_info(notices)")}:
                db.execute("ALTER TABLE notices ADD COLUMN outcome TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS notice_receipts (
                id TEXT PRIMARY KEY, campaign TEXT NOT NULL, sender TEXT NOT NULL,
                kind TEXT NOT NULL, record TEXT NOT NULL,
                UNIQUE (campaign, sender, kind, record)
            )""")

    def sync(self, campaign, items):
        """Record the first snapshot silently, then file newly assigned work."""
        stamp = time()
        campaign = str(campaign)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            first = db.execute(
                "INSERT OR IGNORE INTO observed_campaigns VALUES (?)", (campaign,)
            ).rowcount
            db.executemany(
                "INSERT OR IGNORE INTO notices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    (
                        campaign,
                        kind,
                        record,
                        str(recipient),
                        stamp,
                        stamp,
                        first,
                        "skipped" if first else None,
                    )
                    for kind, record, recipient in items
                ),
            )

    def file(self, campaign, kind, record, recipients):
        if kind not in NOTICES:
            raise ValueError("Unsupported Inbox notice.")
        stamp = time()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany(
                "INSERT OR IGNORE INTO notices VALUES (?, ?, ?, ?, ?, ?, 0, NULL)",
                (
                    (str(campaign), kind, record, str(recipient), stamp, stamp)
                    for recipient in recipients
                ),
            )

    def claim(self):
        stamp = time()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            item = db.execute(
                """SELECT campaign, kind, record, recipient FROM notices
                   WHERE finished=0 AND created>=? AND next_attempt<=?
                   ORDER BY created LIMIT 1""",
                (stamp - DELIVERY_WINDOW, stamp),
            ).fetchone()
            if item:
                db.execute(
                    """UPDATE notices SET next_attempt=?
                       WHERE (campaign, kind, record, recipient)=(?, ?, ?, ?)""",
                    (stamp + 30, *item),
                )
            return item

    def finish(self, item, outcome):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """UPDATE notices SET finished=1, outcome=?
                   WHERE (campaign, kind, record, recipient)=(?, ?, ?, ?)""",
                (outcome, *item),
            )

    def sender_receipt(self, campaign, sender, kind, record):
        scope = (str(campaign), str(sender), kind, record)
        with closing(sqlite3.connect(self.path)) as db, db:
            if not db.execute(
                "SELECT 1 FROM notices WHERE (campaign, kind, record)=(?, ?, ?)",
                (scope[0], kind, record),
            ).fetchone():
                return None
            db.execute(
                "INSERT OR IGNORE INTO notice_receipts VALUES (?, ?, ?, ?, ?)",
                (secrets.token_hex(16), *scope),
            )
            return db.execute(
                (
                    "SELECT id FROM notice_receipts WHERE (campaign, sender, kind, record)=(?, "
                    "?, ?, ?)"
                ),
                scope,
            ).fetchone()[0]

    def read_receipt(self, campaign, sender, identity):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                """SELECT n.recipient, n.created, n.next_attempt, n.finished, n.outcome
                   FROM notice_receipts r JOIN notices n
                   ON (n.campaign, n.kind, n.record)=(r.campaign, r.kind, r.record)
                   WHERE (r.id, r.campaign, r.sender)=(?, ?, ?)
                   ORDER BY n.recipient""",
                (identity, str(campaign), str(sender)),
            ).fetchall()
        now = time()
        return [
            (
                recipient,
                outcome
                or (
                    "unconfirmed"
                    if finished or (created < now - DELIVERY_WINDOW and next_attempt <= now)
                    else "queued"
                ),
            )
            for recipient, created, next_attempt, finished, outcome in rows
        ]

    def recent_receipts(self, campaign, sender):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                """SELECT id FROM notice_receipts WHERE (campaign, sender)=(?, ?)
                   ORDER BY rowid DESC LIMIT 3""",
                (str(campaign), str(sender)),
            ).fetchall()
        return [identity for (identity,) in reversed(rows)]

    def bond(self, setup, sender, receipt):
        record = setup.bonds.get(sender, receipt["id"])
        if record["state"] == "pending" and not record["stale"]:
            self.file(setup.store.campaign_id, "bond", record["id"], [record["target_id"]])

    def scene_invite(self, setup, sender, receipt):
        self.file(setup.store.campaign_id, "scene_invite", receipt["id"], [receipt["recipient"]])

    def mission(self, service, handler, receipt):
        record = service.get(handler, receipt["id"])["mission"]
        if record["phase"] == "offered":
            self.file(
                service.store.campaign_id,
                "mission",
                record["id"],
                (uid for uid in record["offered_to"] if str(uid) not in record["responses"]),
            )


def pending_interactions(setup, missions, battlefield, viewer):
    """Build notice keys from owner-scoped HarpyEngine views."""

    def read(operation):
        try:
            return operation()
        except WorkflowError:
            return None

    items = set()
    own = read(lambda: setup.game.choices(viewer))
    if own is None:
        return items

    def add(kind, identity):
        items.add((kind, str(identity)))

    for row in own:
        add("play", f"{row['id']}:{row['revision']}")
    work = set()
    for row in read(lambda: missions.owned_work(viewer)) or ():
        if row["owner_id"] == str(viewer.user_id) and row["state"] == "pending":
            work.add(row["id"])
            add("play_work", f"{row['id']}:{row['revision']}")
    for row in read(lambda: missions.list(viewer)) or ():
        if row["needs_response"]:
            add("mission", row["id"])
    if viewer == setup.handler:
        from mission_desk import MissionDesk

        from girlframe.services.m3_careers import CareerService

        career = CareerService(setup.store)
        for request in read(lambda: career.status_requests(viewer)) or ():
            if request["position"] is None:
                add("enrollment", f"status:{request['character']}")
        desk = MissionDesk(missions)
        for row in (read(lambda: desk.view(viewer, "Handler", lifecycle=True)) or {}).get(
            "offers", ()
        ):
            for action in ("dispatch", "advance"):
                if action in row.get("actions", ()):
                    add("mission_review", f"{row['id']}:{action}")
    else:
        for row in read(lambda: setup.bonds.list(viewer)) or ():
            if (
                row["target_id"] == str(viewer.user_id)
                and row["state"] == "pending"
                and not row["stale"]
            ):
                add("bond", row["id"])

    choices = read(lambda: setup.enrollment_choices.view(viewer, ())) or {}
    for row in choices.get("requests", ()):
        if row["incoming"] and row["state"] == "pending":
            add("enrollment", row["id"])

    # Some specialist follow-ups live outside the shared required-work ledger.
    for view in (
        setup.owned_followups.view,
        setup.handler_punishments.view,
        setup.beneath_work.view,
    ):
        for card in read(lambda view=view: view(viewer)) or ():
            if card.get("action") and card["id"] not in work:
                add("play_work", f"{card['id']}:{card['action']}:{card.get('work_revision', '')}")

    period = read(lambda: setup.off_duty.view(viewer)) or {}
    if period:
        for invitation in period.get("invitations", ()):
            if not invitation["confirmed"]:
                add("off_duty", f"{period['period']}:scene:{invitation['owner']}")
        if not period.get("reason"):
            for step in ("scene", "recovery"):
                if period.get(step):
                    add("off_duty", f"{period['period']}:{step}")
        closing = period.get("closing") or {}
        for card in (closing.get("strain") or {}).get("cards", ()):
            if card.get("action"):
                add("off_duty", f"{card['id']}:{card['action']}")
        if closing.get("attendance") and not closing["attendance"]["confirmed"]:
            add("off_duty", f"{period['period']}:handler-scene")
        if closing.get("handler") and closing.get("status_ready"):
            step = "finish" if closing.get("finish") else "status"
            add("off_duty", f"{period['period']}:{step}")

    # Battlefield's view already checks the active actor, lock and Handler ownership.
    arena = read(lambda: battlefield.view(viewer)) if battlefield else None
    if arena:
        encounter = arena["encounter"]
        if encounter["can_end_turn"]:
            add("battlefield", encounter["turn"])
        for review in (*encounter.get("reviews", ()), *encounter.get("attack_reviews", ())):
            add("battlefield", review["id"])
    return items


async def scan_notices(bot, scan):
    await bot.wait_until_ready()
    while True:
        try:
            await asyncio.to_thread(scan)
        except (OSError, sqlite3.Error, SQLAlchemyError, RuntimeError) as error:
            logger.warning(
                "Activity assignment notifications could not be scanned (%s).", type(error).__name__
            )
        await asyncio.sleep(5)


async def send_notice(bot, registry, item, pending):
    campaign, kind, _, recipient = item
    bindings = await asyncio.to_thread(registry.bindings, str(bot.activity_id), str(bot.target.id))
    binding = next((row for row in bindings if UUID(row.id) == UUID(campaign)), None)
    if binding is None:
        return "unavailable"
    try:
        guild = bot.get_guild(bot.target.id)
        if guild is None:
            guild = await bot.fetch_guild(bot.target.id)
        member = await guild.fetch_member(int(recipient))
        if member.bot or member.pending or member.get_role(int(binding.role_id)) is None:
            return "unavailable"
        if not await asyncio.to_thread(pending, binding, item):
            return "skipped"
        nonce = sha256(":".join(item).encode()).hexdigest()[:25]
        destination = DESTINATIONS.get(kind, "Open HarpyEngine and check your Inbox.")
        await member.send(
            f"{NOTICES[kind]} {destination}",
            allowed_mentions=discord.AllowedMentions.none(),
            nonce=nonce,
        )
        return "sent"
    except (discord.Forbidden, discord.NotFound):
        # A former member or closed DMs should not cause repeated alerts.
        return "unavailable"


async def deliver_one(bot, registry, notices, pending, item):
    outcome = await asyncio.wait_for(send_notice(bot, registry, item, pending), timeout=20)
    await asyncio.to_thread(notices.finish, item, outcome)


async def deliver_notices(bot, registry, notices, pending):
    await bot.wait_until_ready()
    while True:
        try:
            item = await asyncio.to_thread(notices.claim)
            if item is None:
                await asyncio.sleep(2)
                continue
            await deliver_one(bot, registry, notices, pending, item)
        except (
            discord.DiscordException,
            OSError,
            sqlite3.Error,
            SQLAlchemyError,
            TimeoutError,
            RuntimeError,
        ) as error:
            logger.warning(
                "An Activity Inbox DM could not be delivered (%s).", type(error).__name__
            )
            await asyncio.sleep(2)
