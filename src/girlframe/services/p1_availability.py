"""Transaction-local Pilot epoch checks, not a dispatch or shelving capability.

Canonical DB storage is trusted. Guarded enrollment is a separate explicit source;
no drain producer exists. Migration leaves records empty. Missing means unavailable.
"""

import sqlite3
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_shelving import ShelvingService
from girlframe.services.read_only_bot import GuildViewer


@dataclass(frozen=True)
class ActiveEpoch:
    """Snapshot-local fact. Re-read in every source/claim transaction; never serialize a permit."""

    actor: ActorRef = field(repr=False)
    generation: int


def require_current_active(
    connection: Connection, game: GameService, viewer: GuildViewer, expected_generation: int
) -> ActiveEpoch:
    """Revalidate membership, current original Pilot and exact persisted active epoch.

    This check is necessary, never sufficient, for a future source admission. It
    does not authenticate a producer, validate its writes, authorize remote work,
    or assert that any existing gameplay entry point enforces availability.
    """
    raw = connection.connection.driver_connection
    if not isinstance(raw, sqlite3.Connection) or not raw.in_transaction:
        raise WorkflowError("AVAILABILITY_UNVERIFIED: use the current source transaction.")
    game.authorize(connection, viewer)
    if type(expected_generation) is not int or expected_generation < 1:
        raise WorkflowError("AVAILABILITY_STALE: reopen the current source.")
    _, actor, _ = ShelvingService(game)._target(connection, viewer.user_id)
    if actor.kind != "pilot":
        raise WorkflowError("AVAILABILITY_UNSUPPORTED: original Pilot authority is required.")
    row = connection.execute(
        sa.select(t.actor_availability.c.generation, t.actor_availability.c.phase)
        .where(
            t.actor_availability.c.campaign_id == game.store.campaign_id,
            t.actor_availability.c.owner_id == actor.entity,
            t.actor_availability.c.incarnation == actor.incarnation,
        )
        .order_by(t.actor_availability.c.generation.desc())
        .limit(1)
    ).first()
    if row is None or row.phase != "active":
        raise WorkflowError("ACTOR_UNAVAILABLE: current availability is not established.")
    if row.generation != expected_generation:
        raise WorkflowError("AVAILABILITY_STALE: reopen the current source.")
    return ActiveEpoch(actor=actor, generation=row.generation)
