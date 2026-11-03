#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ -n "${GIRLFRAME_RUNTIME_SOURCE:-}" ]]; then
  if [[ ! -f "$GIRLFRAME_RUNTIME_SOURCE/girlframe/__main__.py" ]]; then
    echo "Runtime source must contain the tested girlframe package." >&2
    exit 1
  fi
  export PYTHONPATH="$GIRLFRAME_RUNTIME_SOURCE${PYTHONPATH:+:$PYTHONPATH}"
fi
exec .venv/bin/python -u -m girlframe start --config "${GIRLFRAME_DISCORD_CONFIG:-var/discord-dev/policy.json}"
