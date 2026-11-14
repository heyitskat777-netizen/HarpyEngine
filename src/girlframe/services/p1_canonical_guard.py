"""Unused actual-write comparison adapter; no gameplay command is admitted by it."""

import json

from girlframe.engine.p1_canonical_projection import (
    HeatSpendScope,
    ProjectionError,
    ProjectionEvidence,
    verify_heat_spend,
)
from girlframe.services.p1_write_capture import Change


def verify_captured_heat_spend(
    changes: tuple[Change, ...], campaign_id: str, scope: HeatSpendScope
) -> ProjectionEvidence:
    """Require the captured SQL write set to be precisely one canonical update.

    Run inside the still-live capture context, before the outer transaction commits.
    Any command/event/receipt/outbox/choice write is currently unsupported and must
    reject; do not exempt it based on an event kind or caller-supplied actor label.
    No existing runtime producer calls this function. A fabricated Change tuple is
    not trustworthy: integration must supply the active collector's actual output.
    """
    if len(changes) != 1:
        raise ProjectionError("Unclassified SQL write set")
    change = changes[0]
    if change.table != "m2_state" or change.operation != "update":
        raise ProjectionError("Unclassified SQL mutation")
    try:
        if change.before_key is None or change.after_key is None:
            raise ValueError("Missing update keys")
        if json.loads(change.before_key) != {"campaign_id": campaign_id} or json.loads(
            change.after_key
        ) != {"campaign_id": campaign_id}:
            raise ValueError("Changed campaign key")
        if change.before_row is None or change.after_row is None:
            raise ValueError("Missing update rows")
        before = json.loads(change.before_row)
        after = json.loads(change.after_row)
        expected_fields = {"campaign_id", "revision", "body_json"}
        if set(before) != expected_fields or set(after) != expected_fields:
            raise ValueError("Unknown canonical SQL columns")
        if before["campaign_id"] != campaign_id or after["campaign_id"] != campaign_id:
            raise ValueError("Wrong campaign")
        if type(before["revision"]) is not int or type(after["revision"]) is not int:
            raise ValueError("Invalid SQL revision")
        if not isinstance(before["body_json"], str) or not isinstance(after["body_json"], str):
            raise ValueError("Missing canonical body")
    except (ValueError, KeyError, TypeError):
        raise ProjectionError("Canonical SQL evidence is inconsistent") from None
    evidence = verify_heat_spend(before["body_json"], after["body_json"], scope)
    if before["revision"] != evidence.from_revision or after["revision"] != evidence.to_revision:
        raise ProjectionError("Canonical SQL revision differs from its body")
    return evidence
