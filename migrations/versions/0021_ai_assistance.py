"""Private synthetic assistance history; no campaign/gameplay backfill or activation."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

# Frozen historical SQL; independent of mutable runtime metadata.
GUARDS = (
    """CREATE TRIGGER p2_assistance_no_update BEFORE UPDATE ON p2_assistance_revisions
BEGIN SELECT RAISE(ABORT, 'Assistance history is immutable'); END""",
    """CREATE TRIGGER p2_assistance_no_delete BEFORE DELETE ON p2_assistance_revisions
BEGIN SELECT RAISE(ABORT, 'Assistance history is immutable'); END""",
    """CREATE TRIGGER p2_assistance_append BEFORE INSERT ON p2_assistance_revisions
BEGIN
SELECT CASE WHEN NOT (
 (NEW.revision=1 AND NEW.status='requested' AND NOT EXISTS (
  SELECT 1 FROM p2_assistance_revisions WHERE campaign_id=NEW.campaign_id
  AND proposal_id=NEW.proposal_id
 )) OR
 (NEW.revision=2 AND NEW.status IN ('draft','failed') AND EXISTS (
  SELECT 1 FROM p2_assistance_revisions WHERE campaign_id=NEW.campaign_id
  AND proposal_id=NEW.proposal_id AND owner_id=NEW.owner_id
  AND revision=1 AND status='requested'
 ) AND NOT EXISTS (
  SELECT 1 FROM p2_assistance_revisions WHERE campaign_id=NEW.campaign_id
  AND proposal_id=NEW.proposal_id AND revision>=2
 )) OR
 (NEW.revision=3 AND NEW.status IN ('approved','rejected') AND EXISTS (
  SELECT 1 FROM p2_assistance_revisions WHERE campaign_id=NEW.campaign_id
  AND proposal_id=NEW.proposal_id AND owner_id=NEW.owner_id
  AND revision=2 AND status='draft'
 ) AND NOT EXISTS (
  SELECT 1 FROM p2_assistance_revisions WHERE campaign_id=NEW.campaign_id
  AND proposal_id=NEW.proposal_id AND revision>=3
 ))
) THEN RAISE(ABORT, 'Unsupported assistance transition') END;
END""",
)


def upgrade() -> None:
    op.execute("""CREATE TABLE p2_assistance_revisions (
 campaign_id TEXT NOT NULL,
 proposal_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision BETWEEN 1 AND 3),
 owner_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('requested','draft','failed','approved','rejected')),
 body_json TEXT NOT NULL,
 event_id TEXT NOT NULL UNIQUE REFERENCES events(id),
 PRIMARY KEY(campaign_id, proposal_id, revision),
 FOREIGN KEY(campaign_id, owner_id) REFERENCES campaign_members(campaign_id, user_id)
) WITHOUT ROWID""")
    for sql in GUARDS:
        op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("Assistance history must be retained; restore a verified backup")
