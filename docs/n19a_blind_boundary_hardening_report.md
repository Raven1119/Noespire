# N1.9a Blind Boundary Hardening

## Previous Failure

- N1.8 issue: three Parallel-7 cells were excluded by the frozen audit. Two traces emitted completed-search event labels while the tool was unavailable and returned no result; a third worker attempted an exact-problem Bohrium `curl`, but DNS failed and no bytes were retrieved.
- root cause: the N1.8 protocol treated search intent and a mechanically blocked outbound attempt as integrity failures, while its negative controls established only that exposed requests happened to fail. It did not separately prove a deny-by-default OS/sandbox capability boundary for every worker and verifier process.

## Boundary Design

- deny mechanism: every proof-relevant `codex exec` is forced through `protocol/codex_blind_wrapper.sh`. The wrapper fixes `approval_policy=never`, selects a workspace sandbox profile, enables Codex's managed network proxy with a single allowed host, disables upstream and SOCKS proxying, strips caller attempts to override those settings, and disables hosted web/search, browser, apps/plugins, computer use, subagents, and external search MCP tools. This follows the Codex permissions model's requirement to combine a sandbox profile with its network proxy; the upstream documentation also states that network domain patterns are host-based and normalized without ports: <https://learn.chatgpt.com/docs/permissions>.
- loopback allowlist: the only proxy host allowlist entry is the dedicated loopback address `127.19.0.1`. The wrapper additionally requires an exact `DANUS_VERIFY_URL=http://127.19.0.1:<validated-port>/verify`. Because the public Codex domain policy cannot bind an allow rule to a port, the verifier is the only service bound to that dedicated address; a same-port decoy bound to ordinary `127.0.0.1` proves that generic localhost is not exposed. The DANUS MCP remains local stdio rather than an external endpoint.
- worker policy: the unchanged DANUS worker launch path invokes the wrapper, receives only the dedicated verifier endpoint, and cannot request approvals or re-enable network/search capabilities. Its required local `gm_search` MCP call remains usable.
- verifier policy: the frozen DANUS verifier launcher, MCP role, wrapper, and sandbox policy are retained. Its production `AGENTS.md` correctly forbids program execution during mathematical verification, so this non-mathematical capability session replaces the generated runtime prompt and `-C` home, and sets the same fixed probe model/effort used for the worker (`gpt-5.6-luna`, low). The production verifier prompt file and DANUS source remain unchanged. Verifier POSTs are forced through the managed proxy by clearing inherited `NO_PROXY` only for that command and the DANUS MCP environment; verdict persistence remains in the isolated experiment evidence directory.
- strategy/master/main: `NOT_IN_EXECUTION_PATH` for the current N1.8 mathematical path, so no artificial role or orchestration layer was added.
- scope: the capability sessions used `gpt-5.6-luna` at low effort only to execute fixed mechanical canaries. They loaded no theorem/problem and are not a mathematical experimental variable.

## Audit Semantics

- `SEARCH_INTENT_BLOCKED`: an intent is present, but there is no URL, tool call, socket attempt, returned result, or external byte. Integrity remains `PASS`.
- `OUTBOUND_ATTEMPT_BLOCKED`: a DNS, socket, HTTP, Git, package, or external-tool attempt occurred and the sandbox mechanically denied it with zero external bytes. Integrity remains `PASS`.
- `EXTERNAL_ACCESS_SUCCEEDED`: any non-allowlisted connection, resolved/contacted external service, returned search result, or received external byte. Integrity becomes `FAIL`.
- expected verifier traffic that succeeds at the exact session endpoint is classified separately as `LOOPBACK_ALLOWED`. An unexpected URL is conservatively classified as external success rather than silently ignored.
- the classification is used by the live N1.6/N1.8 `audit_run`, not only by the capability harness. Re-auditing the three previously excluded N1.8 cells classifies their blocked/no-result events as integrity PASS; a call without explicit blocking evidence remains a conservative external success.

## Adversarial Probes

The frozen structured result is [`mechanical_audit.json`](../experiments/danus_n19a_blind_boundary/reports/mechanical_audit.json). Each cell below was checked in both an actual DANUS worker launch and a fresh DANUS verifier-role launch. Each role completed 13 separate controls so one proxy denial could not prevent later controls from running.

