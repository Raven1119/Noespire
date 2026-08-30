#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
codex_bin="${N19A_REAL_CODEX_BIN:-$root/baselines/danus/bin/codex}"
port="${N19A_SMOKE_PORT:-43123}"
temp_dir="$(mktemp -d)"
server_pid=""

cleanup() {
  [[ -z "$server_pid" ]] || kill "$server_pid" 2>/dev/null || true
  rm -rf -- "$temp_dir"
}
trap cleanup EXIT

python3 -m http.server "$port" --bind 127.19.0.1 --directory "$temp_dir" \
  >"$temp_dir/server.stdout.log" 2>"$temp_dir/server.stderr.log" &
server_pid="$!"
for _ in {1..50}; do
  curl -fsS --max-time 1 "http://127.19.0.1:$port/" >/dev/null 2>&1 && break
  sleep 0.1
done
curl -fsS --max-time 1 "http://127.19.0.1:$port/" >/dev/null

probe=(env NO_PROXY= no_proxy= python3 -c "from urllib.request import urlopen; response=urlopen('http://127.19.0.1:$port/', timeout=3); print('N19A_LOOPBACK_OK', response.status)")

"$codex_bin" sandbox \
  -C "$root" \
  -c 'permissions.n19a_blind.extends=":workspace"' \
  -c permissions.n19a_blind.network.enabled=true \
  -c 'permissions.n19a_blind.network.domains={"127.19.0.1"="allow"}' \
  -c permissions.n19a_blind.network.allow_local_binding=true \
  -c permissions.n19a_blind.network.allow_upstream_proxy=false \
  -c permissions.n19a_blind.network.enable_socks5=false \
  -c permissions.n19a_blind.network.enable_socks5_udp=false \
  -c features.network_proxy=true \
  -P n19a_blind \
  "${probe[@]}"
