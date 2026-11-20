"""Run supplied Activity adapters against this engine using disposable offline stores.

The source-only bundle omits artwork and the browser SDK. Empty synthetic stand-ins
allow Python adapter checks; they provide no browser, artwork or Discord evidence.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "integrations/activity"


def prepare(source: Path, output: Path, *, p2_routes: bool = False) -> Path:
    manifest = json.loads((source / "SOURCE-MANIFEST.json").read_text())
    for name, expected in manifest["included_files"].items():
        path = (source / name).resolve()
        if not path.is_relative_to(source.resolve()):
            raise ValueError("Manifest path escapes the supplied source directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Source manifest mismatch: " + name)
    output.mkdir(parents=True, exist_ok=False)
    app = output / "app"
    lab = app / "harpy-activity-lab"
    shutil.copytree(source / "girlframe-campaign-ui/app/harpy-activity-lab", lab)
    runtime = app / ".sites-runtime/harpyengine-mission-lab"
    runtime.mkdir(parents=True)
    (runtime / "HarpyEngine-playtest").symlink_to(ROOT, target_is_directory=True)
    (lab / "artwork").mkdir(exist_ok=True)
    (lab / "artwork/catalog.json").write_text("[]\n")
    (runtime / "discord-sdk").mkdir()
    (runtime / "discord-sdk/embedded-app.js").write_text("// Python adapter tests only.\n")
    for adapter in ADAPTERS.glob("*.py"):
        shutil.copyfile(adapter, lab / adapter.name)
    if p2_routes:
        shutil.copyfile(ADAPTERS / "p2-desk.js", lab / "p2-desk.js")
        for test_path in (ADAPTERS / "tests").glob("test_*.py"):
            shutil.copyfile(test_path, lab / test_path.name)
        for patch in (
            "p2_lab_routes.patch",
            "campaign_difficulty_ui.patch",
            "portrayal_sheet_ui.patch",
        ):
            subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "-i", str(ADAPTERS / patch)],
                cwd=lab,
                check=True,
            )
    metadata = {
        "engine_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "mirror_base": manifest["engine_base_commit"],
        "manifest_files_verified": len(manifest["included_files"]),
        "engine_python_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src").rglob("*.py"))
        },
        "adapter_overrides": [p.name for p in sorted(ADAPTERS.glob("*.py"))],
        "p2_routes": p2_routes,
        "excluded": ["test_artwork_activity.py", "browser SDK", "live Discord", "artwork"],
    }
    (output / "source.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return lab


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Extracted handoff root")
    parser.add_argument("--output", required=True, type=Path, help="New disposable directory")
    parser.add_argument("--test", action="append", help="Optional explicit test module")
    parser.add_argument("--p2-routes", action="store_true", help="Apply the P2 Activity overlay")
    parser.add_argument(
        "--prepare-only", action="store_true", help="Prepare without running pytest"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "var"):
        parser.error("Keep disposable campaign stores under this checkout's ignored var directory")
    lab = prepare(args.source.resolve(), output, p2_routes=args.p2_routes)
    if args.prepare_only:
        print("Prepared disposable lab:", lab)
        return 0
    tests = args.test or [
        p.name for p in sorted(lab.glob("test_*.py")) if p.name != "test_artwork_activity.py"
    ]
    if any(Path(p).name != p or not p.startswith("test_") or not p.endswith(".py") for p in tests):
        parser.error("Select test module names, without paths")
    env = os.environ.copy()
    # Never inherit a real campaign database or tokens into a synthetic subprocess.
    for name in list(env):
        if name.startswith(("GIRLFRAME_", "DISCORD_")) or name in ("DiscordBot", "OPENAI_API_KEY"):
            env.pop(name)
    env["PYTHONPATH"] = os.pathsep.join(str(ROOT / p) for p in ("src", "tests", "tests/rules"))
    env["GIRLFRAME_RULES_REGISTRY"] = str(ROOT / "rules/registry.json")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests, "--junitxml=" + str(output / "pytest.xml")],
        cwd=lab,
        env=env,
        check=False,
    )
    print("Python Activity adapter result:", result.returncode, "Evidence:", output)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
