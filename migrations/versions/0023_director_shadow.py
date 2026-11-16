"""Explicit synthetic source references and durable shadow outcomes."""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None
STATEMENTS = (
    """CREATE TABLE director_knowledge (
	campaign_id TEXT NOT NULL,
	scene_id TEXT NOT NULL,
	id TEXT NOT NULL,
	body_json TEXT NOT NULL,
	PRIMARY KEY (campaign_id, id),
	FOREIGN KEY(campaign_id, scene_id) REFERENCES m3_scene_contexts (campaign_id, id)
)
 WITHOUT ROWID""",
    """CREATE TABLE director_shadow (
	campaign_id TEXT NOT NULL,
	scene_id TEXT NOT NULL,
	id TEXT NOT NULL,
	body_json TEXT NOT NULL,
	PRIMARY KEY (campaign_id, id),
	FOREIGN KEY(campaign_id, scene_id) REFERENCES m3_scene_contexts (campaign_id, id)
)
 WITHOUT ROWID""",
    """CREATE TRIGGER director_knowledge_no_update BEFORE UPDATE ON director_knowledge
BEGIN SELECT RAISE(ABORT, 'Director reference history is immutable'); END""",
    """CREATE TRIGGER director_knowledge_no_delete BEFORE DELETE ON director_knowledge
BEGIN SELECT RAISE(ABORT, 'Director reference history is immutable'); END""",
    """CREATE TRIGGER director_knowledge_no_replace BEFORE INSERT ON director_knowledge
WHEN EXISTS (SELECT 1 FROM director_knowledge
WHERE campaign_id=NEW.campaign_id AND id=NEW.id)
BEGIN SELECT RAISE(ABORT, 'Director reference history cannot be replaced'); END""",
    """CREATE TRIGGER director_shadow_no_update BEFORE UPDATE ON director_shadow
BEGIN SELECT RAISE(ABORT, 'Director reference history is immutable'); END""",
    """CREATE TRIGGER director_shadow_no_delete BEFORE DELETE ON director_shadow
BEGIN SELECT RAISE(ABORT, 'Director reference history is immutable'); END""",
    """CREATE TRIGGER director_shadow_no_replace BEFORE INSERT ON director_shadow
WHEN EXISTS (SELECT 1 FROM director_shadow
WHERE campaign_id=NEW.campaign_id AND id=NEW.id)
BEGIN SELECT RAISE(ABORT, 'Director reference history cannot be replaced'); END""",
)


def upgrade() -> None:
    for sql in STATEMENTS:
        op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("Director references must be retained; restore a verified backup")
