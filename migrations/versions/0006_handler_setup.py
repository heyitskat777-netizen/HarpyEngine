"""Private immutable Handler setup and Mentor proposal provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_setup_revisions",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.Text, nullable=False, unique=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
    )
    op.add_column("creation_bond_revisions", sa.Column("mentor_assignment_id", sa.Text))
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_setup_{action.lower()} BEFORE {action} "
                "ON campaign_setup_revisions BEGIN "
                "SELECT RAISE(ABORT, 'append-only setup history'); END"
            )
        )


def downgrade() -> None:
    op.drop_column("creation_bond_revisions", "mentor_assignment_id")
    op.drop_table("campaign_setup_revisions")
