#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
uv --cache-dir .cache/uv sync --locked --all-groups
