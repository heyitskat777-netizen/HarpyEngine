"""Check tracked/publishable files, original package integrity, and obvious secrets.

This is a limited local check, not a comprehensive credential or security audit.
Ignored local files are not read. Filenames are reported; matched values never are.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "GIRLFRAME_Discord_Codex_Handoff_v0.2"
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"mfa\.[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}"),
]


def inspect_file(path: Path, data: bytes) -> list[str]:
    errors = []
    name = path.name.lower()
    if (
        path.suffix.lower() in {".pdf", ".zip", ".db", ".sqlite", ".sqlite3"}
        or (name.startswith(".env") and name != ".env.example")
        or name == "campaign.json"
        or "private-reference" in path.parts
    ):
        errors.append(f"Forbidden publishable file: {path}")
    content = data.decode("utf-8", errors="replace")
    if any(pattern.search(content) for pattern in PATTERNS):
        errors.append(f"Possible credential in: {path}")
    return errors


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    paths = sorted(set(result.stdout.decode().split("\0")) - {""})
    errors = []
    for name in paths:
        path = ROOT / name
        if path.is_symlink():
            errors.append(f"Publishable symlink needs manual review: {name}")
        elif path.is_file():
            errors.extend(inspect_file(Path(name), path.read_bytes()))
    manifest = json.loads((HANDOFF / "MANIFEST_SHA256.json").read_text())
    for entry in manifest["files"]:
        data = (HANDOFF / entry["path"]).read_bytes()
        if len(data) != entry["size_bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            errors.append(f"Original handoff differs from manifest: {entry['path']}")
    for error in errors:
        print(error)
    print(
        f"Repository check: {len(paths)} publishable files; "
        f"{len(manifest['files'])} manifest entries; {len(errors)} findings."
    )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
