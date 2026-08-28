# DANUS N1.6 Runtime Manifest

Status: **PRE-RUN FROZEN**

## Frozen state

- Noespire branch: `noespire-nl-proof-v2`
- pre-task Noespire HEAD: `471db63b2fe50843d5b4620e4ce1b81e7c5dce6f`
- N1 tag: `noespire-n1-proof-obligations` (unchanged)
- DANUS path: `baselines/danus`
- DANUS branch/commit: `codex` / `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`
- DANUS source/prompts/workers/verifier/strategy/FactGraph/retrieval/memory/orchestration modified: **NO**
- canonical capability evidence: `protocol/evidence/capability_probe_20260828T162750Z/summary.json` (`PASS`)

## Diagnostic set

| Order | Problem | Structure | SHA-256 |
| ---: | --- | --- | --- |
| 1 | `cubic-form-image` | constructions plus divisibility obstruction | `51109dc012315b93ae138daf3ef059cbb7a1ee5c11f2db53ef7962374d17d632` |
| 2 | `period-five-recurrence` | recurrence period, cyclic orbits, fixed points | `2a717f69d7178eb6e7aa35f2e8485b0be801b2263235b06ea71c6ed20cdacbeb` |
| 3 | `weighted-binomial-paths` | first-hit decomposition and double count | `6baac13f257def1abcde219c457de62f4610600e64ea453f3ba836288eb2c80a` |
| 4 | `reflection-fixed-vector` | reflection determinant and eigenvalue parity | `0916681243c800579f8f38563c3cd5a6cb9a84c68733d008bd77bb09af91981c` |

The canonical machine-readable set is `problems/manifest.json`. The four problem files may not change after the pre-run freeze commit. A later statement defect is `INVALID_PROBLEM`, never grounds for replacement.

## Runtime equality with N1.5

Held equal:

- DANUS commit and ordinary proof algorithm;
- backend: existing authenticated ChatGPT Codex session;
- worker/verifier model: `gpt-5.6-sol`;
- worker roster: upstream default `high:3,xhigh:4`;
- worker efforts: upstream role values (`high`, `xhigh`);
- verifier effort: `xhigh`;
- maximum rounds: `1`;
- worker hard timeout: `14400` seconds;
- maximum consecutive failures: `5`;
- verifier Codex timeout: `900` seconds;
- gateway verifier HTTP timeout: `3600` seconds;
- Fact Graph, memory, supporting closure, termination, and target-selection semantics;
- the same problem-independent seven-role assignment template used in N1.5.

Unavoidable experimental differences:

1. Four new problem statements are used.
2. Every proof-relevant Codex session runs through the frozen blind wrapper.
3. Built-in web/browser, Matlas, plugins/apps, and native Codex subagents are disabled; local DANUS Fact/Memory MCP tools remain available.
4. The N1.6 experiment-control directory (including `reference/` and the source-bearing manifest) is denied by the Codex filesystem profile.
5. A fresh stateless verifier service uses an isolated loopback port for each independent run so its inherited wrapper policy and evidence log are unambiguous.
6. Only verifier-role sessions receive write access to `runtime/verify-runs/`, the existing DANUS output contract; worker and strategy/main sessions do not. This was added after the preserved pre-run system-invalid attempt showed that a workspace-only verifier could reason but could not persist its verdict.

## Frozen worker assignment template

Every assignment requires the complete theorem statement verbatim from `PROBLEM.md`, only verifier-accepted predecessors when genuinely needed, and no weakening/paraphrase.

- `high`: develop a rigorous complete proof directly.
- `high2`: seek an independent alternative proof route.
- `high3`: identify concrete intermediate lemmas or obstructions, prove what is justified, and complete the target if possible.
- `xhigh`: produce a complete quantified proof with assumptions and boundary cases audited.
- `xhigh2`: independently audit promising routes and produce a verifier-ready proof if possible.
- `xhigh3`: seek a structurally distinct proof and record concrete obstructions if blocked.
- `xhigh4`: inspect shared verified state, synthesize the strongest available route, and complete the target if possible.

## Run order and freeze

Run order is the manifest order above. The required pre-run commit message is:

`experiment: freeze N1.6 blind diagnostic`

No formal problem run may start before that commit exists.
