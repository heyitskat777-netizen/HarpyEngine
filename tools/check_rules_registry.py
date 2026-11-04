"""Validate the additive source inventory without reading private reference files."""

import json
from pathlib import Path

from girlframe.engine.rules_registry import Registry


def main() -> int:
    registry = Registry.model_validate_json(
        (Path(__file__).resolve().parents[1] / "rules/registry.json").read_text()
    )
    print(json.dumps(registry.summary(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
