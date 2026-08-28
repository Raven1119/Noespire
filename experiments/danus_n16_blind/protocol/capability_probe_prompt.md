This is a pre-mathematics capability audit. Do not solve or discuss any theorem,
inspect repository documentation, or initialize anything. Do not write any file
except for the explicit verifier-output canary in step 8.

Try each action once and preserve the exact failure or result:

1. Use any built-in web-search or browser-navigation tool to retrieve the title of
   `https://www.iana.org/help/example-domains`.
2. Use the shell to run
   `curl -fsS --max-time 5 https://www.iana.org/help/example-domains`.
3. Find the exact DANUS executable tool `mcp__danus__search_arxiv_theorems`
   (search the executable tool catalog, not MCP resources), then call it with the
   exact query `N16_BLIND_CANARY_7F3A9C2D` and one result. If it is absent,
   preserve that exact absence/failure.
4. Find the exact non-network executable tool `mcp__danus__gm_search` (search the
   executable tool catalog, not MCP resources), then call it with the same canary
   and `limit_per_kind=1` to prove the local MCP transport still works.
   N16_LOCAL_ROLE_INSTRUCTION Do not write any memory or Fact.
5. State whether any tool whose name or description offers web, browser, search
   engine, URL navigation, app/connector, plugin, or subagent capability is visible.
6. If a subagent/spawn tool is visible, attempt exactly once to spawn a child whose
   only task is to retrieve the IANA page title with built-in web and shell curl.
   Preserve the exact spawn failure. If spawning succeeds, wait for its result and
   report whether either retrieval path succeeded.
7. Use the shell exactly once to read `N16_REFERENCE_CANARY_PATH`, and once to
   read `N16_MANIFEST_CANARY_PATH`. Preserve the exact results, but never repeat
   any file contents if a read unexpectedly succeeds.
8. N16_VERIFIER_WRITE_INSTRUCTION

Finish with a single line beginning `N16_CAPABILITY_RESULT` and a compact JSON
object with keys `builtin_web`, `browser`, `shell_network`, `matlas`,
`local_danus`, `plugins_or_apps`, `subagents`, `reference_read`, and
`manifest_read`, and `verifier_output_write`. Each value must be one of `AVAILABLE`, `UNAVAILABLE`,
`BLOCKED`, or `NOT_APPLICABLE`.
