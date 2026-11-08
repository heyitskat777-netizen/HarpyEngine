"""Canonical M2 state, actions, choices and scene-lock operational storage."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def define(metadata: sa.MetaData) -> dict[str, sa.Table]:
    result = {}
    for name, columns in (
        (
            "m2_state",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("revision", sa.Integer, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
            ],
        ),
        (
            "m2_state_history",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("revision", sa.Integer, primary_key=True),
                sa.Column("body_json", sa.Text, nullable=False),
                sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
            ],
        ),
        (
            "m2_scenes",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("channel_id", sa.Text, primary_key=True),
                sa.Column("id", sa.Text, nullable=False),
                sa.Column("revision", sa.Integer, nullable=False),
                sa.Column("participants_json", sa.Text, nullable=False),
                sa.Column("open", sa.Boolean, nullable=False),
            ],
        ),
        (
            "m2_actions",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("id", sa.Text, primary_key=True),
                sa.Column("actor_id", sa.Text, nullable=False),
                sa.Column("channel_id", sa.Text, nullable=False),
                sa.Column("scene_id", sa.Text, nullable=False),
                sa.Column("parent_id", sa.Text),
                sa.Column("revision", sa.Integer, nullable=False),
                sa.Column("state", sa.Text, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
            ],
        ),
        (
            "m2_receipts",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("action_id", sa.Text, primary_key=True),
                sa.Column("id", sa.Text, nullable=False, unique=True),
                sa.Column("body_json", sa.Text, nullable=False),
            ],
        ),
        (
            "m2_choices",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("id", sa.Text, primary_key=True),
                sa.Column("action_id", sa.Text, nullable=False),
                sa.Column("actor_id", sa.Text, nullable=False),
                sa.Column("kind", sa.Text, nullable=False),
                sa.Column("revision", sa.Integer, nullable=False),
                sa.Column("state", sa.Text, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
            ],
        ),
        (
            "m2_responses",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("choice_id", sa.Text, primary_key=True),
                sa.Column("actor_id", sa.Text, nullable=False),
                sa.Column("answer_json", sa.Text, nullable=False),
                sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False),
            ],
        ),
        (
            "m2_locks",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("channel_id", sa.Text, primary_key=True),
                sa.Column("action_id", sa.Text, nullable=False),
                sa.Column("state", sa.Text, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
                sa.Column("lease_until", sa.Integer, nullable=False, server_default="0"),
                sa.Column("claim_token", sa.Text),
            ],
        ),
        (
            "m2_outbox",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("id", sa.Text, primary_key=True),
                sa.Column("action_id", sa.Text, nullable=False),
                sa.Column("channel_id", sa.Text, nullable=False),
                sa.Column("nonce", sa.Text, nullable=False, unique=True),
                sa.Column("body_json", sa.Text, nullable=False),
                sa.Column("state", sa.Text, nullable=False),
                sa.Column("message_id", sa.Text),
                sa.Column("lease_until", sa.Integer, nullable=False, server_default="0"),
                sa.Column("claim_token", sa.Text),
                sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
            ],
        ),
        (
            "m2_orders",
            [
                sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
                sa.Column("id", sa.Text, primary_key=True),
                sa.Column("issuer_id", sa.Text, nullable=False),
                sa.Column("target_id", sa.Text, nullable=False),
                sa.Column("channel_id", sa.Text, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
                sa.Column("state", sa.Text, nullable=False),
            ],
        ),
    ):
        result[name] = sa.Table(name, metadata, *columns)
    for child, columns, parent, parent_columns in (
        ("m2_actions", ["campaign_id", "actor_id"], "campaign_members", ["campaign_id", "user_id"]),
        ("m2_receipts", ["campaign_id", "action_id"], "m2_actions", ["campaign_id", "id"]),
        ("m2_choices", ["campaign_id", "action_id"], "m2_actions", ["campaign_id", "id"]),
        ("m2_responses", ["campaign_id", "choice_id"], "m2_choices", ["campaign_id", "id"]),
        ("m2_locks", ["campaign_id", "action_id"], "m2_actions", ["campaign_id", "id"]),
        ("m2_outbox", ["campaign_id", "action_id"], "m2_actions", ["campaign_id", "id"]),
    ):
        result[child].append_constraint(
            sa.ForeignKeyConstraint(columns, [parent + "." + x for x in parent_columns])
        )
    sa.Index(
        "m2_one_root_action_per_channel",
        result["m2_actions"].c.campaign_id,
        result["m2_actions"].c.channel_id,
        unique=True,
        sqlite_where=sa.text("parent_id IS NULL AND state NOT IN ('complete','aborted')"),
    )
    return result


def upgrade() -> None:
    metadata = sa.MetaData()
    # Parent tables already exist; placeholders resolve FK sorting without creating them.
    for name, columns in (
        ("campaigns", ["id"]),
        ("events", ["id"]),
        ("campaign_members", ["campaign_id", "user_id"]),
    ):
        sa.Table(name, metadata, *(sa.Column(x, sa.Text, primary_key=True) for x in columns))
    tables = define(metadata)
    for table in metadata.sorted_tables:
        if table.name in tables:
            table.create(op.get_bind())
    for name in ("m2_state_history", "m2_receipts", "m2_responses"):
        for action in ("UPDATE", "DELETE"):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER immutable_{name}_{action.lower()} BEFORE {action} "
                    f"ON {name} BEGIN SELECT RAISE(ABORT, 'append-only M2 record'); END"
                )
            )


def downgrade() -> None:
    for name in (
        "m2_responses",
        "m2_choices",
        "m2_receipts",
        "m2_locks",
        "m2_outbox",
        "m2_orders",
        "m2_actions",
        "m2_scenes",
        "m2_state_history",
        "m2_state",
    ):
        op.drop_table(name)
