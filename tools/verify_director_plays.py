"""Audit all registered referrals; optionally run the explicit native workflow packet."""

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from girlframe.engine.m2 import PLAY_IDS
from girlframe.engine.m3_handler_play_state import BASIC, EXTRA
from girlframe.engine.m3_plays import ASSET_IDS, FIXED_IDS, HEAT_IDS, JANUS_ROLL_IDS, ROLL_IDS
from girlframe.services.director_play_catalog import NATIVE_RULES, PlayCatalog

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true", help="Run explicit native gameplay checks")
    args = parser.parse_args()
    catalog = PlayCatalog()
    expected = {
        *PLAY_IDS,
        *ROLL_IDS,
        *FIXED_IDS,
        *HEAT_IDS,
        *ASSET_IDS,
        *JANUS_ROLL_IDS,
        "receive_orders",
        "gorgon_attack",
        "gorgon_collateral",
        "gorgon_warp",
        *("handler_" + key for key, _ in (*BASIC, *EXTRA)),
    }
    missing = sorted(expected - NATIVE_RULES.keys())
    routes = catalog.all()
    output = ROOT / "var/director-play-coverage"
    output.mkdir(parents=True, exist_ok=True)
    checks = [
        line.strip()
        for line in (ROOT / "tools/fixtures/director_play_native_checks.txt")
        .read_text()
        .splitlines()
        if line.strip() and not line.startswith("#")
    ]
    summary = {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "registry_sha256": catalog.digest,
        "native_identifiers": len(expected),
        "missing_native_routes": missing,
        "inventoried_rules": len(catalog.registry.entries),
        "referral_routes": len(routes),
        "adapter_counts": dict(Counter(r.adapter for r in routes)),
        "registered_play_headings": sum(e.kind == "play" for e in catalog.registry.entries),
        "scope": "Referrals/review cover the source inventory; only five ordinary native Plays "
        "have structured outcome adapters. Review does not implement missing rules.",
        "native_test_selection": checks,
        "native_test_result": "not_run",
        "external_tokens": 0,
        "external_cost": 0,
        "routes": [r.model_dump(mode="json") for r in routes],
    }
    code = int(bool(missing))
    if args.native and not code:
        code = subprocess.call(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *checks,
                "--junitxml=" + str(output / "native.xml"),
            ],
            cwd=ROOT,
        )
        suite = ET.parse(output / "native.xml").getroot().find("testsuite")
        summary["native_test_result"] = {
            k: suite.attrib[k] for k in ("tests", "failures", "errors", "skipped", "time")
        }
    changed = set(
        subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).splitlines()
    )
    changed.update(
        subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
        ).splitlines()
    )
    summary["changed_file_sha256"] = {
        p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        for p in sorted(changed)
        if (ROOT / p).is_file()
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in ("routes", "native_test_selection", "changed_file_sha256")
            },
            indent=2,
        )
    )
    print("Full catalog and check evidence:", output / "summary.json")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
