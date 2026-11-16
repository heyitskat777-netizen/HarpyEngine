"""Run the bounded synthetic shadow trial. No credentials, provider calls or live DB."""

import subprocess
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    python = root / ".venv" / "bin" / "python"
    return subprocess.call(
        [
            str(python),
            "-m",
            "pytest",
            "-q",
            "tests/test_director_shadow.py",
            "tests/test_director_conversation.py",
            "tests/rules/test_director_npc_context.py",
            "tests/test_director_observation.py",
            "tests/test_database.py",
            "--junitxml=var/p2-engine-trial.xml",
        ],
        cwd=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
