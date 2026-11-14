"""Unused preparation journal; dispatch remains unavailable, legacy rows untouched."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def define(metadata: sa.MetaData) -> dict[str, sa.Table]:
    effects = sa.Table(
        "external_effects",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("event_seq", sa.Integer, nullable=False),
        sa.Column("source_kind", sa.Text, nullable=False),
        sa.Column("source_id", sa.Text, nullable=False),
        sa.Column("source_revision", sa.Integer, nullable=False),
        sa.Column("step_key", sa.Text, nullable=False),
        sa.Column("operation", sa.Text, nullable=False),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("payload_digest", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False, server_default="prepared"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["campaign_id", "event_seq"], ["events.campaign_id", "events.seq"]),
        sa.UniqueConstraint(
            "campaign_id", "source_kind", "source_id", "source_revision", "step_key"
        ),
        sa.CheckConstraint("state = 'prepared'"),
        sa.CheckConstraint("revision = 1 AND schema_version = 1 AND source_revision >= 1"),
        sa.CheckConstraint(
            "operation IN ('control_post', 'public_post', 'private_post', "
            "'facilitator_notice', 'permission_apply', 'permission_restore')"
        ),
    )
    actors = sa.Table(
        "external_effect_actors",
        metadata,
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("effect_id", sa.Text, primary_key=True),
        sa.Column("actor_token", sa.Text, primary_key=True),
        sa.Column("relation", sa.Text, primary_key=True),
        sa.Column("actor_json", sa.Text, nullable=False),
        sa.Column("availability_generation", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id", "effect_id"], ["external_effects.campaign_id", "external_effects.id"]
        ),
        sa.CheckConstraint("availability_generation >= 1"),
        sa.CheckConstraint("relation IN ('subject', 'owner', 'audience', 'shared_scene')"),
    )
    sa.Index("ix_external_effect_actor", actors.c.campaign_id, actors.c.actor_token)
    resources = sa.Table(
        "external_resources",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("resource_key", sa.Text, primary_key=True),
        sa.Column("descriptor_json", sa.Text, nullable=False),
        # Physical channel ownership cannot cross campaigns, including DM channels.
        sa.UniqueConstraint("resource_key"),
    )
    links = sa.Table(
        "external_effect_resources",
        metadata,
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("effect_id", sa.Text, primary_key=True),
        sa.Column("resource_key", sa.Text, primary_key=True),
        sa.Column("binding_json", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id", "effect_id"], ["external_effects.campaign_id", "external_effects.id"]
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id", "resource_key"],
            ["external_resources.campaign_id", "external_resources.resource_key"],
        ),
    )
    sa.Index("ix_external_effect_resource", links.c.campaign_id, links.c.resource_key)
    return {"effects": effects, "actors": actors, "resources": resources, "links": links}


def upgrade() -> None:
    metadata = sa.MetaData()
    bind = op.get_bind()
    for name in ("campaigns", "events"):
        sa.Table(name, metadata, autoload_with=bind)
    tables = define(metadata)
    for table in tables.values():
        table.create(bind)


def downgrade() -> None:
    names = (
        "external_effect_resources",
        "external_effect_actors",
        "external_effects",
        "external_resources",
    )
    bind = op.get_bind()
    # Even prepared rows contain irreplaceable private payload/incidence evidence.
    for name in names:
        if bind.scalar(sa.text(f"SELECT count(*) FROM {name}")):
            raise RuntimeError("Refuse to discard external-effect preparation evidence")
    for name in names:
        op.drop_table(name)
