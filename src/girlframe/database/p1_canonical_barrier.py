"""Conservative canonical write barrier, not a complete actor freeze."""

import sqlalchemy as sa

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


def install(metadata: sa.MetaData) -> None:
    for sql in GUARDS:
        sa.event.listen(
            metadata,
            "after_create",
            sa.DDL(  # type: ignore[no-untyped-call]
                sql.replace("CREATE TRIGGER ", "CREATE TRIGGER IF NOT EXISTS ", 1)
            ).execute_if(dialect="sqlite"),
        )
