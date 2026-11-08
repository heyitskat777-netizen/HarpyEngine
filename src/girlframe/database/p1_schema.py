"""Standalone facilitator notices have no fabricated gameplay action or roll foreign key."""

import sqlalchemy as sa


def define(metadata: sa.MetaData) -> sa.Table:
    return sa.Table(
        "p1_facilitator_outbox",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("request_id", sa.Text, nullable=False),
        sa.Column("request_revision", sa.Integer, nullable=False),
        sa.Column("channel_id", sa.Text, nullable=False),
        sa.Column("recipient_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False),
        sa.Column("nonce", sa.Text, nullable=False, unique=True),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_until", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claim_token", sa.Text),
        sa.Column("message_id", sa.Text),
        sa.Column("snapshot_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("last_error", sa.Text, nullable=False, server_default=""),
    )
