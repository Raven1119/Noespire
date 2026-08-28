#!/usr/bin/env bash
set -euo pipefail

if [[ "${1-}" != "exec" ]]; then
  echo "N1.6 blind wrapper permits only 'codex exec'" >&2
  exit 64
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
noespire_root="$(cd "$here/../../.." && pwd)"
real_codex="${N16_REAL_CODEX_BIN:-$noespire_root/baselines/danus/bin/codex}"
experiment_control_dir="$noespire_root/experiments/danus_n16_blind"
verify_runs_dir="$noespire_root/baselines/danus/runtime/verify-runs"

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
    --config|-c)
      (($# >= 2)) || { echo "missing value for $1" >&2; exit 64; }
      case "$2" in
        tools.web_search=*|web_search=*|sandbox_workspace_write.network_access=*|approval_policy=*|sandbox_mode=*|default_permissions=*|permissions.n16_blind=*|agents.enabled=*|mcp_servers.danus.required=*|mcp_servers.danus.default_tools_approval_mode=*|mcp_servers.danus.disabled_tools=*|mcp_servers.danus.env.MATLAS_URL=*)
          shift 2
          ;;
        *)
          filtered+=("$1" "$2")
          shift 2
          ;;
      esac
      ;;
    --config=tools.web_search=*|--config=web_search=*|--config=sandbox_workspace_write.network_access=*|--config=approval_policy=*|--config=sandbox_mode=*|--config=default_permissions=*|--config=permissions.n16_blind=*|--config=agents.enabled=*|--config=mcp_servers.danus.required=*|--config=mcp_servers.danus.default_tools_approval_mode=*|--config=mcp_servers.danus.disabled_tools=*|--config=mcp_servers.danus.env.MATLAS_URL=*)
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

filesystem_config="\"$experiment_control_dir\"=\"deny\""
write_scope="workspace-only"
if [[ "$role" == "verifier" ]]; then
  filesystem_config+=",\"$verify_runs_dir\"=\"write\""
  write_scope="verifier-output-write"
fi
permission_config="permissions.n16_blind={extends=\":workspace\",filesystem={$filesystem_config},network={enabled=false}}"

mandatory=(
  --config approval_policy="never"
  --config default_permissions="n16_blind"
  --config "$permission_config"
  --config web_search="disabled"
  --config tools.web_search=false
  --config mcp_servers.danus.required=true
  --config mcp_servers.danus.default_tools_approval_mode="approve"
  --config 'mcp_servers.danus.disabled_tools=["search_arxiv_theorems"]'
  --config 'mcp_servers.danus.env.MATLAS_URL="http://127.0.0.1:9/n16-disabled"'
  --config agents.enabled=false
  --config agents.max_concurrent_threads_per_session=1
  --disable browser_use
  --disable browser_use_external
  --disable browser_use_full_cdp_access
  --disable in_app_browser
  --disable apps
  --disable enable_mcp_apps
  --disable computer_use
  --disable remote_plugin
  --disable plugins
  --disable recommended_plugins
  --disable skill_search
  --disable standalone_web_search
  --disable search_tool
  --disable multi_agent
  --disable multi_agent_mode
  --disable multi_agent_v2
  --disable collaboration_modes
  --disable enable_fanout
)

if [[ "${N16_DISABLE_AUTHORING_MCP:-0}" == "1" ]]; then
  mandatory+=(
    --config mcp_servers.write-paper.enabled=false
    --config mcp_servers.human-summary.enabled=false
  )
fi

[[ "${N16_CAPABILITY_PROBE:-0}" == "1" ]] && mandatory+=(--json)

export MATLAS_URL="http://127.0.0.1:9/n16-disabled"

if [[ -n "${N16_BLIND_WRAPPER_LOG:-}" ]]; then
  printf '%s\tpid=%s\trole=%s\tcwd=%q\tpolicy=n16-blind-profile,never,control-dir-deny,%s,danus-mcp-approved,network-off,web-off,search-mcp-disabled,matlas-disabled,browser-off,plugins-off,subagents-off\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$" "$role" "$PWD" "$write_scope" >>"$N16_BLIND_WRAPPER_LOG"
fi

if ((${#filtered[@]} < 2)); then
  exec "$real_codex" "${filtered[0]}" "${mandatory[@]}"
fi

# DANUS appends a role-specific whole-table MCP config. Put mandatory field
# overrides after every caller option but before the final prompt so the whole
# table cannot restore disabled retrieval or interactive approvals.
prompt="${filtered[-1]}"
caller_options=("${filtered[@]:1:${#filtered[@]}-2}")
exec "$real_codex" "${filtered[0]}" "${caller_options[@]}" "${mandatory[@]}" "$prompt"
