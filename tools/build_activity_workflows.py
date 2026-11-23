"""Build a conservative source/branch matrix, without treating inventory as mechanics."""

import argparse
import ast
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def public_api(path: Path) -> str:
    names = []
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ClassDef):
            names.extend(
                node.name + "." + method.name
                for method in node.body
                if isinstance(method, ast.FunctionDef) and not method.name.startswith("_")
            )
        elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            names.append(node.name)
    return "; ".join(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/integration")
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    registry = json.loads((ROOT / "rules/registry.json").read_text())
    types = json.loads((ROOT / "docs/acceptance/p1_type_coverage.json").read_text())["rows"]
    curated = json.loads((ROOT / "integrations/activity/workflows.json").read_text())["workflows"]
    services = {p: p.read_text() for p in sorted((ROOT / "src/girlframe/services").glob("*.py"))}
    api = {p: public_api(p) for p in services}
    rows = []
    for entry in registry["entries"]:
        # Package headings and references remain in the canonical inventory. They
        # are not invented consumer workflows in this matrix.
        if entry["kind"] in ("playbook", "reference"):
            continue
        rule = entry["id"]
        contract = entry["contract"]
        source = entry["source"]
        family = next((x for x in types if rule.startswith(x["registry_prefix"])), None)
        direct = [p for p, text in services.items() if '"' + rule + '"' in text]
        candidates = direct or [
            ROOT / name
            for name in (family["code"] if family else [])
            if name.startswith("src/girlframe/services/")
        ]
        # Direct references and family indexes locate source for review. Neither
        # proves eligibility, effects, a consumer, or an applicable test pass.
        native = "; ".join(str(p.relative_to(ROOT)) for p in candidates)
        projection = " | ".join(api[p] for p in candidates if p in api)
        tiers = contract["tier_options"] if contract else {"branch audit pending": []}
        for branch, options in tiers.items():
            rows.append(
                {
                    "rule_id": rule,
                    "title": entry["title"],
                    "source": (
                        f"{source['document']}: printed {source['printed_page']}, "
                        f"PDF {source['pdf_page']}"
                    ),
                    "branch": branch,
                    "status": "Evidence pending",
                    "prerequisites": (
                        contract["actor_type"] + " | " + "; ".join(contract["pre_roll_sources"])
                        if contract
                        else "Actor/body/source prerequisites need native branch review"
                    ),
                    "native_command": native
                    or "No source mapped; inspect the rule before claiming missing implementation",
                    "projection": projection
                    or "Native query/target/owned-choice projection audit pending",
                    "owners": contract["choice_ownership"]
                    if contract
                    else "Per-branch original controller/Handler ownership audit pending",
                    "completion": (
                        "; ".join(
                            options
                            + contract["post_roll_effects"]
                            + contract["mandatory_followups"]
                        )
                        if contract
                        else "Actual effect and required continuation closure audit pending"
                    ),
                    "activity_dependency": (
                        "Source-specific entry, targets and original-work reopen; "
                        "see Activity coverage and curated ports"
                    ),
                    "test_evidence": "; ".join(entry["test_evidence"]),
                    "gate": (
                        f"module={entry['module']}; implementation={entry['implementation']}; "
                        f"independent review={entry['independent_review']}. "
                        "Inspect actual service gate; inventory is not a release decision"
                    ),
                    "evidence_limit": (
                        "Source index / contract only. Test references do not prove "
                        "applicable branch results; retain pending until reviewed"
                    ),
                }
            )
    entries = {entry["id"]: entry for entry in registry["entries"]}
    for item in curated:
        entry = entries.get(item["rule_id"])
        anchor = entry["source"] if entry else None
        rows.append(
            item
            | {
                "title": entry["title"] if entry else "Owner-confirmed character reset",
                "source": (
                    f"{anchor['document']}: printed {anchor['printed_page']}, "
                    f"PDF {anchor['pdf_page']}"
                    if anchor
                    else "Owner integration requirement; not a printed rule"
                ),
                "evidence_limit": (
                    "Curated ordinary branch; release gate, tested scope and "
                    "unresolved evidence remain explicit"
                ),
            }
        )
    fields = [
        "rule_id",
        "title",
        "source",
        "branch",
        "status",
        "prerequisites",
        "native_command",
        "projection",
        "owners",
        "completion",
        "activity_dependency",
        "test_evidence",
        "gate",
        "evidence_limit",
    ]
    with (output / "ACTIVITY_WORKFLOWS.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (output / "ACTIVITY_READY_PORTS.json").write_text(json.dumps(curated, indent=2) + "\n")
    print(f"{len(rows)} rows; {len(curated)} curated branches. Unreviewed inventory stays pending.")


if __name__ == "__main__":
    main()
