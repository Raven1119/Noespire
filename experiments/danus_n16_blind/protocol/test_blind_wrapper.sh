#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

fake="$here/fake_codex_capture.sh"
args_out="$tmp/args.txt"
env_out="$tmp/env.txt"

N16_REAL_CODEX_BIN="$fake" \
N16_TEST_ARGS_OUT="$args_out" \
N16_TEST_ENV_OUT="$env_out" \
N16_CAPABILITY_PROBE=1 \
  "$here/codex_blind_wrapper.sh" exec \
    --dangerously-bypass-approvals-and-sandbox \
    --config tools.web_search=true \
    --config mcp_servers.danus.default_tools_approval_mode=prompt \
    --config 'mcp_servers.danus.disabled_tools=[]' \
    --config 'mcp_servers.danus.env.MATLAS_URL="https://leansearch.net/thm/search"' \
    --config agents.enabled=true \
    --config mcp_servers.danus.required=false \
    --config default_permissions=unsafe \
    --config 'permissions.n16_blind={extends=":danger-full-access"}' \
    --sandbox danger-full-access \
    --search \
    CAPABILITY_PROBE

grep -Fx -- 'exec' "$args_out" >/dev/null
grep -Fx -- 'approval_policy=never' "$args_out" >/dev/null
grep -Fx -- 'default_permissions=n16_blind' "$args_out" >/dev/null
grep -E -- '^permissions\.n16_blind=\{extends=":workspace",filesystem=\{.*danus_n16_blind.*="deny".*\},network=\{enabled=false\}\}$' "$args_out" >/dev/null
if grep -F -- 'verify-runs"="write"' "$args_out"; then
  echo "non-verifier unexpectedly received verifier output write access" >&2
  exit 1
fi
grep -Fx -- 'tools.web_search=false' "$args_out" >/dev/null
grep -Fx -- 'web_search=disabled' "$args_out" >/dev/null
grep -Fx -- 'mcp_servers.danus.default_tools_approval_mode=approve' "$args_out" >/dev/null
grep -Fx -- 'mcp_servers.danus.required=true' "$args_out" >/dev/null
grep -Fx -- 'mcp_servers.danus.disabled_tools=["search_arxiv_theorems"]' "$args_out" >/dev/null
grep -Fx -- 'mcp_servers.danus.env.MATLAS_URL="http://127.0.0.1:9/n16-disabled"' "$args_out" >/dev/null
grep -Fx -- 'agents.enabled=false' "$args_out" >/dev/null
grep -Fx -- 'agents.max_concurrent_threads_per_session=1' "$args_out" >/dev/null
grep -Fx -- '--disable' "$args_out" >/dev/null
grep -Fx -- 'browser_use' "$args_out" >/dev/null
grep -Fx -- 'plugins' "$args_out" >/dev/null
grep -Fx -- 'multi_agent_mode' "$args_out" >/dev/null
grep -Fx -- 'CAPABILITY_PROBE' "$args_out" >/dev/null
grep -Fx -- '--json' "$args_out" >/dev/null

if grep -En -- 'dangerously-bypass|danger-full-access|tools.web_search=true|default_tools_approval_mode=prompt|required=false|default_permissions=unsafe|disabled_tools=\[\]|leansearch.net|agents.enabled=true|^--search$' "$args_out"; then
  echo "forbidden capability survived wrapper" >&2
  exit 1
fi

grep -Fx -- 'http://127.0.0.1:9/n16-disabled' "$env_out" >/dev/null

verifier_args_out="$tmp/verifier-args.txt"
verifier_env_out="$tmp/verifier-env.txt"
N16_REAL_CODEX_BIN="$fake" \
N16_TEST_ARGS_OUT="$verifier_args_out" \
N16_TEST_ENV_OUT="$verifier_env_out" \
  "$here/codex_blind_wrapper.sh" exec \
    --config 'mcp_servers.danus={env={DANUS_ROLE="verifier"}}' \
    VERIFIER_CAPABILITY_PROBE
grep -E -- '^permissions\.n16_blind=\{extends=":workspace",filesystem=\{.*danus_n16_blind.*="deny",.*verify-runs.*="write".*\},network=\{enabled=false\}\}$' "$verifier_args_out" >/dev/null
upstream_line="$(grep -n -F -- 'mcp_servers.danus={env={DANUS_ROLE="verifier"}}' "$verifier_args_out" | cut -d: -f1)"
disabled_line="$(grep -n -F -- 'mcp_servers.danus.disabled_tools=["search_arxiv_theorems"]' "$verifier_args_out" | cut -d: -f1)"
[[ "$disabled_line" -gt "$upstream_line" ]] || {
  echo "mandatory DANUS tool restriction does not override the upstream table" >&2
  exit 1
}
[[ "$(tail -n 1 "$verifier_args_out")" == "VERIFIER_CAPABILITY_PROBE" ]] || {
  echo "mandatory options were placed after the final prompt" >&2
  exit 1
}

if "$here/codex_blind_wrapper.sh" mcp list >/dev/null 2>&1; then
  echo "non-exec subcommand was not rejected" >&2
  exit 1
fi

echo "PASS: blind wrapper enforces the frozen external policy"
