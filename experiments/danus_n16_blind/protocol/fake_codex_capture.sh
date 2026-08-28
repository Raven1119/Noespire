#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" >"$N16_TEST_ARGS_OUT"
printf '%s\n' "${MATLAS_URL-}" >"$N16_TEST_ENV_OUT"
