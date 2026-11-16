"""Synthetic Director observation; no historical transcript or gameplay backfill."""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

# Frozen historical DDL; do not import mutable runtime metadata.
STATEMENTS = (
    """CREATE TABLE director_scene_state (
	campaign_id TEXT NOT NULL,
	scene_id TEXT NOT NULL,
	body_json TEXT NOT NULL,
	PRIMARY KEY (campaign_id, scene_id),
	FOREIGN KEY(campaign_id, scene_id) REFERENCES m3_scene_contexts (campaign_id, id)
)
 WITHOUT ROWID""",
    """CREATE TABLE director_inputs (
	campaign_id TEXT NOT NULL,
	scene_id TEXT NOT NULL,
	sequence INTEGER NOT NULL,
	source_id TEXT NOT NULL,
	source_revision INTEGER NOT NULL,
	owner_id TEXT NOT NULL,
	kind TEXT NOT NULL,
	accepted_at FLOAT NOT NULL,
	body_json TEXT NOT NULL,
	PRIMARY KEY (campaign_id, scene_id, sequence),
	UNIQUE (campaign_id, source_id, source_revision),
	CHECK (sequence>0 AND source_revision>0),
	CHECK (kind IN ('message','completed_play')),
	FOREIGN KEY(campaign_id, scene_id) REFERENCES m3_scene_contexts (campaign_id, id)
)
 WITHOUT ROWID""",
    """CREATE TABLE director_runs (
	campaign_id TEXT NOT NULL,
	scene_id TEXT NOT NULL,
	run_id TEXT NOT NULL,
	lease_token TEXT NOT NULL,
	lease_until FLOAT NOT NULL,
	status TEXT NOT NULL,
	body_json TEXT NOT NULL,
	PRIMARY KEY (campaign_id, scene_id, run_id),
	CHECK (status IN ('running','reviewed','failed','stale')),
	FOREIGN KEY(campaign_id, scene_id) REFERENCES m3_scene_contexts (campaign_id, id),
	UNIQUE (lease_token)
)
 WITHOUT ROWID""",
    """CREATE UNIQUE INDEX director_one_running_scene ON director_runs (campaign_id, scene_id)
WHERE status = 'running'""",
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


def upgrade() -> None:
    for sql in STATEMENTS:
        op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("Observation history must be retained; restore a verified backup")
