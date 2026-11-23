"""Audit saved role projections and compare two synthetic campaign lengths.

This reads completed fixture artifacts, never canonical campaign state or models.
The GM blind packets must remain separate from fixture expected judgments.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    root, baseline = args.directory, args.baseline
    summary = json.loads((root / "campaign-summary.json").read_text())
    smoke = json.loads((baseline / "campaign-summary.json").read_text())
    assert summary["synthetic"] is True and smoke["synthetic"] is True
    assert summary["inputs"] > smoke["inputs"]
    packets = json.loads((root / "handler-packets.json").read_text())["audits"]
    events = json.loads((root / "campaign-events.json").read_text())["events"]
    forbidden = (
        "PRIVATE_SUSTAINED_GM_MOTIVE",
        "PRIVATE_LATCH_UNREPORTED_CONTACT",
        "violet reflector",
        "SYNTHETIC_TRIAL_GM_PRIVATE_CANARY",
        "Being the cause of a preventable loss",
        "Watching preventable harm",
    )
    requests = {}
    for row in packets:
        encoded = json.dumps(row)
        assert all(value not in encoded for value in forbidden)
        if row["handler"] is not None:
            request = row["handler"]
            assert request["context"]["audience"] == "actor"
            assert request["context"]["actor"]["kind"] == "handler"
            assert row["handler_dossier"]["actor"] == request["context"]["actor"]
            requests[row["input"]] = request
    replies = [row for row in events if row["kind"] == "handler_intervention"]
    for row in replies:
        reply = row["reply"]
        assert all(value not in reply["text"] for value in forbidden)
        allowed = {ref["id"] for ref in requests[row["input_number"]]["context"]["references"]}
        assert set(reply["source_refs"]) <= allowed
    fields = ("actor", "native_total", "verdict", "positive", "negative")
    assert [{k: r[k] for k in fields} for r in summary["contextual_rulings"]] == [
        {k: r[k] for k in fields} for r in smoke["contextual_rulings"]
    ]
    mission_fields = (
        "name",
        "success",
        "permissions_before",
        "permissions_after",
        "discipline_tasks",
        "status_order",
    )
    assert [{k: r[k] for k in mission_fields} for r in summary["missions"]] == [
        {k: r[k] for k in mission_fields} for r in smoke["missions"]
    ]
    assert summary["heat_spending"] == smoke["heat_spending"]
    assert summary["native_receipts"] == summary["mission_plays"] + 2 * len(summary["periods"])
    assert summary["strain_rolls"] == 3 * len(summary["periods"])
    assert summary["pending_native_choices"] == 0
    assert summary["database_reopen_replay"]
    assert len(requests) == summary["inputs"]
    assert len(replies) == summary["handler_interventions"]
    result = dict(
        handler_requests=len(requests),
        reviewed_replies=len(replies),
        role_audit_groups=len(packets),
        forbidden_fragments_checked=len(forbidden),
        detected_leaks=0,
        citations_in_scope=True,
        reduced_inputs=smoke["inputs"],
        expanded_inputs=summary["inputs"],
        same_native_results_costs_and_outcomes=True,
    )
    p = root / "independent-artifact-audit.json"
    p.write_text(json.dumps(result, indent=2) + "\n")
    p.chmod(0o600)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
