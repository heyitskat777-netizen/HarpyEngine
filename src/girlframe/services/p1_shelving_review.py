"""Transaction-current actor review evidence, never an availability/dispatch permit.

The authenticated adapter supplies GuildViewer. No caller may construct one from
player-authored metadata. This module does not install a freeze or an authority row.
"""

import json
import sqlite3
from typing import Literal

import sqlalchemy as sa
from pydantic import Field, ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.services.m2_game import GameService
from girlframe.services.m3_incarnations import IdentityProof
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_shelving import KIND, ShelvingService
from girlframe.services.read_only_bot import GuildViewer


class ReviewEvidence(Model):
    """Private facts from one read snapshot; serializing this grants no authority."""

    campaign_id: str
    request_id: str
    request_revision: int = Field(ge=1)
    request_event: str
    owner: Snowflake
    actor: ActorRef
    identity: IdentityProof
    reviewer: Snowflake
    configuration_event: str
    game_revision: int = Field(ge=0)
    player_requested: bool
    availability_authority: Literal[False] = False


class ShelvingReviewService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store
        self.intake = ShelvingService(game)

    def inspect(self, viewer: GuildViewer, identity: str, expected: int) -> ReviewEvidence:
        """Read one consistent snapshot, with current membership and facilitator checks.

        The evidence expires with this snapshot. Future mutation integration must
        call inspect_transaction again in its own transaction; a saved result is
        not a capability, cached authorization or a promise of safe availability.
        """
        with self.store.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            return self.inspect_transaction(connection, viewer, identity, expected)

    def inspect_transaction(
        self, connection: Connection, viewer: GuildViewer, identity: str, expected: int
    ) -> ReviewEvidence:
        """Resolve original actor and current reviewer inside the caller's transaction.

        Performs only reads. This is the authority preflight, not an availability
        transition. Resource generations, incidence, drain and final canonical
        transaction validation remain separate mandatory prerequisites.
        """
        raw = connection.connection.driver_connection
        if not isinstance(raw, sqlite3.Connection) or not raw.in_transaction:
            raise WorkflowError("Shelving review requires an open SQLite transaction.")
        self.game.authorize(connection, viewer, game=False)
        if type(expected) is not int or expected < 1:
            raise WorkflowError("STALE_SHELVING_REQUEST: use the saved request revision.")
        configuration = self.intake._gm(connection, viewer)
        source = connection.execute(
            sa.select(t.events.c.id, t.events.c.payload_json)
            .where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == KIND,
                sa.func.json_extract(t.events.c.payload_json, "$.id") == identity,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        ).first()
        if source is None:
            raise WorkflowError("Shelving request is unavailable.")
        try:
            row = json.loads(source.payload_json)
            original = ActorRef.model_validate(row["original_actor"])
            owner = row["owner"]
            revision = row["revision"]
            if type(owner) is not int or type(revision) is not int:
                raise ValueError("Invalid request identity")
            if row["status"] != "requested" or revision != expected:
                raise WorkflowError("STALE_SHELVING_REQUEST: reopen the saved request.")
            # Handler/body and NPC authority require separate canonical adapters.
            if original.kind != "pilot":
                raise WorkflowError("SHELVING_REVIEW_UNSUPPORTED: Pilot evidence only.")
            if original.entity != str(owner):
                raise ValueError("Request owner does not match original actor")
            if type(row["player_requested"]) is not bool:
                raise ValueError("Invalid player request evidence")
            if row["player_requested"] and row.get("player_requester", row["initiator"]) != owner:
                raise ValueError("Player request has no original-player provenance")
            saved = IdentityProof.model_validate(row["pilot_identity_proof"])
            if saved.owner != owner or saved.character != original.incarnation:
                raise ValueError("Saved proof does not match original request")
        except (KeyError, TypeError, ValueError, ValidationError):
            raise WorkflowError(
                "SHELVING_IDENTITY_UNVERIFIED: reopen intake with original source evidence."
            ) from None
        state, actor, proof = self.intake._target(connection, owner)
        if actor != original:
            raise WorkflowError("STALE_SHELVING_ACTOR: this request belongs to a previous actor.")
        assert proof is not None
        current = IdentityProof.model_validate(proof)
        # A profile revision can advance for the same actor. Prove the saved
        # request snapshot still exists rather than equating revision with person.
        saved_snapshot = connection.scalar(
            sa.select(t.snapshots.c.event_id)
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == t.snapshots.c.campaign_id,
                    t.events.c.id == t.snapshots.c.event_id,
                ),
            )
            .where(
                t.snapshots.c.campaign_id == self.store.campaign_id,
                t.snapshots.c.user_id == str(owner),
                t.snapshots.c.character_id == saved.profile,
                t.snapshots.c.revision == saved.source_profile_revision,
                t.snapshots.c.event_id == saved.snapshot_event,
            )
        )
        if saved_snapshot is None or saved.profile != current.profile:
            raise WorkflowError("SHELVING_IDENTITY_UNVERIFIED: original snapshot is unavailable.")
        return ReviewEvidence(
            campaign_id=self.store.campaign_id,
            request_id=identity,
            request_revision=revision,
            request_event=source.id,
            owner=owner,
            actor=actor,
            identity=current,
            reviewer=viewer.user_id,
            configuration_event=configuration,
            game_revision=state.revision,
            player_requested=row["player_requested"],
        )
