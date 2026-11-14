"""Immutable Pilot epochs; explicit guarded enrollment exists, no drain producer."""

import sqlalchemy as sa

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


def define(metadata: sa.MetaData) -> sa.Table:
    table = sa.Table(
        "p1_actor_availability",
        metadata,
        sa.Column("campaign_id", sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("owner_id", sa.Text, primary_key=True),
        sa.Column("incarnation", sa.Text, primary_key=True),
        sa.Column("generation", sa.Integer, primary_key=True),
        sa.Column("phase", sa.Text, nullable=False),
        sa.CheckConstraint("length(owner_id)>0 AND length(incarnation)>0"),
        sa.CheckConstraint("typeof(generation)='integer' AND generation>0"),
        sa.CheckConstraint("phase IN ('active','draining')"),
        sqlite_with_rowid=False,
    )
    for sql in GUARDS:
        sa.event.listen(
            table,
            "after_create",
            sa.DDL(sql).execute_if(dialect="sqlite"),  # type: ignore[no-untyped-call]
        )
    return table
