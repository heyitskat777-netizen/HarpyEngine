"""Pause only an actually activated diceless Bonded source; keep rule choices in its service."""

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_bonded import Child, Source, records
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def active(state: GameState, identity: str) -> bool:
    return any(
        x.id == identity and x.action is None and x.phase in ("results", "child")
        for x in records(state, Source)
    )


def reserve(game: "GameService", c: Connection, state: GameState) -> None:
    from girlframe.services.p1_facilitator import require_scene_clear

    table = t.p1_source_pauses
    for source in records(state, Source):
        if not active(state, source.id):
            continue
        existing = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == source.id,
                )
            )
            .mappings()
            .first()
        )
        if existing is not None:
            continue
        scene = game.scene(c, source.cast.channel)
        lock = game.lock(c, source.cast.channel)
        require_scene_clear(game, c, source.cast.channel)
        if scene["id"] != source.cast.id or (lock and lock["state"] != "released"):
            raise WorkflowError(
                "Finish the actual pending scene Play before activating this source"
            )
        other = c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.channel_id == str(source.cast.channel),
                table.c.state != "closed",
            )
        )
        if other is not None:
            raise WorkflowError("Finish or restore the previous actual source pause first")
        if source.effect_event is None:
            raise WorkflowError("Activate the real source before reserving its scene pause")
        c.execute(
            table.insert().values(
                campaign_id=game.store.campaign_id,
                id=source.id,
                kind="bonded",
                channel_id=str(source.cast.channel),
                scene_id=source.cast.id,
                event_id=source.effect_event,
                state="acquiring",
                snapshot_json="{}",
            )
        )


def projection(game: "GameService", c: Connection, identity: str) -> dict[str, Any]:
    table = t.p1_source_pauses
    row = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    return (
        dict(state=row["state"], error=row["last_error"], retry=row["state"] == "review")
        if row
        else dict(state="not_activated", error="", retry=False)
    )


def require_ready(game: "GameService", c: Connection, state: GameState, identity: str) -> None:
    if not active(state, identity) or projection(game, c, identity)["state"] != "held":
        raise WorkflowError(
            "SOURCE_PAUSE_NOT_ACKNOWLEDGED: wait for the actual scene pause; "
            "no choice effects applied"
        )


def require_clear(
    game: "GameService",
    c: Connection,
    channel: int,
    *,
    prepared: PlayInput | None = None,
    action: dict[str, Any] | None = None,
) -> None:
    table = t.p1_source_pauses
    rows = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.channel_id == str(channel),
                table.c.state != "closed",
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    state = load_state(c, game.store.campaign_id)
    for row in rows:
        source_work = (
            prepared.source_work
            if prepared
            else (action or {}).get("data", {}).get("bonded_child", {}).get("child")
        )
        child = next(
            (x for x in records(state, Child) if x.id == source_work and x.source == row["id"]),
            None,
        )
        if child is None or row["state"] != "held" or not active(state, row["id"]):
            raise WorkflowError(
                "SOURCE_SCENE_PAUSED: resolve the original source or wait for restoration"
            )


def retry(game: "GameService", viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.services.m3_access import Access
        from girlframe.services.m3_bonded import prove

        Access(game.store).authorize(c, viewer, "plays", director_response=True)
        state = load_state(c, game.store.campaign_id)
        source = prove(game, c, state, identity)
        if viewer.user_id not in source.controllers.values():
            raise WorkflowError("Only original source owners review its permission delivery")
        table = t.p1_source_pauses
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == identity,
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["state"] != "review" or row["lease_until"] > int(game.store.clock()):
            raise WorkflowError("Reopen the actual source pause review first")
        c.execute(
            table.update()
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .values(state="acquiring" if active(state, identity) else "restoring", last_error="")
        )
        game.event(c, viewer.user_id, key, "m3.source_pause_retry", source_id=identity)
        return projection(game, c, identity)

    return game.store._write(
        viewer, key, "m3.source_pause_retry", dict(source_id=identity), operation, auto_audit=False
    )
