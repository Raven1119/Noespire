#!/usr/bin/env bash
set -euo pipefail

if [[ "${1-}" != "exec" ]]; then
  echo "N1.9a blind wrapper permits only 'codex exec'" >&2
  exit 64
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
noespire_root="$(cd "$here/../../.." && pwd)"
real_codex="${N19A_REAL_CODEX_BIN:-$noespire_root/baselines/danus/bin/codex}"

port="${N19A_ALLOWED_LOOPBACK_PORT:-}"
[[ "$port" =~ ^[0-9]+$ ]] && ((port >= 1 && port <= 65535)) || {
  echo "N19A_ALLOWED_LOOPBACK_PORT must be a valid TCP port" >&2
  exit 64
}
verifier_host="127.19.0.1"
expected_verify_url="http://$verifier_host:$port/verify"
if [[ "${DANUS_VERIFY_URL:-}" != "$expected_verify_url" ]]; then
  echo "DANUS_VERIFY_URL must equal $expected_verify_url" >&2
  exit 64
fi

filtered=("exec")
shift
while (($#)); do
  case "$1" in
    --dangerously-bypass-approvals-and-sandbox|--approve-for-me|--search)
      shift
      ;;
    --sandbox|-s|--ask-for-approval|-a)
      (($# >= 2)) || { echo "missing value for $1" >&2; exit 64; }
      shift 2
      ;;
    --enable|--disable)
      (($# >= 2)) || { echo "missing value for $1" >&2; exit 64; }
      case "$2" in
        network_proxy|web_search|browser*|*search*|apps|*plugin*|*agent*|computer_use)
          shift 2
          ;;
        *)
          filtered+=("$1" "$2")
          shift 2
          ;;
      esac
      ;;
    --config|-c)
      (($# >= 2)) || { echo "missing value for $1" >&2; exit 64; }
      case "$2" in
        approval_policy=*|default_permissions=*|sandbox_mode=*|sandbox_workspace_write.*|permissions.*.network.*|features.network_proxy=*|tools.web_search=*|web_search=*|mcp_servers.danus.required=*|mcp_servers.danus.default_tools_approval_mode=*|mcp_servers.danus.disabled_tools=*|mcp_servers.danus.env.MATLAS_URL=*|mcp_servers.danus.env.NO_PROXY=*|mcp_servers.danus.env.no_proxy=*|mcp_servers.danus.env.DANUS_VERIFY_URL=*|agents.enabled=*)
          shift 2
          ;;
        *)
          filtered+=("$1" "$2")
          shift 2
          ;;
      esac
      ;;
    --config=approval_policy=*|--config=default_permissions=*|--config=sandbox_mode=*|--config=sandbox_workspace_write.*|--config=permissions.*.network.*|--config=features.network_proxy=*|--config=tools.web_search=*|--config=web_search=*|--config=mcp_servers.danus.required=*|--config=mcp_servers.danus.default_tools_approval_mode=*|--config=mcp_servers.danus.disabled_tools=*|--config=mcp_servers.danus.env.MATLAS_URL=*|--config=mcp_servers.danus.env.NO_PROXY=*|--config=mcp_servers.danus.env.no_proxy=*|--config=mcp_servers.danus.env.DANUS_VERIFY_URL=*|--config=agents.enabled=*)
      shift
      ;;
    *)
      filtered+=("$1")
      shift
      ;;
  esac
done

role="main_or_strategy"
joined=" ${filtered[*]} "
[[ "$joined" == *'/workers/'* ]] && role="worker"
[[ "$joined" == *'DANUS_ROLE="verifier"'* ]] && role="verifier"

mandatory=(
  --config 'approval_policy="never"'
  --config 'default_permissions="n19a_blind"'
  --config 'permissions.n19a_blind.extends=":workspace"'
  --config permissions.n19a_blind.network.enabled=true
  --config 'permissions.n19a_blind.network.domains={"127.19.0.1"="allow"}'
  --config permissions.n19a_blind.network.allow_local_binding=true
  --config permissions.n19a_blind.network.allow_upstream_proxy=false
  --config permissions.n19a_blind.network.enable_socks5=false
  --config permissions.n19a_blind.network.enable_socks5_udp=false
  --config features.network_proxy=true
  --config 'web_search="disabled"'
  --config tools.web_search=false
  --config mcp_servers.danus.required=true
  --config 'mcp_servers.danus.default_tools_approval_mode="approve"'
  --config 'mcp_servers.danus.disabled_tools=["search_arxiv_theorems"]'
  --config 'mcp_servers.danus.env.MATLAS_URL="http://127.0.0.1:9/n19a-disabled"'
  --config 'mcp_servers.danus.env.NO_PROXY=""'
  --config 'mcp_servers.danus.env.no_proxy=""'
  --config "mcp_servers.danus.env.DANUS_VERIFY_URL=\"$expected_verify_url\""
  --config agents.enabled=false
  --disable browser_use
  --disable browser_use_external
  --disable in_app_browser
  --disable apps
  --disable enable_mcp_apps
  --disable computer_use
  --disable remote_plugin
  --disable plugins
  --disable recommended_plugins
  --disable standalone_web_search
  --disable search_tool
  --disable multi_agent
  --disable multi_agent_mode
)
[[ "${N19A_CAPABILITY_PROBE:-0}" == "1" ]] && mandatory+=(--json)

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY FTP_PROXY http_proxy https_proxy all_proxy ftp_proxy NO_PROXY no_proxy
export MATLAS_URL="http://127.0.0.1:9/n19a-disabled"
export N19A_EFFECTIVE_LOOPBACK_ENDPOINT="$verifier_host:$port"
export N19A_EXTERNAL_SEARCH_SURFACE="cli-disabled:web,arxiv,apps,plugins"

if [[ -n "${N19A_BLIND_WRAPPER_LOG:-}" ]]; then
  printf '%s\tpid=%s\trole=%s\tcwd=%q\tpolicy=n19a-native-sandbox-proxy,deny-default,loopback=%s,web-off,external-mcp-off\tsearch_surface=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$" "$role" "$PWD" "$N19A_EFFECTIVE_LOOPBACK_ENDPOINT" "$N19A_EXTERNAL_SEARCH_SURFACE" >>"$N19A_BLIND_WRAPPER_LOG"
fi

if ((${#filtered[@]} < 2)); then
  exec "$real_codex" "${filtered[0]}" "${mandatory[@]}"
fi

prompt="${filtered[-1]}"
caller_options=("${filtered[@]:1:${#filtered[@]}-2}")
exec "$real_codex" "${filtered[0]}" "${caller_options[@]}" "${mandatory[@]}" "$prompt"
