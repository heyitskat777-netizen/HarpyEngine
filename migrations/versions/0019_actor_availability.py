"""Add empty preparation-only availability epochs; no historic authority backfill."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

GUARDS = (
    """CREATE TRIGGER p1_availability_no_update BEFORE UPDATE ON p1_actor_availability
BEGIN SELECT RAISE(ABORT, 'Availability history is immutable'); END""",
    """CREATE TRIGGER p1_availability_no_delete BEFORE DELETE ON p1_actor_availability
BEGIN SELECT RAISE(ABORT, 'Availability history is immutable'); END""",
    """CREATE TRIGGER p1_availability_append BEFORE INSERT ON p1_actor_availability
BEGIN
SELECT CASE WHEN EXISTS (
 SELECT 1 FROM p1_actor_availability WHERE campaign_id=NEW.campaign_id
 AND owner_id=NEW.owner_id AND incarnation=NEW.incarnation AND generation=NEW.generation
) THEN RAISE(ABORT, 'Availability history cannot be replaced') END;
SELECT CASE WHEN NOT (
 (NEW.generation=1 AND NEW.phase='active' AND NOT EXISTS (
  SELECT 1 FROM p1_actor_availability WHERE campaign_id=NEW.campaign_id
  AND owner_id=NEW.owner_id AND incarnation=NEW.incarnation
 )) OR
 (NEW.phase='draining' AND NEW.generation=2 AND EXISTS (
  SELECT 1 FROM p1_actor_availability WHERE campaign_id=NEW.campaign_id
  AND owner_id=NEW.owner_id AND incarnation=NEW.incarnation
  AND generation=1 AND phase='active'
 ))
) THEN RAISE(ABORT, 'Unsupported availability transition') END;
END""",
)


def upgrade() -> None:
    op.execute("""CREATE TABLE p1_actor_availability (
 campaign_id TEXT NOT NULL REFERENCES campaigns(id),
 owner_id TEXT NOT NULL CHECK(length(owner_id)>0),
 incarnation TEXT NOT NULL CHECK(length(incarnation)>0),
 generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0),
 phase TEXT NOT NULL CHECK(phase IN ('active','draining')),
 PRIMARY KEY(campaign_id, owner_id, incarnation, generation)
) WITHOUT ROWID""")
    for sql in GUARDS:
        op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("Availability history must not be discarded; restore a verified backup")
