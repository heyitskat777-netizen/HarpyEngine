"""Private append-only assistance records in the existing campaign database."""

import sqlalchemy as sa

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


def define(metadata: sa.MetaData) -> sa.Table:
    table = sa.Table(
        "p2_assistance_revisions",
        metadata,
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("proposal_id", sa.Text, primary_key=True),
        sa.Column("revision", sa.Integer, primary_key=True),
        sa.Column("owner_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("body_json", sa.Text, nullable=False),
        sa.Column("event_id", sa.ForeignKey("events.id"), nullable=False, unique=True),
        sa.ForeignKeyConstraint(
            ["campaign_id", "owner_id"],
            ["campaign_members.campaign_id", "campaign_members.user_id"],
        ),
        sa.CheckConstraint("typeof(revision)='integer' AND revision BETWEEN 1 AND 3"),
        sa.CheckConstraint("status IN ('requested','draft','failed','approved','rejected')"),
        sqlite_with_rowid=False,
    )
    for sql in GUARDS:
        sa.event.listen(
            table,
            "after_create",
            sa.DDL(sql).execute_if(dialect="sqlite"),  # type: ignore[no-untyped-call]
        )
    return table
