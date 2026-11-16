"""Minimal synthetic observation journal, scene cursor and recoverable review claims."""

import sqlalchemy as sa

GUARDS = (
    """CREATE TRIGGER director_inputs_no_update BEFORE UPDATE ON director_inputs
BEGIN SELECT RAISE(ABORT, 'Observation history is immutable'); END""",
    """CREATE TRIGGER director_inputs_no_delete BEFORE DELETE ON director_inputs
BEGIN SELECT RAISE(ABORT, 'Observation history is immutable'); END""",
    """CREATE TRIGGER director_inputs_append BEFORE INSERT ON director_inputs
BEGIN
SELECT CASE WHEN EXISTS (
 SELECT 1 FROM director_inputs WHERE campaign_id=NEW.campaign_id
 AND (scene_id=NEW.scene_id AND sequence=NEW.sequence
 OR source_id=NEW.source_id AND source_revision=NEW.source_revision)
) THEN RAISE(ABORT, 'Observation history cannot be replaced') END;
SELECT CASE WHEN NOT (
 (NEW.source_revision=1 AND NOT EXISTS (
  SELECT 1 FROM director_inputs WHERE campaign_id=NEW.campaign_id AND source_id=NEW.source_id
 )) OR
 (NEW.source_revision>1 AND NEW.kind='message' AND EXISTS (
  SELECT 1 FROM director_inputs WHERE campaign_id=NEW.campaign_id
  AND scene_id=NEW.scene_id AND source_id=NEW.source_id
  AND source_revision=NEW.source_revision-1 AND owner_id=NEW.owner_id AND kind=NEW.kind
 ))
) THEN RAISE(ABORT, 'Observation source revision is invalid') END;
END""",
)


def define(metadata: sa.MetaData) -> dict[str, sa.Table]:
    tables = {}
    for name, columns in (
        ("state", [sa.Column("body_json", sa.Text, nullable=False)]),
        (
            "inputs",
            [
                sa.Column("sequence", sa.Integer, primary_key=True),
                sa.Column("source_id", sa.Text, nullable=False),
                sa.Column("source_revision", sa.Integer, nullable=False),
                sa.Column("owner_id", sa.Text, nullable=False),
                sa.Column("kind", sa.Text, nullable=False),
                sa.Column("accepted_at", sa.Float, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
                sa.UniqueConstraint("campaign_id", "source_id", "source_revision"),
                sa.CheckConstraint("sequence>0 AND source_revision>0"),
                sa.CheckConstraint("kind IN ('message','completed_play')"),
            ],
        ),
        (
            "runs",
            [
                sa.Column("run_id", sa.Text, primary_key=True),
                sa.Column("lease_token", sa.Text, nullable=False, unique=True),
                sa.Column("lease_until", sa.Float, nullable=False),
                sa.Column("status", sa.Text, nullable=False),
                sa.Column("body_json", sa.Text, nullable=False),
                sa.CheckConstraint("status IN ('running','reviewed','failed','stale')"),
            ],
        ),
    ):
        table = sa.Table(
            "director_scene_state" if name == "state" else "director_" + name,
            metadata,
            sa.Column("campaign_id", sa.Text, primary_key=True),
            sa.Column("scene_id", sa.Text, primary_key=True),
            *columns,
            sa.ForeignKeyConstraint(
                ["campaign_id", "scene_id"],
                ["m3_scene_contexts.campaign_id", "m3_scene_contexts.id"],
            ),
            sqlite_with_rowid=False,
        )
        tables[name] = table
    for sql in GUARDS:
        sa.event.listen(
            tables["inputs"],
            "after_create",
            sa.DDL(sql).execute_if(dialect="sqlite"),  # type: ignore[no-untyped-call]
        )
    sa.Index(
        "director_one_running_scene",
        tables["runs"].c.campaign_id,
        tables["runs"].c.scene_id,
        unique=True,
        sqlite_where=tables["runs"].c.status == "running",
    )
    return tables
