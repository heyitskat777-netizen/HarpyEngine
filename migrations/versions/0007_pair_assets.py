"""Immutable Pair-authored starting Asset allocations."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pair_asset_revisions",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("bond_id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("bond_revision", sa.Integer, nullable=False),
        sa.Column("names_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False, unique=True),
        sa.ForeignKeyConstraint(
            ["campaign_id", "bond_id", "bond_revision"],
            [
                "creation_bond_revisions.campaign_id",
                "creation_bond_revisions.id",
                "creation_bond_revisions.revision",
            ],
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_pair_assets_{action.lower()} BEFORE {action} "
                "ON pair_asset_revisions BEGIN SELECT RAISE(ABORT, 'append-only Pair Assets'); END"
            )
        )


def downgrade() -> None:
    op.drop_table("pair_asset_revisions")
