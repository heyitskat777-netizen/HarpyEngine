"""Mission authority and immutable private mission/work histories."""

import sqlalchemy as sa


def define(metadata: sa.MetaData) -> dict[str, sa.Table]:
    missions = sa.Table(
        "m3_missions",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("handler_id", sa.Text, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("phase", sa.Text, nullable=False),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id", "handler_id"],
            ["campaign_members.campaign_id", "campaign_members.user_id"],
        ),
    )
    history = sa.Table(
        "m3_mission_history",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
    )
    work = sa.Table(
        "m3_required_work",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("mission_id", sa.Text, nullable=False),
        sa.Column("owner_id", sa.Text, nullable=False),
        sa.Column("subject_id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id", "mission_id"], ["m3_missions.campaign_id", "m3_missions.id"]
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "owner_id"],
            ["campaign_members.campaign_id", "campaign_members.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "subject_id"],
            ["campaign_members.campaign_id", "campaign_members.user_id"],
        ),
    )
    return {table.name: table for table in (missions, history, work)}
