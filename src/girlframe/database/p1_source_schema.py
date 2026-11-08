"""Durable permission acknowledgment for genuine diceless source workflows."""

import sqlalchemy as sa


def define(metadata: sa.MetaData) -> sa.Table:
    return sa.Table(
        "p1_source_pauses",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("channel_id", sa.Text, nullable=False),
        sa.Column("scene_id", sa.Text, nullable=False),
        sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("snapshot_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("lease_until", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claim_token", sa.Text),
        sa.Column("last_error", sa.Text, nullable=False, server_default=""),
    )
