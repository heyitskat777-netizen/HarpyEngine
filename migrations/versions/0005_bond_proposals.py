"""Immutable private starting-Bond proposal revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creation_bond_revisions",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("target_id", sa.Text, nullable=False),
        sa.Column("source_revision", sa.Integer, nullable=False),
        sa.Column("target_revision", sa.Integer, nullable=False),
        sa.Column("girl_playbook", sa.Text, nullable=False),
        sa.Column("prompt", sa.Integer, nullable=False),
        sa.Column("context", sa.Text, nullable=False),
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
                f"CREATE TRIGGER immutable_bond_{action.lower()} BEFORE {action} "
                "ON creation_bond_revisions BEGIN "
                "SELECT RAISE(ABORT, 'append-only Bond history'); END"
            )
        )


def downgrade() -> None:
    op.drop_table("creation_bond_revisions")
