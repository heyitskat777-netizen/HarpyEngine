"""Add M3 mission authority and immutable work histories; preserve existing records."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


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


def upgrade() -> None:
    metadata = sa.MetaData()
    for name, columns in (
        ("campaigns", ("id",)),
        ("events", ("id",)),
        ("campaign_members", ("campaign_id", "user_id")),
    ):
        sa.Table(name, metadata, *(sa.Column(x, sa.Text, primary_key=True) for x in columns))
    tables = define(metadata)
    for table in metadata.sorted_tables:
        if table.name in tables:
            table.create(op.get_bind())
    for name in ("m3_mission_history", "m3_required_work"):
        for action in ("UPDATE", "DELETE"):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER immutable_{name}_{action.lower()} BEFORE {action} "
                    f"ON {name} BEGIN SELECT RAISE(ABORT, 'append-only M3 record'); END"
                )
            )


def downgrade() -> None:
    for name in ("m3_required_work", "m3_mission_history", "m3_missions"):
        op.drop_table(name)
