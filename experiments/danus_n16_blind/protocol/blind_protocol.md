# N1.6 Blind DANUS Protocol

Status: **PRE-RUN FROZEN**

## Experimental boundary

This protocol changes only the external Codex execution/tool policy around frozen DANUS. It does not modify DANUS source, worker/verifier/strategy prompts, retrieval or memory algorithms, Fact Graph semantics, orchestration, or proof strategy.

The worker receives only the exact bytes of one file from `problems/`. Source identity, URLs, and evaluator proof text remain under `reference/` and are never copied into a DANUS project, task, memory, Fact, verifier request, or strategy context.

## Enforced execution policy

Every DANUS-launched `codex exec` resolves through `protocol/codex_blind_wrapper.sh`. The wrapper strips upstream `--dangerously-bypass-approvals-and-sandbox` and any conflicting caller overrides, then mandates:

- `approval_policy="never"`;
- a custom `n16_blind` permission profile extending `:workspace`, with network disabled and the entire N1.6 experiment-control directory denied for reads;
- top-level `web_search="disabled"` plus the legacy web flag disabled;
- browser, app/connector, plugin, search, and native multi-agent features disabled;
- the DANUS MCP server required and locally auto-approved;
- `search_arxiv_theorems` removed from the DANUS MCP tool surface;
- `MATLAS_URL` redirected to a closed loopback endpoint as defense in depth;
- authoring MCP servers disabled for this experiment.

The directory-level deny is intentional. It hides both private references and source-bearing manifests. A recursive per-file glob on Windows-mounted WSL storage caused the sandbox helper to fail while materializing individual masks. Denying the directory itself produces `Permission denied` inside every role without changing NTFS ACLs, touching `.lake/.git` caches, or invoking the Windows ACL helper.

## Pre-mathematics capability gate

Canonical passing evidence: `protocol/evidence/capability_probe_20260828T152943Z/`.

The probe exercised the real frozen worker launcher, verifier launcher, and strategy/main launcher. In every role:

- no built-in web, browser, app/plugin, Matlas, or subagent call occurred;
- `curl` failed at DNS resolution;
- reading both `reference/capability_canary.txt` and the source-bearing problem manifest returned `Permission denied`; neither private marker appeared in the trace;
- the worker and strategy/main DANUS local `gm_search` call completed successfully;
- verifier local search was not applicable because the frozen verifier role intentionally exposes only the now-disabled external search tool.

`summary.json` reports `automatic_gate: PASS`. Earlier probe directories preserve failed protocol designs, including the initial external-search leak and the invalid recursive-deny helper failure. They are diagnostic evidence and are not formal math runs.

## Formal-run integrity rules

- Exactly one independent run per frozen problem, in manifest order.
- Seven upstream workers (`high:3,xhigh:4`), one round, no retry, best-of-N, replacement, manual Fact, prompt repair, guidance, or budget change.
- A dedicated stateless verifier service is launched for each run under the same wrapper, on an isolated loopback port, then terminated after capture.
- A system fault is recorded as `SYSTEM_INVALID_RUN`; it is never silently retried or counted as proof-search failure.
- The formal wrapper policy and problem byte hash are checked before each run.
- The target rule is the lexicographically smallest accepted Fact whose whitespace-normalized statement equals the frozen problem bytes. If none exists, the run is unsolved.

## Leakage audit

After all runs, every captured worker/verifier/tool trace is scanned for:

- web/browser/search/tool calls or external URL retrieval;
- theorem/problem/source-name lookup attempts;
- any `reference/` read attempt or capability-canary secret;
- suspicious overlap with the private reference proof text.

Only `BLIND_INTEGRITY_PASS` runs may contribute to the N2 gate.
