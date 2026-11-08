"""Durable human-facilitator channel notices, preserving gameplay histories."""

import sqlalchemy as sa
from alembic import op

from girlframe.database.p1_schema import define

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reference parents already exist; use their reflected metadata for foreign keys.
    metadata = sa.MetaData()
    bind = op.get_bind()
    for name in ("campaigns", "events"):
        sa.Table(name, metadata, autoload_with=bind)
    define(metadata).create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM p1_facilitator_outbox")):
        raise RuntimeError("Refuse to discard saved facilitator delivery history")
    op.drop_table("p1_facilitator_outbox")
