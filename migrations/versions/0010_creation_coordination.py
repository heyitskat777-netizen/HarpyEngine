"""Immutable private playbook choices from bonded Girls and appointed Handlers."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creation_coordination_revisions",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("author_id", sa.Text, nullable=False),
        sa.Column("owner_id", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("context_json", sa.Text, nullable=False),
        sa.Column("choice_json", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False, unique=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(
            ["campaign_id", "author_id"],
            ["campaign_members.campaign_id", "campaign_members.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "owner_id"], ["characters.campaign_id", "characters.user_id"]
        ),
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_creation_coordination_{action.lower()} BEFORE {action} "
                "ON creation_coordination_revisions BEGIN "
                "SELECT RAISE(ABORT, 'append-only playbook coordination'); END"
            )
        )


def downgrade() -> None:
    op.drop_table("creation_coordination_revisions")
