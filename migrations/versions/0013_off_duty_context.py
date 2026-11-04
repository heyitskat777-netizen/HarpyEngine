"""Persist Off-Duty periods and work context without rewriting mission history."""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def immutable(name: str) -> None:
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_{name}_{action.lower()} BEFORE {action} "
                f"ON {name} BEGIN SELECT RAISE(ABORT, 'append-only M3 record'); END"
            )
        )


def upgrade() -> None:
    op.create_table(
        "m3_off_duty",
        sa.Column("campaign_id", sa.Text, sa.ForeignKey("campaigns.id"), primary_key=True),
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
    op.create_table(
        "m3_off_duty_history",
        sa.Column("campaign_id", sa.Text, sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.Text, sa.ForeignKey("events.id"), nullable=False, unique=True),
    )
    with op.batch_alter_table("m3_required_work", recreate="always") as batch:
        batch.alter_column("mission_id", existing_type=sa.Text, nullable=True)
        batch.add_column(sa.Column("off_duty_id", sa.Text))
        batch.create_foreign_key(
            "fk_work_off_duty",
            "m3_off_duty",
            ["campaign_id", "off_duty_id"],
            ["campaign_id", "id"],
        )
        batch.create_check_constraint(
            "ck_work_one_context",
            "(mission_id IS NOT NULL AND off_duty_id IS NULL) OR "
            "(mission_id IS NULL AND off_duty_id IS NOT NULL)",
        )
    immutable("m3_required_work")
    immutable("m3_off_duty_history")


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM m3_off_duty")):
        raise RuntimeError(
            "Refuse to discard saved Off-Duty periods; restore matching code instead"
        )
    with op.batch_alter_table("m3_required_work", recreate="always") as batch:
        batch.drop_constraint("ck_work_one_context", type_="check")
        batch.drop_constraint("fk_work_off_duty", type_="foreignkey")
        batch.drop_column("off_duty_id")
        batch.alter_column("mission_id", existing_type=sa.Text, nullable=False)
    immutable("m3_required_work")
    op.drop_table("m3_off_duty_history")
    op.drop_table("m3_off_duty")
