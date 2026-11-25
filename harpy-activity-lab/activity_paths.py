"""Trusted local paths shared by the Activity and its synthetic tools."""

import os
from pathlib import Path

ACTIVITY_ROOT = Path(__file__).resolve().parent
CHECKOUT = ACTIVITY_ROOT.parent
RUNTIME = Path(
    os.environ.get(
        "HARPY_ACTIVITY_RUNTIME_ROOT", CHECKOUT / ".sites-runtime" / "harpyengine-mission-lab"
    )
).resolve()


def engine_root(*, trial: bool = False) -> Path:
    """Use the integrated engine, or a deliberately selected external checkout."""
    configured = os.environ.get("HARPY_ACTIVITY_ENGINE_ROOT")
    if configured:
        root = Path(configured).resolve()
    elif (CHECKOUT / "src" / "girlframe").is_dir():
        root = CHECKOUT
    else:
        snapshot = "HarpyEngine-p2-candidate" if trial else "HarpyEngine-release-723955c"
        root = (RUNTIME / snapshot).resolve()
    if not all(
        (root / item).is_file()
        for item in ("src/girlframe/__init__.py", "rules/registry.json", "alembic.ini")
    ):
        raise RuntimeError("Set HARPY_ACTIVITY_ENGINE_ROOT to a complete HarpyEngine checkout.")
    return root
