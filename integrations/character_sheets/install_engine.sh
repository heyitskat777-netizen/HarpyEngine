#!/usr/bin/env bash
set -euo pipefail

kit_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -d "$kit_root/engine" || ! -d "$kit_root/engine_source" ]]; then
  echo 'Run the install-engine.sh from the extracted character-sheet package.' >&2
  exit 1
fi
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"'
python3 -m venv "$kit_root/.bootstrap"
"$kit_root/.bootstrap/bin/python" -m pip install uv==0.12.23
UV_PROJECT_ENVIRONMENT="$kit_root/.venv" \
  "$kit_root/.bootstrap/bin/uv" sync --project "$kit_root/engine_source" --locked --no-dev
echo 'Engine and locked runtime dependencies installed. No database, token, campaign or bot was started.'
echo 'See INTEGRATION_HANDOFF.md for authorized store initialization and native registration.'
