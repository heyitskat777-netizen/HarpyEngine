"""Offline five-Play adapter rehearsal, optionally with a manually edited GM proposal."""

import argparse
import json
from collections import Counter
from pathlib import Path

from audit_director_rulings import ROOT, render, run_case

from girlframe.ai.gm_protocol import GMProposal, OfflineReviewProvider


class ManualProvider:
    """A human supplies the GM judgment; no SDK, HTTP call or token spending."""

    def __init__(self, directory):
        self.directory = directory
        self.calls = 0
        self.last = None
        self.previous = None

    def propose(self, packet):
        self.calls += 1
        self.last = packet
        if self.previous and self.previous.request_id == packet.request_id:
            return self.previous
        default = OfflineReviewProvider().propose(packet)
        if packet.stage != "awaiting_keep_ruling":
            return default
        packet_path = self.directory / "request.json"
        proposal_path = self.directory / "proposal.json"
        packet_path.write_text(packet.model_dump_json(indent=2) + "\n")
        proposal_path.write_text(default.model_dump_json(indent=2) + "\n")
        print(f"\nPrivate synthetic request: {packet_path}")
        print(f"Edit this proposal in another editor: {proposal_path}")
        print("Actual ARE:", packet.positive, "ARE NOT:", packet.negative)
        print("For enough/not_enough, assess every demand with its ID, a sufficient boolean,")
        print("evidence_ids including traits, actual trait/polarity claims, and private_reason.")
        print("Keep the exact request_id; cite goal, receipt and any condition IDs. effects=[]")
        print("Leaving needs_clarification is valid and leaves the owner choice pending.")
        input("Press Enter after saving the proposal: ")
        self.previous = GMProposal.model_validate_json(proposal_path.read_text())
        return self.previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="One ID from tools/fixtures/director_ruling_audit.json")
    parser.add_argument("--list", action="store_true", help="List available synthetic cases")
    parser.add_argument(
        "--interactive", action="store_true", help="Manually supply one Keep GM proposal"
    )
    parser.add_argument("--goal", help="Override the selected synthetic case's declared goal")
    parser.add_argument("--frame", type=Path, help="JSON stakes, demands and intent for that goal")
    args = parser.parse_args()
    cases = json.loads((ROOT / "tools/fixtures/director_ruling_audit.json").read_text())["cases"]
    if args.list:
        for case in cases:
            print(case["id"], case["play"], "—", case["goal"])
        return 0
    if args.interactive and not args.case:
        parser.error("--interactive requires one --case (for example precision_control_mid)")
    if args.goal and not (args.interactive and args.frame):
        parser.error("--goal requires --interactive and an explicitly authored --frame")
    if args.case:
        selected = [case.copy() for case in cases if case["id"] == args.case]
        if not selected:
            parser.error("Unknown case; use --list")
    else:
        selected = []
        seen = set()
        for case in cases:
            if case["play"] not in seen and case["desired"] != "native_guard":
                selected.append(case.copy())
                seen.add(case["play"])
    if args.interactive and selected[0]["play"] != "keep_your_head":
        parser.error("Manual contextual judgment currently consumes Keep's native ruling only")
    output = ROOT / "var/gm-adapter-playtest"
    output.mkdir(parents=True, exist_ok=True)
    print("OFFLINE SYNTHETIC REHEARSAL. No provider calls, real data or spending.")
    print("Pilot, target, Tags and other native choices use explicit fixture scripts.")
    print("Default GM trait relevance is facilitator-authored. It is not AI comprehension.")
    if args.goal:
        selected[0]["goal"] = args.goal
    definition = json.loads(args.frame.read_text()) if args.frame else None

    def confirm(proposal):
        print("\nEngine accepted the structured proposal:", proposal["verdict"])
        return input("As the original offline Handler controller, confirm it? [y/N] ") == "y"

    rows = []
    for case in selected:
        directory = output / case["id"]
        directory.mkdir(exist_ok=True)
        try:
            row = run_case(
                case,
                protocol=True,
                provider=ManualProvider(directory) if args.interactive else None,
                frame_definition=definition,
                confirm_proposal=confirm if args.interactive else None,
            )
        except Exception as error:
            print(f"Rejected/failed {case['id']}: {type(error).__name__}: {error}")
            print("No live state was used. Each run creates and disposes its synthetic database.")
            return 1
        rows.append(row)
        print(
            case["id"],
            "GM:",
            row["gm_verdict"],
            "native complete:",
            row["native_complete"],
            "fully resolved:",
            row.get("completed_review", {}).get("fully_resolved"),
        )
    summary = {
        "protocol": 2,
        "judgment_setup": "Manual structured GM" if args.interactive else "Annotated fixture GM",
        "statuses": dict(Counter(row["status"] for row in rows)),
        "native_complete": sum(row["native_complete"] for row in rows),
        "external_tokens": 0,
        "external_cost": 0,
    }
    (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    render(rows, output, summary)
    print("Readable results:", output / "index.html")
    print("Databases are temporary; this is a single-attempt adapter console, not a campaign UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
