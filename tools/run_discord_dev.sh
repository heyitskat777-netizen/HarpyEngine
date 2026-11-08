#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ -n "${GIRLFRAME_RUNTIME_SOURCE:-}" ]]; then
  if [[ ! -f "$GIRLFRAME_RUNTIME_SOURCE/girlframe/__main__.py" ]]; then
    echo "Runtime source must contain the tested girlframe package." >&2
    exit 1
  fi
  export PYTHONPATH="$GIRLFRAME_RUNTIME_SOURCE${PYTHONPATH:+:$PYTHONPATH}"
  if [[ -f "$GIRLFRAME_RUNTIME_SOURCE/girlframe/services/m3_access.py" ]]; then
    # A reviewed M3 release must carry its registry beside src/. Missing snapshots
    # fail closed when M3 is enabled; an explicit operator override remains possible.
    export GIRLFRAME_RULES_REGISTRY="${GIRLFRAME_RULES_REGISTRY:-$(dirname -- "$GIRLFRAME_RUNTIME_SOURCE")/rules/registry.json}"
  fi
fi
exec .venv/bin/python -u -m girlframe start --config "${GIRLFRAME_DISCORD_CONFIG:-var/discord-dev/policy.json}"
