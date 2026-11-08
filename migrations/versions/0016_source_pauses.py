"""Genuine diceless source pause acknowledgments; no manufactured gameplay Action."""

import sqlalchemy as sa
from alembic import op

from girlframe.database.p1_source_schema import define

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata = sa.MetaData()
    bind = op.get_bind()
    for name in ("campaigns", "events"):
        sa.Table(name, metadata, autoload_with=bind)
    define(metadata).create(bind)


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM p1_source_pauses")):
        raise RuntimeError("Refuse to discard actual source permission restoration history")
    op.drop_table("p1_source_pauses")
