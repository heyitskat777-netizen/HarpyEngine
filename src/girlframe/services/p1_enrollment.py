"""Authenticated local Pilot enrollment; no shelving, drain or dispatch activation."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_guarded_intake import IntakePlan, _row, _validate
from girlframe.services.p1_guarded_source import (
    CommitOutcomeUnknown,
    SourceCommittedCleanupError,
    SourceTransactionError,
    run_guarded_source,
)
from girlframe.services.p1_shelving import ShelvingService
from girlframe.services.p1_write_capture import CaptureError, Change
from girlframe.services.read_only_bot import GuildViewer

KIND = "p1.pilot_availability_enrolled"


@dataclass(frozen=True)
class EnrollmentPlan:
    envelope: IntakePlan = field(repr=False)
    row_json: str | None = field(repr=False)


def _validate_enrollment(changes: tuple[Change, ...], plan: EnrollmentPlan) -> None:
    if plan.row_json is not None:
        if not changes:
            raise SourceTransactionError("Missing enrollment write")
        change, *rest = changes
        row = json.loads(plan.row_json)
        key = {k: row[k] for k in ("campaign_id", "owner_id", "incarnation", "generation")}
        if (
            change.table != "p1_actor_availability"
            or change.operation != "insert"
            or change.before_row is not None
            or change.before_key is not None
            or json.loads(change.after_key or "null") != key
            or _row(change) != row
        ):
            raise SourceTransactionError("Enrollment differs from original actor authority")
        changes = tuple(rest)
    _validate(changes, plan.envelope, source_kind=KIND)


def enroll_current_pilot(
    game: GameService, viewer: GuildViewer, key: str, expected_actor: ActorRef
) -> dict[str, Any]:
    """Explicit own-actor enrollment, with fresh source authority even on replay.

    The authenticated adapter supplies viewer, never player-authored identity.
    The expected actor is a stale-view check only, never evidence of ownership.
    No caller can enroll somebody else, resume draining, or certify a freeze.
    """
    game.store.guild_member(viewer)
    if game.store.engine.url.database in (None, ":memory:"):
        raise WorkflowError("ENROLLMENT_UNAVAILABLE: use the migrated local database.")
    settings = Settings(database_url=game.store.engine.url.render_as_string(hide_password=False))
    digest = hashlib.sha256(
        json.dumps(
            {
                "actor": viewer.user_id,
                "kind": KIND,
                "payload": {"original_actor": expected_actor.model_dump(mode="json")},
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()

    def authorize(connection: Connection) -> EnrollmentPlan:
        game.authorize(connection, viewer)
        _, actor, proof = ShelvingService(game)._target(connection, viewer.user_id)
        if actor.kind != "pilot" or actor != expected_actor or proof is None:
            raise WorkflowError("ENROLLMENT_STALE: reopen the current original Pilot.")
        current = (
            connection.execute(
                sa.select(t.actor_availability)
                .where(
                    t.actor_availability.c.campaign_id == game.store.campaign_id,
                    t.actor_availability.c.owner_id == actor.entity,
                    t.actor_availability.c.incarnation == actor.incarnation,
                )
                .order_by(t.actor_availability.c.generation.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if current is not None and (current["phase"] != "active" or current["generation"] != 1):
            raise WorkflowError("ACTOR_UNAVAILABLE: enrollment cannot resume this actor.")
        cached = (
            connection.execute(
                sa.select(t.commands).where(
                    t.commands.c.campaign_id == game.store.campaign_id,
                    t.commands.c.interaction_key == key,
                )
            )
            .mappings()
            .first()
        )
        if cached is not None:
            if cached["request_hash"] != digest:
                raise WorkflowError("IDEMPOTENCY_CONFLICT: this request changed.")
            if current is None:
                raise WorkflowError("ENROLLMENT_UNVERIFIED: recover the saved source.")
            outcome = cached["outcome_json"]
        else:
            outcome = json.dumps(
                dict(
                    original_actor=actor.model_dump(mode="json"),
                    pilot_identity_proof=proof,
                    generation=1,
                    phase="active",
                ),
                sort_keys=True,
            )
        campaign = dict(
            connection.execute(
                sa.select(t.campaigns).where(t.campaigns.c.id == game.store.campaign_id)
            )
            .mappings()
            .one()
        )
        insert = current is None
        row = dict(
            campaign_id=game.store.campaign_id,
            owner_id=actor.entity,
            incarnation=actor.incarnation,
            generation=1,
            phase="active",
        )
        return EnrollmentPlan(
            envelope=IntakePlan(
                campaign=game.store.campaign_id,
                actor=str(viewer.user_id),
                key=key,
                digest=digest,
                outcome=outcome,
                before_campaign=json.dumps(campaign, sort_keys=True),
                event_id=str(uuid4()) if insert else None,
                cached=cached is not None,
            ),
            row_json=json.dumps(row, sort_keys=True) if insert else None,
        )

    def apply(connection: Connection, plan: EnrollmentPlan) -> dict[str, Any]:
        envelope = plan.envelope
        result = dict(json.loads(envelope.outcome))
        if plan.row_json is not None:
            connection.execute(t.actor_availability.insert().values(**json.loads(plan.row_json)))
            game.event(connection, viewer.user_id, key, KIND, event_id=envelope.event_id, **result)
        if not envelope.cached:
            connection.execute(
                t.commands.insert().values(
                    campaign_id=envelope.campaign,
                    interaction_key=key,
                    request_hash=envelope.digest,
                    outcome_json=envelope.outcome,
                )
            )
        return result

    try:
        return run_guarded_source(
            settings, authorize=authorize, operation=apply, validate=_validate_enrollment
        ).result
    except SourceCommittedCleanupError:
        raise WorkflowError("ENROLLMENT_COMMITTED: saved; reopen, do not submit again.") from None
    except CommitOutcomeUnknown:
        raise WorkflowError(
            "ENROLLMENT_UNCERTAIN: check saved state before retry; keep the same key."
        ) from None
    except (CaptureError, SourceTransactionError):
        raise WorkflowError("ENROLLMENT_REJECTED: no enrollment was committed.") from None
