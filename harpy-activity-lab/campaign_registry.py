"""Bot-owned routing metadata. Character sheets and game state remain in HarpyEngine."""

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import NAMESPACE_URL, uuid5

SNOWFLAKE = re.compile(r"[1-9][0-9]{16,19}")
DEFAULT_CAMPAIGN = "default"
RUNTIME = Path(__file__).resolve().parent.parent / ".sites-runtime" / "harpyengine-mission-lab"


class CampaignBindingError(ValueError):
    pass


@dataclass(frozen=True)
class CampaignBinding:
    id: str
    application_id: str
    guild_id: str
    role_id: str
    handler_id: str
    name: str
    channel_id: str | None = None


COLUMNS = "id, application_id, guild_id, role_id, handler_id, name"


class CampaignRegistry:
    def __init__(self, path):
        self.path = Path(path)

    def owns_bot_managed_campaign(self, campaign_id, application_id, guild_id, owner_id):
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            return (
                db.execute(
                    """SELECT 1 FROM bindings
                   WHERE id=? AND application_id=? AND guild_id=? AND owner_id=?
                     AND handler_id=application_id""",
                    (campaign_id, application_id, guild_id, owner_id),
                ).fetchone()
                is not None
            )

    def bindings(self, application_id, guild_id):
        if not self.path.is_file():
            return []
        # Open read-only. Activity sessions never create or edit role bindings.
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name='bindings'"
            ).fetchone():
                return []
            columns = {row[1] for row in db.execute("PRAGMA table_info(bindings)")}
            channel = "channel_id" if "channel_id" in columns else "NULL"
            active = " AND replaced_by IS NULL" if "replaced_by" in columns else ""
            rows = db.execute(
                f"SELECT {COLUMNS}, {channel} FROM bindings "
                f"WHERE application_id=? AND guild_id=?{active} ORDER BY name_key",
                (application_id, guild_id),
            ).fetchall()
        return [CampaignBinding(*row) for row in rows]

    def latest(self, origin):
        """Follow only successors filed by the same-campaign reset transaction."""
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if "replaced_by" not in {row[1] for row in db.execute("PRAGMA table_info(bindings)")}:
                return origin
            row = db.execute(
                """WITH RECURSIVE chain(id) AS (
                       VALUES (?) UNION SELECT b.replaced_by FROM bindings b JOIN chain c
                         ON b.id=c.id
                       WHERE b.replaced_by IS NOT NULL
                   )
                   SELECT b.id FROM bindings b JOIN chain c ON b.id=c.id WHERE
                     b.replaced_by IS NULL""",
                (origin,),
            ).fetchone()
            return row[0] if row else None

    def replace_campaign(
        self,
        campaign_id,
        *,
        application_id,
        guild_id,
        owner_id,
        confirmation,
        name,
        key,
        checkpoint,
        provision,
    ):
        name = name.strip() if isinstance(name, str) else ""
        if not 1 <= len(name) <= 80 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise CampaignBindingError("Enter a campaign name of 1–80 characters on one line.")
        # Keep the established UUID derivation so archived replacements can be imported.
        action = uuid5(NAMESPACE_URL, f"harpyengine:reset:{application_id}:{campaign_id}:{key}")
        interaction_id = str(10**17 + action.int % (9 * 10**18))
        identity = uuid5(
            NAMESPACE_URL, f"harpyengine:activity:{application_id}:{interaction_id}"
        ).hex
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(bindings)")}
            if "replaced_by" not in columns:
                db.execute("ALTER TABLE bindings ADD COLUMN replaced_by TEXT")
                db.execute("ALTER TABLE bindings ADD COLUMN archived_at INTEGER")
            row = db.execute(
                """SELECT role_id, handler_id, name, channel_id, replaced_by FROM bindings
                   WHERE id=? AND application_id=? AND guild_id=? AND owner_id=?
                     AND handler_id=application_id""",
                (campaign_id, application_id, guild_id, owner_id),
            ).fetchone()
            if row is None or row[4] is not None:
                raise CampaignBindingError("This campaign is no longer available to reset.")
            role, handler, original, channel, _ = row
            if original != confirmation or original.casefold() == name.casefold():
                raise CampaignBindingError(
                    "Enter the exact current campaign name and choose a new name."
                )
            if db.execute(
                (
                    "SELECT 1 FROM bindings WHERE application_id=? AND (id=? OR "
                    "interaction_id=? OR (guild_id=? AND name_key=?))"
                ),
                (application_id, identity, interaction_id, guild_id, name.casefold()),
            ).fetchone():
                raise CampaignBindingError("A campaign with that name already exists.")
            next_campaign = CampaignBinding(
                identity, application_id, guild_id, role, handler, name, channel
            )
            checkpoint()
            provision(next_campaign)
            db.execute(
                """UPDATE bindings SET replaced_by=?, archived_at=?, channel_id=NULL, name_key=?
                   WHERE id=?""",
                (identity, int(time()), "archive:" + campaign_id, campaign_id),
            )
            db.execute(
                """INSERT INTO bindings
                   (id,application_id,guild_id,role_id,handler_id,name,channel_id,name_key,owner_id,interaction_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    identity,
                    application_id,
                    guild_id,
                    role,
                    handler,
                    name,
                    channel,
                    name.casefold(),
                    owner_id,
                    interaction_id,
                ),
            )
        return next_campaign

    def register(
        self,
        *,
        application_id,
        guild_id,
        owner_id,
        actor_id,
        role_id,
        role_guild_id,
        handler_id,
        interaction_id,
        name,
        channel_id=None,
        channel_guild_id=None,
        provision=None,
    ):
        # The bot supplies these values from a verified guild interaction.
        if actor_id != owner_id:
            raise CampaignBindingError("Only the Discord server owner can create a campaign.")
        if any(
            not isinstance(value, str) or not SNOWFLAKE.fullmatch(value)
            for value in (
                application_id,
                guild_id,
                owner_id,
                role_id,
                handler_id,
                interaction_id,
            )
        ):
            raise CampaignBindingError("Choose a server role and Handler from this Discord server.")
        if role_guild_id != guild_id or role_id == guild_id:
            raise CampaignBindingError("Choose a role from this server other than @everyone.")
        if channel_id is not None and (
            not isinstance(channel_id, str)
            or not SNOWFLAKE.fullmatch(channel_id)
            or channel_guild_id != guild_id
        ):
            raise CampaignBindingError("Choose a channel in this Discord server.")
        name = name.strip() if isinstance(name, str) else ""
        if not 1 <= len(name) <= 80 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise CampaignBindingError("Enter a campaign name of 1–80 characters on one line.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        parameters = (application_id, guild_id, role_id, handler_id, name, channel_id)
        with closing(sqlite3.connect(self.path, timeout=100)) as db, db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS bindings (
                    id TEXT PRIMARY KEY, application_id TEXT NOT NULL, guild_id TEXT NOT NULL,
                    role_id TEXT NOT NULL, handler_id TEXT NOT NULL, name TEXT NOT NULL,
                      channel_id TEXT,
                    name_key TEXT NOT NULL, owner_id TEXT NOT NULL, interaction_id TEXT NOT NULL,
                    UNIQUE(application_id, guild_id, name_key),
                    UNIQUE(application_id, interaction_id)
                )"""
            )
            db.execute("BEGIN IMMEDIATE")
            if not any(row[1] == "channel_id" for row in db.execute("PRAGMA table_info(bindings)")):
                db.execute("ALTER TABLE bindings ADD COLUMN channel_id TEXT")
            db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS bound_campaign_channel
                   ON bindings (application_id, guild_id, channel_id) WHERE channel_id IS
                     NOT NULL"""
            )
            previous = db.execute(
                f"SELECT {COLUMNS}, channel_id, owner_id FROM bindings "
                "WHERE application_id=? AND interaction_id=?",
                (application_id, interaction_id),
            ).fetchone()
            if previous:
                if previous[1:] != (*parameters, owner_id):
                    raise CampaignBindingError(
                        "This Discord interaction already has a different binding."
                    )
                return CampaignBinding(*previous[:-1])
            identity = uuid5(
                NAMESPACE_URL, f"harpyengine:activity:{application_id}:{interaction_id}"
            ).hex
            try:
                db.execute(
                    """INSERT INTO bindings (id,application_id,guild_id,role_id,handler_id,
                              name,channel_id,name_key,owner_id,interaction_id)
                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (identity, *parameters, name.casefold(), owner_id, interaction_id),
                )
            except sqlite3.IntegrityError:
                raise CampaignBindingError(
                    "A campaign with that name or channel already exists on this server."
                ) from None
            binding = CampaignBinding(identity, *parameters)
            if provision:
                provision(binding)
        return binding