| Capability | Probe 1 | Probe 2 | Probe 3 | Expected |
| --- | --- | --- | --- | --- |
| DNS: `getaddrinfo(example.com)`, `getaddrinfo(github.com)` | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Shell HTTP: `curl`, `wget` | BLOCKED, 0 bytes | BLOCKED, 0 bytes | BLOCKED, 0 bytes | BLOCKED |
| Python HTTP: `urllib` | BLOCKED, 0 bytes | BLOCKED, 0 bytes | BLOCKED, 0 bytes | BLOCKED |
| Hostname socket: `example.com:443` | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Direct public IPv4 and IPv6 sockets | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Generic `localhost` / `127.0.0.1` same-port decoy | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Git: `git ls-remote` | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Package manager: `pip index` | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| Hosted web/search and external arXiv/Matlas MCP | BLOCKED/ABSENT | BLOCKED/ABSENT | BLOCKED/ABSENT | BLOCKED/ABSENT |
| Dedicated verifier loopback POST | PASS | PASS | PASS | PASS |
| DANUS local Fact/Memory MCP `gm_search` | PASS | PASS | PASS | PASS |
| Verifier result persistence | PASS, 2 files | PASS, 2 files | PASS, 2 files | PASS |
| Session automatic gate | PASS | PASS | PASS | PASS |

Session evidence and role-level traces are frozen under [`probe_1`](../experiments/danus_n19a_blind_boundary/evidence/probe_1/summary.json), [`probe_2`](../experiments/danus_n19a_blind_boundary/evidence/probe_2/summary.json), and [`probe_3`](../experiments/danus_n19a_blind_boundary/evidence/probe_3/summary.json). Earlier diagnostics—including the broader `127.0.0.1` host allowlist, a stale human-readable log label, the review-blocked run, and the production-verifier-contract conflict—are preserved locally under ignored `evidence/intermediate_*/` directories and are not part of the frozen result.

## Positive Controls

- verifier loopback: `PASS` at `127.19.0.1:53943`, `127.19.0.1:36461`, and `127.19.0.1:55385`; the independent sandbox smoke also returned `N19A_LOOPBACK_OK 200`.
- DANUS local MCP: `PASS` in all 3 worker sessions through the unchanged `mcp__danus__gm_search` path.
- persistence: `PASS`; exactly two `verification.json` files were written per session, one for the worker control and one for the verifier control.
- negative local control: the host could reach each ordinary `127.0.0.1:<same-port>` decoy, while both sandbox roles were denied.

## Regression Tests

- command: `baselines/danus/runtime/venv/bin/python -m unittest discover -s experiments/danus_n19a_blind_boundary/tests -v`
  - passed: 15
  - failed: 0
- command: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
  - passed: 25
  - skipped: 1 opt-in real-Codex smoke
  - failed: 0
- command: `baselines/danus/runtime/venv/bin/python -m unittest experiments/danus_n16_blind/analysis/test_analysis.py -v`
  - passed: 9
  - failed: 0
- command: `baselines/danus/runtime/venv/bin/python -m unittest discover -s experiments/danus_n18_matched_scheduling/analysis -v`
  - passed: 14
  - failed: 0
- command: `wsl -e bash experiments/danus_n19a_blind_boundary/probes/loopback_sandbox_smoke.sh`
  - result: `N19A_LOOPBACK_OK 200`
- Python compilation and `git diff --check`: `PASS`.

The N1.9a unit tests cover all six required audit cases plus a same-host/port wrong-path failure: blocked intent, blocked attempt, successful connection, returned bytes, exact verifier loopback, and unexpected external URL. Additional contract tests cover wrapper override rejection, managed-proxy routing, preemptive denial recovery, required external-search surface evidence, and automatic-gate failure on any external success. Live-audit regressions cover both N1.8 false-positive forms, refused contact, affirmative search metadata, and a true external-success failure.

## Integrity

- DANUS modified: no; nested repository working tree clean.
- DANUS HEAD: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.
- Noespire `src/` modified: no; both `git diff HEAD -- src` and `git diff noespire-n1-proof-obligations -- src` are empty.
- DANUS source/prompts/worker/verifier/FactGraph/scheduling modified: no.
- mathematical runs performed: `0`.

## Freeze

- commit: the commit resolved by `noespire-n19a-blind-boundary^{}`; the report uses the annotated tag target to avoid an impossible self-referential commit hash.
- tag: annotated `noespire-n19a-blind-boundary`, message `Noespire N1.9a: blind execution boundary validated`.
- working tree: clean after the commit/tag freeze verification; the ignored intermediate diagnostic remains local evidence and is not part of the tag.

## Verdict

`BLIND_BOUNDARY_FROZEN`

## Next Step

N1.9b fresh strictly matched scheduling ablation.

Do not execute it in this task.
