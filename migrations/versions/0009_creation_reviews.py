"""Immutable private assembled creation-review sheets; no playable activation."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creation_review_revisions",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("dependency_hash", sa.Text, nullable=False),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False, unique=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["campaign_id", "user_id"], ["characters.campaign_id", "characters.user_id"]
        ),
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_creation_review_{action.lower()} BEFORE {action} "
                "ON creation_review_revisions BEGIN "
                "SELECT RAISE(ABORT, 'append-only creation review'); END"
            )
        )


def downgrade() -> None:
    op.drop_table("creation_review_revisions")
