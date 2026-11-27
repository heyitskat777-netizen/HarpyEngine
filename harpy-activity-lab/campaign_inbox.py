"""Best-effort Discord reminders for pending, recipient-owned Inbox items."""

import asyncio
import logging
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from time import time
from uuid import UUID

import discord
from sqlalchemy.exc import SQLAlchemyError

from girlframe.services.onboarding import WorkflowError

logger = logging.getLogger("harpy_activity.discord")
DELIVERY_WINDOW = 120
CLEANUP_INTERVAL = 30
NOTICES = {
    "bond": "A pilot filed a starting Bond proposal for your response.",
    "mission": "The Handler filed a mission offer for your response.",
    "mission_review": "A mission is ready for your Handler review.",
    "scene_invite": "A scene host invited you to join a scene.",
    "communication": "A new private transmission is available.",
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
    "communication": "Open Comms in HarpyEngine to read it.",
}


@dataclass(frozen=True)
class SentDM:
    channel: str
    message: str


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
            columns = {column[1] for column in db.execute("PRAGMA table_info(notices)")}
            for column in ("outcome", "dm_channel", "dm_message", "cleanup_outcome"):
                if column not in columns:
                    db.execute(f"ALTER TABLE notices ADD COLUMN {column} TEXT")
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
                """INSERT OR IGNORE INTO notices
                   (campaign, kind, record, recipient, created, next_attempt, finished, outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
                """INSERT OR IGNORE INTO notices
                   (campaign, kind, record, recipient, created, next_attempt)
                   VALUES (?, ?, ?, ?, ?, ?)""",
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

    def finish(self, item, outcome, dm=None):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """UPDATE notices SET finished=1, outcome=?, dm_channel=?, dm_message=?,
                       next_attempt=?
                   WHERE (campaign, kind, record, recipient)=(?, ?, ?, ?) AND finished=0""",
                (outcome, dm.channel if dm else None, dm.message if dm else None, time(), *item),
            )

    def claim_cleanup(self):
        stamp = time()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """SELECT campaign, kind, record, recipient, dm_channel, dm_message
                   FROM notices
                   WHERE outcome='sent' AND dm_message IS NOT NULL AND dm_channel IS NOT NULL
                       AND kind <> 'communication'
                       AND cleanup_outcome IS NULL AND next_attempt<=?
                   ORDER BY next_attempt, created LIMIT 1""",
                (stamp,),
            ).fetchone()
            if row is None:
                return None
            *item, channel, message = row
            db.execute(
                """UPDATE notices SET next_attempt=?
                   WHERE (campaign, kind, record, recipient)=(?, ?, ?, ?)""",
                (stamp + CLEANUP_INTERVAL, *item),
            )
            return tuple(item), SentDM(channel, message)

    def finish_cleanup(self, item, dm, outcome):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """UPDATE notices SET cleanup_outcome=?
                   WHERE (campaign, kind, record, recipient, dm_channel, dm_message)
                       =(?, ?, ?, ?, ?, ?)""",
                (outcome, *item, dm.channel, dm.message),
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
                """SELECT id, kind, record FROM notice_receipts WHERE (campaign, sender)=(?, ?)
                   ORDER BY rowid DESC LIMIT 3""",
                (str(campaign), str(sender)),
            ).fetchall()
        return list(reversed(rows))

    def bond(self, setup, sender, receipt):
        record = setup.bonds.get(sender, receipt["id"])
        if record["state"] == "pending" and not record["stale"]:
            self.file(setup.store.campaign_id, "bond", record["id"], [record["target_id"]])

    def scene_invite(self, setup, sender, receipt):
        self.file(setup.store.campaign_id, "scene_invite", receipt["id"], [receipt["recipient"]])

    def communication(self, setup, sender, receipt):
        self.file(setup.store.campaign_id, "communication", receipt["id"], [receipt["recipient"]])

    def mission(self, service, handler, receipt):
        record = service.get(handler, receipt["id"])["mission"]
        if record["phase"] == "offered":
            self.file(
                service.store.campaign_id,
                "mission",
                record["id"],
                (uid for uid in record["offered_to"] if str(uid) not in record["responses"]),
            )


def pending_interactions(setup, missions, battlefield, viewer, *, lookup=None):
    """Project owned work. A lookup also retains assignments temporarily blocked by other work."""

    problem = None

    def read(operation):
        nonlocal problem
        try:
            return operation()
        except WorkflowError as error:
            problem = error
            return None

    def wants(kind):
        return lookup is None or lookup[0] == kind

    items = set()

    def add(kind, identity):
        items.add((kind, str(identity)))

    def retain(kind, prefix):
        if lookup and lookup[0] == kind and lookup[1].startswith(prefix):
            items.add(lookup)

    if wants("play"):
        own = read(lambda: setup.game.choices(viewer))
        if own is None and lookup is None:
            return items
        for row in own or ():
            add("play", f"{row['id']}:{row['revision']}")

    if wants("scene_invite") and lookup is not None:
        for card in setup.records.scene_invites(viewer):
            add("scene_invite", card["id"])

    if lookup and wants("communication") and setup.can_notify_communication(
        viewer, lookup[1], since=int(time()) - DELIVERY_WINDOW
    ):
        add("communication", lookup[1])

    if wants("bond"):
        if lookup is None:
            bonds = read(lambda: setup.bonds.list(viewer)) or ()
        else:
            # A pending Bond outside the recent Inbox page is still pending.
            bonds = (setup.bonds.get(viewer, lookup[1]),)
        for row in bonds:
            if (
                row["target_id"] == str(viewer.user_id)
                and row["state"] == "pending"
                and not row["stale"]
            ):
                add("bond", row["id"])

    if wants("mission"):
        for row in read(lambda: missions.list(viewer)) or ():
            if row["needs_response"]:
                add("mission", row["id"])

    if wants("mission_review") and viewer == setup.handler:
        from mission_desk import MissionDesk

        desk = MissionDesk(missions)
        for row in (read(lambda: desk.view(viewer, "Handler", lifecycle=True)) or {}).get(
            "offers", ()
        ):
            for action in ("dispatch", "advance"):
                if action in row.get("actions", ()):
                    add("mission_review", f"{row['id']}:{action}")

    if wants("enrollment"):
        if viewer == setup.handler:
            from girlframe.services.m3_careers import CareerService

            career = CareerService(setup.store)
            for request in read(lambda: career.status_requests(viewer)) or ():
                if request["position"] is None:
                    add("enrollment", f"status:{request['character']}")
        choices = read(lambda: setup.enrollment_choices.view(viewer, ())) or {}
        for row in choices.get("requests", ()):
            if row["incoming"] and row["state"] == "pending":
                add("enrollment", row["id"])

    if wants("play_work"):
        work = set()
        for row in read(lambda: missions.owned_work(viewer)) or ():
            if row["owner_id"] == str(viewer.user_id) and row["state"] == "pending":
                work.add(row["id"])
                add("play_work", f"{row['id']}:{row['revision']}")
        # Some specialist follow-ups live outside the shared required-work ledger.
        for view in (
            setup.owned_followups.view,
            setup.handler_punishments.view,
            setup.beneath_work.view,
        ):
            for card in read(lambda view=view: view(viewer)) or ():
                if card.get("action") and card["id"] not in work:
                    add(
                        "play_work",
                        f"{card['id']}:{card['action']}:{card.get('work_revision', '')}",
                    )
                elif card.get("waiting"):
                    retain("play_work", f"{card['id']}:")

    if wants("off_duty"):
        period = read(lambda: setup.off_duty.view(viewer)) or {}
        if period:
            for invitation in period.get("invitations", ()):
                if not invitation["confirmed"]:
                    add("off_duty", f"{period['period']}:scene:{invitation['owner']}")
            for step in ("scene", "recovery"):
                identity = f"{period['period']}:{step}"
                if not period.get("reason") and period.get(step):
                    add("off_duty", identity)
                elif (
                    period.get("reason")
                    and not period.get("recovered")
                    and not (step == "scene" and period.get("declined"))
                    and lookup == ("off_duty", identity)
                ):
                    items.add(lookup)
            closing = period.get("closing") or {}
            for card in (closing.get("strain") or {}).get("cards", ()):
                if card.get("action"):
                    add("off_duty", f"{card['id']}:{card['action']}")
            if closing.get("attendance") and not closing["attendance"]["confirmed"]:
                add("off_duty", f"{period['period']}:handler-scene")
            if closing.get("handler") and closing.get("status_ready"):
                step = "finish" if closing.get("finish") else "status"
                add("off_duty", f"{period['period']}:{step}")
        elif lookup:
            # The view can hide a failed authorization. Let the source report it on lookup.
            read(lambda: setup.off_duty.periods.current(viewer))

    if wants("battlefield") and battlefield:
        arena = read(lambda: battlefield.view(viewer))
        if arena:
            encounter = arena["encounter"]
            if encounter["can_end_turn"] or (lookup and encounter.get("yours")):
                add("battlefield", encounter["turn"])
            for review in (*encounter.get("reviews", ()), *encounter.get("attack_reviews", ())):
                add("battlefield", review["id"])
            if lookup and arena.get("busy") and encounter["handler"]:
                for review in read(lambda: battlefield.combat.tasks(viewer)) or ():
                    if review["incoming"]:
                        add("battlefield", review["id"])
    if lookup is not None and lookup not in items and problem is not None:
        raise problem
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


async def notice_binding(bot, registry, campaign):
    bindings = await asyncio.to_thread(registry.bindings, str(bot.activity_id), str(bot.target.id))
    return next((row for row in bindings if UUID(row.id) == UUID(campaign)), None)


async def send_notice(bot, registry, item, pending):
    campaign, kind, _, recipient = item
    binding = await notice_binding(bot, registry, campaign)
    if binding is None:
        return "unavailable"
    try:
        guild = bot.get_guild(bot.target.id)
        if guild is None:
            guild = await bot.fetch_guild(bot.target.id)
        member = await guild.fetch_member(int(recipient))
        if member.bot or member.pending or member.get_role(int(binding.role_id)) is None:
            return "unavailable"
        still_pending = await asyncio.to_thread(pending, binding, item)
        if still_pending is None:
            return None
        if not still_pending:
            return "skipped"
        nonce = sha256(":".join(item).encode()).hexdigest()[:25]
        destination = DESTINATIONS.get(kind, "Open HarpyEngine and check your Inbox.")
        message = await member.send(
            f"{NOTICES[kind]} {destination}",
            allowed_mentions=discord.AllowedMentions.none(),
            nonce=nonce,
        )
        return SentDM(str(message.channel.id), str(message.id))
    except (discord.Forbidden, discord.NotFound):
        # A former member or closed DMs should not cause repeated alerts.
        return "unavailable"


async def deliver_one(bot, registry, notices, pending, item):
    outcome = await asyncio.wait_for(send_notice(bot, registry, item, pending), timeout=20)
    if isinstance(outcome, SentDM):
        await asyncio.to_thread(notices.finish, item, "sent", outcome)
    elif outcome is not None:
        await asyncio.to_thread(notices.finish, item, outcome)


async def retire_one(bot, registry, notices, pending, item, dm):
    binding = await notice_binding(bot, registry, item[0])
    if binding is None or await asyncio.to_thread(pending, binding, item) is not False:
        return
    try:
        channel = bot.get_partial_messageable(int(dm.channel), type=discord.ChannelType.private)
        await asyncio.wait_for(channel.get_partial_message(int(dm.message)).delete(), timeout=20)
    except discord.NotFound:
        pass  # The exact reminder was already deleted.
    except discord.Forbidden:
        await asyncio.to_thread(notices.finish_cleanup, item, dm, "unavailable")
        return
    await asyncio.to_thread(notices.finish_cleanup, item, dm, "removed")


async def deliver_notices(bot, registry, notices, pending):
    await bot.wait_until_ready()
    while True:
        try:
            item = await asyncio.to_thread(notices.claim)
            if item is not None:
                await deliver_one(bot, registry, notices, pending, item)
            cleanup = await asyncio.to_thread(notices.claim_cleanup)
            if cleanup is not None:
                await retire_one(bot, registry, notices, pending, *cleanup)
            if item is None:
                await asyncio.sleep(2)
        except (
            discord.DiscordException,
            OSError,
            sqlite3.Error,
            SQLAlchemyError,
            TimeoutError,
            RuntimeError,
        ) as error:
            logger.warning(
                "An Activity Inbox DM could not be delivered or cleared (%s).", type(error).__name__
            )
            await asyncio.sleep(2)
