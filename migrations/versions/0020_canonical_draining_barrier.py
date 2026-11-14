"""Block canonical state mutation while availability is draining, without activation."""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

# Frozen historical SQL: do not import mutable runtime schema.
GUARDS = (
    """CREATE TRIGGER p1_canonical_draining_insert BEFORE INSERT ON m2_state
WHEN EXISTS (SELECT 1 FROM p1_actor_availability
 WHERE campaign_id=NEW.campaign_id AND phase='draining')
OR EXISTS (SELECT 1 FROM m2_state AS occupied
 JOIN p1_actor_availability AS availability ON availability.campaign_id=occupied.campaign_id
 WHERE occupied.rowid=NEW.rowid AND availability.phase='draining')
BEGIN SELECT RAISE(ABORT, 'Canonical writes blocked by draining availability'); END""",
    """CREATE TRIGGER p1_canonical_draining_update BEFORE UPDATE ON m2_state
WHEN EXISTS (SELECT 1 FROM p1_actor_availability
 WHERE campaign_id IN (OLD.campaign_id, NEW.campaign_id) AND phase='draining')
OR EXISTS (SELECT 1 FROM m2_state AS occupied
 JOIN p1_actor_availability AS availability ON availability.campaign_id=occupied.campaign_id
 WHERE occupied.rowid=NEW.rowid AND availability.phase='draining')
BEGIN SELECT RAISE(ABORT, 'Canonical writes blocked by draining availability'); END""",
    """CREATE TRIGGER p1_canonical_draining_delete BEFORE DELETE ON m2_state
WHEN EXISTS (SELECT 1 FROM p1_actor_availability
 WHERE campaign_id=OLD.campaign_id AND phase='draining')
BEGIN SELECT RAISE(ABORT, 'Canonical writes blocked by draining availability'); END""",
)


def upgrade() -> None:
    for sql in GUARDS:
        op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("Do not remove the draining barrier; restore a verified backup")
