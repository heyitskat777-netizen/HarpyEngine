"""Private, versioned creation drafts; no playable-character activation."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creation_drafts",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("character_revision", sa.Integer, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False, unique=True),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["campaign_id", "user_id"], ["characters.campaign_id", "characters.user_id"]
        ),
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_creation_{action.lower()} "
                f"BEFORE {action} ON creation_drafts BEGIN "
                "SELECT RAISE(ABORT, 'append-only creation history'); END"
            )
        )


def downgrade() -> None:
    op.drop_table("creation_drafts")
