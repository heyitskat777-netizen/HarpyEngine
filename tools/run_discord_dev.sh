#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -u -m girlframe start --config "${GIRLFRAME_DISCORD_CONFIG:-var/discord-dev/policy.json}"
