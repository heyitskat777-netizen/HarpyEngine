"""Build a sanitized, source-pinned character-sheet integration ZIP and engine wheel."""

import argparse
import ast
import hashlib
import io
import json
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    "src",
    "rules",
    "migrations",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "README.md",
    "tools/build_character_sheet_package.py",
    "integrations/character_sheets",
    "docs/work_orders/P1_CHARACTER_SHEET_EXCHANGE.md",
)


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ci-evidence", type=Path)
    args = parser.parse_args()
    sha = (
        git("rev-parse", "--verify", "--end-of-options", args.source_ref + "^{commit}")
        .decode()
        .strip()
    )
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = out / ("build-source-" + sha[:7])
    source.mkdir(exist_ok=False)
    archive_bytes = git("archive", "--format=tar", sha, *SOURCE_PATHS)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
        archive.extractall(source, filter="data")
    tree = ast.parse((source / "src/girlframe/__init__.py").read_text())
    version = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    )
    wheels = out / ("wheels-" + sha[:7])
    build_env = os.environ.copy()
    build_env["SOURCE_DATE_EPOCH"] = git("show", "-s", "--format=%ct", sha).decode().strip()
    subprocess.run(
        ["uv", "build", str(source), "--wheel", "--out-dir", str(wheels)], check=True, env=build_env
    )
    (wheel,) = wheels.glob("*.whl")
    files: dict[str, bytes] = {"engine/" + wheel.name: wheel.read_bytes()}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(source).as_posix()
        if relative.startswith((".venv/", "dist/", "build/")) or ".egg-info" in relative:
            continue
        if path.suffix.lower() in {
            ".db",
            ".sqlite",
            ".sqlite3",
            ".pdf",
            ".zip",
        } or path.name.startswith(".env"):
            raise SystemExit("Forbidden package file: " + relative)
        files["engine_source/" + relative] = path.read_bytes()
    sdk = source / "integrations/character_sheets"
    for path in sorted(sdk.iterdir()):
        if path.is_file():
            files["campaign-ui/" + path.name] = path.read_bytes()
    for name in ("INTEGRATION_HANDOFF.md", "python_adapter_example.py"):
        files[name] = (sdk / name).read_bytes()
    files["install-engine.sh"] = (sdk / "install_engine.sh").read_bytes()
    files["README.md"] = f"""# HarpyEngine character sheets v{version}

Source: `{sha}`. Read `INTEGRATION_HANDOFF.md` first.

- Campaign UI: use the schemas, catalog and dependency-free browser codec under
  `campaign-ui/`; generate a character-draft JSON download.
- HarpyEngine Discord: `/character import document:<file>` previews and confirms
  an inactive creation draft. `/character export` downloads templates, snapshots
  or printable HTML. Existing review/coordination/activation remain explicit.
- Another Python Discord app: Python3.12; run `bash install-engine.sh` (creates
  a local venv and installs the included engine source with locked runtime dependencies;
  network access may be needed for dependencies). No bot/database is started.
- Offline codec example after installation:
  `.venv/bin/python python_adapter_example.py campaign-ui/example-mockingbird-janus-b.json`
- Engine source and locked dependencies are included under `engine_source/`.
  To initialize a NEW isolated engine database, set its GIRLFRAME_DATABASE_URL,
  use the included Alembic migrations and the actual authorized campaign policy.
  Point GIRLFRAME_RULES_REGISTRY at `engine_source/rules/registry.json` when using
  runtime services outside an existing checkout. Do not copy a real campaign DB
  or approval into this package, or start a competing authoritative campaign.

Printable HTML is scriptless; browser Print → Save as PDF supplies PDF output.
JSON files carry data, not ownership, accepted Bonds, live resources or consent.
Current-sheet snapshots are read-only and cannot be restored through draft import.
No HTTP/OAuth server, PDF/OCR importer, real campaign data, credentials, private
engine archive or official PDF is included. Full rules/human acceptance is separate.
""".encode()
    evidence = None
    if args.ci_evidence:
        evidence = json.loads(args.ci_evidence.read_text())
        if evidence.get("headSha") != sha or evidence.get("conclusion") != "success":
            raise SystemExit("CI evidence must be successful for the exact source commit")
        files["EVIDENCE.json"] = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode()
    manifest = {
        "package": "harpyengine-character-sheets",
        "version": version,
        "source_commit": sha,
        "draft_schema_version": 1,
        "snapshot_schema_version": 1,
        "rules_status": "RULES_SUBSET",
        "ci": evidence,
        "files": [
            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())
        ],
    }
    files["MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    destination = out / f"HarpyEngine_Character_Sheets_v{version}.zip"
    with zipfile.ZipFile(
        destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if name == "install-engine.sh" else 0o644) << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(digest + "  " + destination.name + "\n")
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for entry in manifest["files"]:
            assert hashlib.sha256(archive.read(entry["path"])).hexdigest() == entry["sha256"]
    print(
        json.dumps(
            {
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "sha256": digest,
                "source_commit": sha,
                "files": len(files),
            }
        )
    )


if __name__ == "__main__":
    main()
