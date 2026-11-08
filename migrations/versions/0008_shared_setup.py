"""Immutable private Court and Mentor-callsign setup requests."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_setup_revisions",
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
        sa.Column("event_id", sa.Text, nullable=False, unique=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["campaign_id", "source_id"], ["characters.campaign_id", "characters.user_id"]
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "target_id"], ["characters.campaign_id", "characters.user_id"]
        ),
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_shared_setup_{action.lower()} BEFORE {action} "
                "ON shared_setup_revisions BEGIN "
                "SELECT RAISE(ABORT, 'append-only shared setup'); END"
            )
        )


def downgrade() -> None:
    op.drop_table("shared_setup_revisions")
