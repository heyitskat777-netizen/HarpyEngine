"""Application metadata. New changes require versioned Alembic migrations."""

import sqlalchemy as sa

from girlframe.database.base import Base

metadata = Base.metadata
coordination_revisions = sa.Table(
    "creation_coordination_revisions",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("author_id", sa.Text, nullable=False),
    sa.Column("owner_id", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("context_json", sa.Text, nullable=False),
    sa.Column("choice_json", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.ForeignKeyConstraint(
        ["campaign_id", "author_id"], ["campaign_members.campaign_id", "campaign_members.user_id"]
    ),
    sa.ForeignKeyConstraint(
        ["campaign_id", "owner_id"], ["characters.campaign_id", "characters.user_id"]
    ),
)
creation_reviews = sa.Table(
    "creation_review_revisions",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("dependency_hash", sa.Text, nullable=False),
    sa.Column("body_json", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.ForeignKeyConstraint(
        ["campaign_id", "user_id"], ["characters.campaign_id", "characters.user_id"]
    ),
)
creation_drafts = sa.Table(
    "creation_drafts",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("character_revision", sa.Integer, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("body_json", sa.Text, nullable=False),
    sa.ForeignKeyConstraint(
        ["campaign_id", "user_id"], ["characters.campaign_id", "characters.user_id"]
    ),
)
bond_revisions = sa.Table(
    "creation_bond_revisions",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("source_id", sa.Text, nullable=False),
    sa.Column("target_id", sa.Text, nullable=False),
    sa.Column("source_revision", sa.Integer, nullable=False),
    sa.Column("target_revision", sa.Integer, nullable=False),
    sa.Column("mentor_assignment_id", sa.Text),
    sa.Column("girl_playbook", sa.Text, nullable=False),
    sa.Column("prompt", sa.Integer, nullable=False),
    sa.Column("context", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.ForeignKeyConstraint(
        ["campaign_id", "source_id"], ["characters.campaign_id", "characters.user_id"]
    ),
    sa.ForeignKeyConstraint(
        ["campaign_id", "target_id"], ["characters.campaign_id", "characters.user_id"]
    ),
)
pair_asset_revisions = sa.Table(
    "pair_asset_revisions",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("bond_id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("bond_revision", sa.Integer, nullable=False),
    sa.Column("names_json", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.ForeignKeyConstraint(
        ["campaign_id", "bond_id", "bond_revision"],
        [
            "creation_bond_revisions.campaign_id",
            "creation_bond_revisions.id",
            "creation_bond_revisions.revision",
        ],
    ),
)
shared_setup_revisions = sa.Table(
    "shared_setup_revisions",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("source_id", sa.Text, nullable=False),
    sa.Column("target_id", sa.Text, nullable=False),
    sa.Column("source_revision", sa.Integer, nullable=False),
    sa.Column("target_revision", sa.Integer, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("choice_json", sa.Text, nullable=False),
    sa.Column("constraint_token", sa.Text),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.ForeignKeyConstraint(
        ["campaign_id", "source_id"], ["characters.campaign_id", "characters.user_id"]
    ),
    sa.ForeignKeyConstraint(
        ["campaign_id", "target_id"], ["characters.campaign_id", "characters.user_id"]
    ),
)
setup_revisions = sa.Table(
    "campaign_setup_revisions",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("body_json", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
)
campaigns = sa.Table(
    "campaigns",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("guild_id", sa.Text, nullable=False, unique=True),
    sa.Column("revision", sa.Integer, nullable=False, server_default="0"),
    sa.Column("name", sa.Text, nullable=False, server_default="Private campaign"),
    sa.Column("initialized", sa.Boolean, nullable=False, server_default="0"),
)
members = sa.Table(
    "campaign_members",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("active", sa.Boolean, nullable=False, server_default="1"),
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
    sa.Column("visibility", sa.Text, nullable=False, server_default="private"),
    sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("ruleset_version", sa.Text, nullable=False, server_default="synthetic-m1"),
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
managed_roles = sa.Table(
    "managed_roles",
    metadata,
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
    sa.Column("key", sa.Text, primary_key=True),
    sa.Column("discord_id", sa.Text),
    sa.Column("state", sa.Text, nullable=False),
    sa.UniqueConstraint("campaign_id", "discord_id"),
)
character_sync = sa.Table(
    "character_discord_sync",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, nullable=False),
    sa.Column("desired_json", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),
    sa.Column("warning", sa.Text, nullable=False, server_default=""),
    sa.ForeignKeyConstraint(
        ["campaign_id", "user_id"], ["characters.campaign_id", "characters.user_id"]
    ),
)
principals = sa.Table(
    "principals",
    metadata,
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("id", sa.Text, nullable=False, unique=True),
    sa.Column("created_utc", sa.Text, nullable=False),
)
snapshots = sa.Table(
    "character_snapshots",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("revision", sa.Integer, primary_key=True),
    sa.Column("character_id", sa.Text, nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id")),
    sa.Column("public_json", sa.Text, nullable=False),
    sa.Column("private_json", sa.Text, nullable=False),
    sa.ForeignKeyConstraint(
        ["campaign_id", "user_id"], ["campaign_members.campaign_id", "campaign_members.user_id"]
    ),
)
rolls = sa.Table(
    "roll_receipts",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    sa.Column("user_id", sa.ForeignKey("principals.user_id"), nullable=False),
    sa.Column("character_id", sa.ForeignKey("characters.id"), nullable=False),
    sa.Column("command_key", sa.Text, nullable=False),
    sa.Column("roll_index", sa.Integer, nullable=False, server_default="0"),
    sa.Column("visibility", sa.Text, nullable=False),
    sa.Column("receipt_json", sa.Text, nullable=False),
    sa.UniqueConstraint("campaign_id", "command_key", "roll_index"),
)
pauses = sa.Table(
    "safety_pauses",
    metadata,
    sa.Column("campaign_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.ForeignKeyConstraint(
        ["campaign_id", "user_id"], ["campaign_members.campaign_id", "campaign_members.user_id"]
    ),
)
outbox = sa.Table(
    "delivery_outbox",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), nullable=False),
    sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False),
    sa.Column("roll_id", sa.ForeignKey("roll_receipts.id"), nullable=False, unique=True),
    sa.Column("channel_id", sa.Text, nullable=False),
    sa.Column("nonce", sa.Text, nullable=False, unique=True),
    sa.Column("state", sa.Text, nullable=False, server_default="pending"),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("claim_token", sa.Text),
    sa.Column("lease_until", sa.Integer, nullable=False, server_default="0"),
    sa.Column("not_before", sa.Integer, nullable=False, server_default="0"),
    sa.Column("message_id", sa.Text),
    sa.Column("last_error", sa.Text, nullable=False, server_default=""),
)
