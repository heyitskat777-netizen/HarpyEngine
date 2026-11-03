"""Application metadata. New changes require versioned Alembic migrations."""

import sqlalchemy as sa

from girlframe.database.base import Base

metadata = Base.metadata
campaigns = sa.Table(
    "campaigns",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("guild_id", sa.Text, nullable=False, unique=True),
    sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
)
members = sa.Table(
    "campaign_members",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("role", sa.Text, nullable=False),
)
characters = sa.Table(
    "characters",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("id", sa.Text, nullable=False, unique=True),
    sa.Column("revision", sa.Integer, nullable=False),
    sa.Column("public_json", sa.Text, nullable=False),
    sa.Column("private_json", sa.Text, nullable=False),
    sa.ForeignKeyConstraint(
        ["campaign_id", "user_id"], ["campaign_members.campaign_id", "campaign_members.user_id"]
    ),
)
commands = sa.Table(
    "commands_inbox",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("interaction_key", sa.Text, primary_key=True),
    sa.Column("request_hash", sa.Text, nullable=False),
    sa.Column("outcome_json", sa.Text, nullable=False),
)
events = sa.Table(
    "events",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("seq", sa.Integer, primary_key=True),
    sa.Column("command_key", sa.Text, nullable=False),
    sa.Column("event_index", sa.Integer, nullable=False, server_default="0"),
    sa.Column("actor_id", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("payload_json", sa.Text, nullable=False),
    sa.Column("id", sa.Text, nullable=False, unique=True),
    sa.Column("created_utc", sa.Text, nullable=False),
    sa.UniqueConstraint("campaign_id", "command_key", "event_index"),
)
plans = sa.Table(
    "setup_plans",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), nullable=False),
    sa.Column("actor_id", sa.Text, nullable=False),
    sa.Column("expires", sa.Integer, nullable=False),
    sa.Column("template_version", sa.Integer, nullable=False),
)
resources = sa.Table(
    "setup_resources",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("discord_id", sa.Text),
    sa.Column("state", sa.Text, nullable=False),
    sa.UniqueConstraint("campaign_id", "discord_id"),
)
