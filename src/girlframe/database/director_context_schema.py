"""Append-only source knowledge and shadow outcomes in the existing store."""

import sqlalchemy as sa


def define(metadata: sa.MetaData) -> dict[str, sa.Table]:
    result = {}
    for name in ("knowledge", "shadow"):
        table = sa.Table(
            "director_" + name,
            metadata,
            sa.Column("campaign_id", sa.Text, primary_key=True),
            sa.Column("scene_id", sa.Text, nullable=False),
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("body_json", sa.Text, nullable=False),
            sa.ForeignKeyConstraint(
                ["campaign_id", "scene_id"],
                ["m3_scene_contexts.campaign_id", "m3_scene_contexts.id"],
            ),
            sqlite_with_rowid=False,
        )
        for operation in ("UPDATE", "DELETE"):
            sql = f"""CREATE TRIGGER director_{name}_no_{operation.lower()}
BEFORE {operation} ON director_{name}
BEGIN SELECT RAISE(ABORT, 'Director reference history is immutable'); END"""
            sa.event.listen(table, "after_create", sa.DDL(sql).execute_if(dialect="sqlite"))  # type: ignore[no-untyped-call]
        sql = f"""CREATE TRIGGER director_{name}_no_replace BEFORE INSERT ON director_{name}
WHEN EXISTS (SELECT 1 FROM director_{name}
WHERE campaign_id=NEW.campaign_id AND id=NEW.id)
BEGIN SELECT RAISE(ABORT, 'Director reference history cannot be replaced'); END"""
        sa.event.listen(table, "after_create", sa.DDL(sql).execute_if(dialect="sqlite"))  # type: ignore[no-untyped-call]
        result[name] = table
    return result
