#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
python_bin="$root/baselines/danus/runtime/venv/bin/python"
fake_backend="$root/baselines/danus/danus/verify/tests/fake_codex.py"

exec "$python_bin" "$fake_backend" "$@"
