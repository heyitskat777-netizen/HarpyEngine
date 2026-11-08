"""Keep actual scene identities and scoped work without inventing recovery periods."""

import json

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

CONTEXT_CHECK = (
    "((mission_id IS NOT NULL) + (off_duty_id IS NOT NULL) + "
    "(scene_id IS NOT NULL) + campaign_context) = 1 AND campaign_context IN (0, 1)"
)


def immutable(name: str) -> None:
    for action in ("UPDATE", "DELETE"):
        op.execute(
            sa.text(
                f"CREATE TRIGGER immutable_{name}_{action.lower()} BEFORE {action} "
                f"ON {name} BEGIN SELECT RAISE(ABORT, 'append-only M3 record'); END"
            )
        )


def upgrade() -> None:
    table = op.create_table(
        "m3_scene_contexts",
        sa.Column("campaign_id", sa.Text, sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("channel_id", sa.Text, nullable=False),
        sa.Column(
            "binding_event", sa.Text, sa.ForeignKey("events.id"), nullable=False, unique=True
        ),
    )
    bind = op.get_bind()
    # Read only actual bind evidence. A missing outcome is not a guessed scene.
    rows = bind.execute(
        sa.text(
            "SELECT e.campaign_id, e.id, e.payload_json, c.outcome_json FROM events e "
            "LEFT JOIN commands_inbox c ON c.campaign_id=e.campaign_id "
            "AND c.interaction_key=e.command_key WHERE e.kind='m2.scene_bound' ORDER BY e.seq"
        )
    ).mappings()
    for row in rows:
        payload = json.loads(row["payload_json"])
        outcome = json.loads(row["outcome_json"]) if row["outcome_json"] else {}
        if (
            payload.get("scene_id")
            and outcome.get("scene")
            and payload["scene_id"] != outcome["scene"]
        ):
            raise RuntimeError("Conflicting actual scene binding evidence; recover source records")
        identity = payload.get("scene_id") or outcome.get("scene")
        channel = payload.get("channel")
        if (
            isinstance(identity, str)
            and identity
            and str(channel).isascii()
            and str(channel).isdecimal()
            and int(channel) > 0
        ):
            bind.execute(
                table.insert().values(
                    campaign_id=row["campaign_id"],
                    id=identity,
                    channel_id=str(channel),
                    binding_event=row["id"],
                )
            )
    with op.batch_alter_table("m3_required_work", recreate="always") as batch:
        batch.drop_constraint("ck_work_one_context", type_="check")
        batch.add_column(sa.Column("scene_id", sa.Text))
        batch.add_column(
            sa.Column("campaign_context", sa.Boolean, nullable=False, server_default=sa.false())
        )
        batch.create_foreign_key(
            "fk_work_scene_context",
            "m3_scene_contexts",
            ["campaign_id", "scene_id"],
            ["campaign_id", "id"],
        )
        batch.create_check_constraint("ck_work_one_context", CONTEXT_CHECK)
    immutable("m3_required_work")
    immutable("m3_scene_contexts")
    op.execute(
        sa.text(
            "CREATE TRIGGER stable_m3_work_context BEFORE INSERT ON m3_required_work "
            "WHEN EXISTS (SELECT 1 FROM m3_required_work old "
            "WHERE old.campaign_id=NEW.campaign_id AND old.id=NEW.id AND "
            "(old.mission_id IS NOT NEW.mission_id OR old.off_duty_id IS NOT NEW.off_duty_id "
            "OR old.scene_id IS NOT NEW.scene_id "
            "OR old.campaign_context IS NOT NEW.campaign_context)) "
            "BEGIN SELECT RAISE(ABORT, 'immutable required-work context'); END"
        )
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM m3_required_work "
            "WHERE scene_id IS NOT NULL OR campaign_context = 1"
        )
    ):
        raise RuntimeError(
            "Refuse to discard actual scene/campaign work; restore matching code instead"
        )
    with op.batch_alter_table("m3_required_work", recreate="always") as batch:
        batch.drop_constraint("ck_work_one_context", type_="check")
        batch.drop_constraint("fk_work_scene_context", type_="foreignkey")
        batch.drop_column("scene_id")
        batch.drop_column("campaign_context")
        batch.create_check_constraint(
            "ck_work_one_context",
            "(mission_id IS NOT NULL AND off_duty_id IS NULL) OR "
            "(mission_id IS NULL AND off_duty_id IS NOT NULL)",
        )
    immutable("m3_required_work")
    op.drop_table("m3_scene_contexts")
