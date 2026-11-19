"""Route private Harpy Keep workflows through their exact original source."""

from typing import Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState, PlayInput
from girlframe.services import m3_harpy_gaze as gaze
from girlframe.services import m3_harpy_intimacy as intimacy
from girlframe.services.m2_game import GameService
from girlframe.services.read_only_bot import GuildViewer


def prepare_keep(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    play: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not play.source_work:
        return None
    return gaze.prepare_keep(game, c, state, viewer, play, channel) or intimacy.prepare_keep(
        game, c, state, viewer, play, channel
    )


def bind_keep(state: GameState, scope: dict[str, Any], action: str, event: str) -> None:
    source = intimacy if scope.get("kind") == intimacy.KIND else gaze
    source.bind_keep(state, scope, action, event)


def validate_keep(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> None:
    source = intimacy if action["data"]["harpy_gaze_keep"].get("kind") == intimacy.KIND else gaze
    source.validate_keep(game, c, state, action)


def finish_keep(
    game: GameService,
    c: Connection,
    action: dict[str, Any],
    event: str,
    viewer: GuildViewer,
    key: str,
) -> None:
    source = intimacy if action["data"]["harpy_gaze_keep"].get("kind") == intimacy.KIND else gaze
    source.finish_keep(game, c, action, event, viewer, key)
