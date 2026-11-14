"""Exact guarded request/withdrawal/decline source; no gameplay freeze or availability change."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.config import Settings
from girlframe.database import tables as t
from girlframe.engine.m2 import RULESET
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_guarded_source import (
    CommitOutcomeUnknown,
    SourceCommittedCleanupError,
    SourceTransactionError,
    run_guarded_source,
)
from girlframe.services.p1_shelving import KIND, ShelvingService
from girlframe.services.p1_write_capture import CaptureError, Change
from girlframe.services.read_only_bot import GuildViewer


@dataclass(frozen=True)
class IntakePlan:
    campaign: str
    actor: str
    key: str = field(repr=False)
    digest: str = field(repr=False)
    outcome: str = field(repr=False)
    before_campaign: str = field(repr=False)
    event_id: str | None = field(repr=False)
    cached: bool


def _row(change: Change, *, before: bool = False) -> dict[str, Any]:
    raw = change.before_row if before else change.after_row
    if raw is None:
        raise SourceTransactionError("Missing original source write evidence")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SourceTransactionError("Invalid source write evidence")
    return value


def _validate(changes: tuple[Change, ...], plan: IntakePlan, *, source_kind: str = KIND) -> None:
    """Classify the complete source, never exempt generic audit or command writes."""
    if plan.cached:
        if changes:
            raise SourceTransactionError("Cached intake replay must not write")
        return
    if plan.event_id is None:
        if (
            len(changes) != 1
            or changes[0].table != "commands_inbox"
            or changes[0].operation != "insert"
        ):
            raise SourceTransactionError("Duplicate intake must write only its receipt")
        _validate_receipt(changes[0], plan)
        return
    if [(x.table, x.operation) for x in changes] != [
        ("campaigns", "update"),
        ("events", "insert"),
        ("commands_inbox", "insert"),
    ]:
        raise SourceTransactionError("Unclassified intake source effects")
    campaign, event, command = changes
    before = json.loads(plan.before_campaign)
    revision = before["revision"] + 1
    if (
        _row(campaign, before=True) != before
        or _row(campaign) != dict(before, revision=revision)
        or json.loads(campaign.before_key or "null") != {"id": plan.campaign}
        or json.loads(campaign.after_key or "null") != {"id": plan.campaign}
    ):
        raise SourceTransactionError("Campaign source revision is inconsistent")
    written_event = _row(event)
    created = written_event.get("created_utc")
    try:
        if not isinstance(created, str) or datetime.fromisoformat(created).utcoffset() != timedelta(
            0
        ):
            raise ValueError("Invalid source time")
    except ValueError:
        raise SourceTransactionError("Source event time is invalid") from None
    expected_event = dict(
        campaign_id=plan.campaign,
        seq=revision,
        command_key=plan.key,
        event_index=0,
        actor_id=plan.actor,
        kind=source_kind,
        payload_json=plan.outcome,
        id=plan.event_id,
        created_utc=created,
        visibility="private",
        schema_version=1,
        ruleset_version=RULESET,
    )
    expected_command = dict(
        campaign_id=plan.campaign,
        interaction_key=plan.key,
        request_hash=plan.digest,
        outcome_json=plan.outcome,
    )
    if (
        event.before_row is not None
        or event.before_key is not None
        or command.before_row is not None
        or command.before_key is not None
        or written_event != expected_event
        or json.loads(event.after_key or "null") != {"campaign_id": plan.campaign, "seq": revision}
        or _row(command) != expected_command
        or json.loads(command.after_key or "null")
        != {
            "campaign_id": plan.campaign,
            "interaction_key": plan.key,
        }
    ):
        raise SourceTransactionError("Intake event or receipt differs from its authorized source")


def change_intake(
    service: ShelvingService,
    viewer: GuildViewer,
    key: str,
    identity: str,
    expected: int,
    operation: Literal["withdraw", "decline"],
) -> dict[str, Any]:
    """Current owner/GM authority and idempotency precede every source operation.

    Historical-actor withdrawal remains owner-controlled. No current-actor proof is
    required to withdraw old intake; this does not mutate the actor or original work.
    """
    service.store.guild_member(viewer)
    if service.store.engine.url.database in (None, ":memory:"):
        raise WorkflowError("GUARDED_INTAKE_UNAVAILABLE: use the migrated local database.")
    settings = Settings(database_url=service.store.engine.url.render_as_string(hide_password=False))
    payload = dict(id=identity, expected=expected, operation=operation)
    digest = hashlib.sha256(
        json.dumps(
            {"actor": viewer.user_id, "kind": KIND, "payload": payload}, sort_keys=True
        ).encode()
    ).hexdigest()

    def authorize(connection: Connection) -> IntakePlan:
        service._authorize(connection, viewer)
        configuration = service._gm(connection, viewer) if operation == "decline" else None
        row = service._rows(connection).get(identity)
        if row is None:
            raise WorkflowError("Shelving request is unavailable.")
        if operation == "withdraw":
            if row["owner"] != viewer.user_id:
                raise WorkflowError("Only the original player may withdraw this request.")
        elif operation != "decline":
            raise WorkflowError("Unknown shelving intake action.")
        campaign = dict(
            connection.execute(
                sa.select(t.campaigns).where(t.campaigns.c.id == service.store.campaign_id)
            )
            .mappings()
            .one()
        )
        cached = (
            connection.execute(
                sa.select(t.commands).where(
                    t.commands.c.campaign_id == service.store.campaign_id,
                    t.commands.c.interaction_key == key,
                )
            )
            .mappings()
            .first()
        )
        if cached is not None:
            if cached["request_hash"] != digest:
                raise WorkflowError("IDEMPOTENCY_CONFLICT: this request changed.")
            outcome = cached["outcome_json"]
        else:
            if (
                type(expected) is not int
                or row["revision"] != expected
                or row["status"] != "requested"
            ):
                raise WorkflowError("STALE_SHELVING_REQUEST: reopen the saved request.")
            outcome = json.dumps(
                dict(
                    row,
                    revision=row["revision"] + 1,
                    status="withdrawn" if operation == "withdraw" else "declined",
                    reviewer=viewer.user_id,
                    configuration_event=configuration,
                ),
                sort_keys=True,
            )
        return IntakePlan(
            campaign=service.store.campaign_id,
            actor=str(viewer.user_id),
            key=key,
            digest=digest,
            outcome=outcome,
            before_campaign=json.dumps(campaign, sort_keys=True),
            event_id=None if cached is not None else str(uuid4()),
            cached=cached is not None,
        )

    return _execute(service, viewer, key, settings, authorize)


def _execute(
    service: ShelvingService,
    viewer: GuildViewer,
    key: str,
    settings: Settings,
    authorize: Callable[[Connection], IntakePlan],
) -> dict[str, Any]:
    def apply(connection: Connection, plan: IntakePlan) -> dict[str, Any]:
        result = dict(json.loads(plan.outcome))
        if not plan.cached:
            if plan.event_id is not None:
                service.game.event(
                    connection, viewer.user_id, key, KIND, event_id=plan.event_id, **result
                )
            connection.execute(
                t.commands.insert().values(
                    campaign_id=plan.campaign,
                    interaction_key=key,
                    request_hash=plan.digest,
                    outcome_json=plan.outcome,
                )
            )
        return result

    try:
        return run_guarded_source(
            settings, authorize=authorize, operation=apply, validate=_validate
        ).result
    except SourceCommittedCleanupError:
        raise WorkflowError(
            "INTAKE_COMMITTED: this request was saved. "
            "Reopen its saved view; do not submit it again."
        ) from None
    except CommitOutcomeUnknown:
        raise WorkflowError(
            "INTAKE_OUTCOME_UNCERTAIN: reopen the saved request before any retry. "
            "Do not submit a new request key."
        ) from None
    except (CaptureError, SourceTransactionError):
        raise WorkflowError(
            "INTAKE_SOURCE_REJECTED: no intake change was committed. Reopen the saved request."
        ) from None


def _validate_receipt(change: Change, plan: IntakePlan) -> None:
    if (
        change.before_row is not None
        or change.before_key is not None
        or json.loads(change.after_key or "null")
        != {"campaign_id": plan.campaign, "interaction_key": plan.key}
        or _row(change)
        != dict(
            campaign_id=plan.campaign,
            interaction_key=plan.key,
            request_hash=plan.digest,
            outcome_json=plan.outcome,
        )
    ):
        raise SourceTransactionError("Duplicate intake receipt differs from its source")


def request_intake(
    service: ShelvingService, viewer: GuildViewer, key: str, owner: int | None
) -> dict[str, Any]:
    """Bind proposal or explicit player request to current authority and actor proof."""
    service.store.guild_member(viewer)
    if service.store.engine.url.database in (None, ":memory:"):
        raise WorkflowError("GUARDED_INTAKE_UNAVAILABLE: use the migrated local database.")
    settings = Settings(database_url=service.store.engine.url.render_as_string(hide_password=False))
    target = viewer.user_id if owner is None else owner
    digest = hashlib.sha256(
        json.dumps(
            {"actor": viewer.user_id, "kind": KIND, "payload": {"owner": target}},
            sort_keys=True,
        ).encode()
    ).hexdigest()

    def authorize(connection: Connection) -> IntakePlan:
        service._authorize(connection, viewer)
        configuration = service._gm(connection, viewer) if target != viewer.user_id else None
        state, original, evidence = service._target(connection, target)
        actor = original.model_dump(mode="json")
        campaign = dict(
            connection.execute(
                sa.select(t.campaigns).where(t.campaigns.c.id == service.store.campaign_id)
            )
            .mappings()
            .one()
        )
        cached = (
            connection.execute(
                sa.select(t.commands).where(
                    t.commands.c.campaign_id == service.store.campaign_id,
                    t.commands.c.interaction_key == key,
                )
            )
            .mappings()
            .first()
        )
        event_id = None
        if cached is not None:
            if cached["request_hash"] != digest:
                raise WorkflowError("IDEMPOTENCY_CONFLICT: this request changed.")
            outcome = cached["outcome_json"]
            if json.loads(outcome).get("original_actor") != actor:
                raise WorkflowError(
                    "STALE_SHELVING_REQUEST: reopen the original request or request anew."
                )
        else:
            row = next(
                (
                    row
                    for row in service._rows(connection).values()
                    if row["owner"] == target
                    and row["original_actor"] == actor
                    and row["status"] == "requested"
                ),
                None,
            )
            if row is None:
                row = dict(
                    id=str(uuid4()),
                    owner=target,
                    original_actor=actor,
                    pilot_identity_proof=evidence,
                    revision=1,
                    status="requested",
                    initiator=viewer.user_id,
                    player_requested=target == viewer.user_id,
                    configuration_event=configuration,
                    game_revision=state.revision,
                )
                event_id = str(uuid4())
            elif target == viewer.user_id and not row["player_requested"]:
                row = dict(
                    row,
                    revision=row["revision"] + 1,
                    player_requested=True,
                    player_requester=viewer.user_id,
                    player_request_game_revision=state.revision,
                    pilot_identity_proof=evidence,
                )
                event_id = str(uuid4())
            outcome = json.dumps(row, sort_keys=True)
        return IntakePlan(
            campaign=service.store.campaign_id,
            actor=str(viewer.user_id),
            key=key,
            digest=digest,
            outcome=outcome,
            before_campaign=json.dumps(campaign, sort_keys=True),
            event_id=event_id,
            cached=cached is not None,
        )

    return _execute(service, viewer, key, settings, authorize)
