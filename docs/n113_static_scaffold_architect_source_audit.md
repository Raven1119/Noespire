# N1.13 Static Scaffold Architect Source Audit

## Scope and frozen inputs

- Product branch: `noespire-nl-proof-v2`, with the validated N1.12 working tree as the implementation baseline.
- Frozen DANUS baseline: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`; it remains an unchanged reference repository.
- This slice adds one fresh, one-shot decomposition proposal before N1.12. It adds no retry, repair, critic, adaptive refinement, parallel rollout, OR search, frontend path, Lean path, or database.

## Reuse decisions

| Area | Decision | N1.13 use |
| --- | --- | --- |
| `Fact`, `FactGraph`, `submit_candidate()` | KEEP_EXISTING | Architect output never enters the truth store. Only existing worker/verifier PASS can create a Fact. |
| `ProofObligation` and `execute_obligation()` | KEEP_EXISTING | Materialized premises remain accepted Fact IDs only; one worker and at most one verifier run per node attempt. |
| N1.11 attempt evidence | KEEP_EXISTING | Candidate, verifier, PASS/FAIL/ERROR, and exception recovery remain unchanged. |
| N1.12 `ProofScaffold`, scheduler, and closure | KEEP_EXISTING | Valid proposals become ordinary scaffold nodes and run through the already validated deterministic executor. |
| `CodexInvoker` | KEEP_EXISTING | Architect is a third consumer of the existing structured-output/fresh-ephemeral invocation seam. No provider abstraction is added. |
| `CodexExec` command/audit options | ADAPT | Optional pinned model/effort and the existing N1.9a-style blind surface are made explicit; timeout failures now retain invocation evidence. Existing callers keep their prior defaults. |
| N1.12 new-scaffold validation | ADAPT | Expose the existing pure structural check through a small reusable interface so proposal validation and `ProofScaffold.create()` cannot drift. Runtime scheduling semantics do not change. |
| Static proposal schema, prompt, validation, statuses | NEW | One module, `scaffold_architect.py`, owns proposal-only model interaction and the mechanical trust boundary. |
| Experiment isolation and aggregation | NEW | A self-contained experiment directory freezes theorem-only architect workspaces, raw proposals, validated scaffolds, audits, run state, and metrics. |

## Reusable N1.12 runtime

The following path is reused without semantic changes:

```text
ScaffoldNode
→ deterministic ready-node selection
→ ordinary ProofObligation with real Fact IDs
→ one ResearchWorker
→ one fresh verifier
→ verifier-gated Fact admission
→ downstream unlock
→ FactGraph.supporting_closure(target)
```

`solve_scaffold()` remains the only multi-node execution loop. N1.13 does not add a second scheduler, worker pool, retry loop, or feedback path into the Architect.

## Proposal-to-scaffold seam

The Codex response first becomes a `ScaffoldProposal`, which is still untrusted search output. It crosses into executable N1.12 state only here:

```text
raw ScaffoldProposal
→ validate_scaffold_proposal(...)
→ ValidatedScaffoldProposal
→ materialize_scaffold(...)
→ ProofScaffold.create(...)
```

No Fact is written at this seam. The raw proposal and normalized validated scaffold remain separate artifacts so later audit can distinguish model output from validator normalization.

## Mechanical checks

The LLM is not trusted for:

- non-empty and unique normalized node IDs;
- target existence and exact normalized target-statement equality;
- rejection of any target ancestor that restates the target theorem;
- self-dependencies, dangling dependencies, cycles, and duplicate exact nodes;
- configured node-count limit;
- the experimental requirement that at least one non-target ancestor reaches the target;
- base-Fact existence, matching `problem_id`, and membership in the exact allowed input set;
- rejection of pre-resolved or future Fact IDs.

These checks finish before `ProofScaffold.create()` and before any ResearchWorker/verifier call. Mechanically detecting arbitrary semantic hidden assumptions is explicitly deferred; only unauthorized Fact references are detectable in N1.13.

## Architect context

The Architect does not need the complete Fact Graph. Its prompt receives only:

- `problem_id`;
- the complete theorem statement;
- IDs and statements of explicitly allowed accepted premise Facts;
- the fixed proposal contract and current node limit.

It receives no Fact proofs, unrelated graph history, attempts, worker/verifier traces, DANUS memory, reference solution, Lean information, or previous theorem conversation. The validator may read the graph mechanically to authenticate allowed Fact IDs; that data is not added to the model prompt.

## Keeping decomposition separate from proof

The structured schema contains node identity, mathematical goal, scaffold dependencies, permitted base-Fact references, and target ID—no proof or reasoning field. The prompt says the Architect must design obligations rather than prove them and forbids administrative steps. The proposal is frozen before the first worker. Distinct fresh Codex invocations then prove and verify nodes; no worker result is sent back to the Architect, and failure ends as `EXECUTION_BLOCKED` without replanning.

## DANUS and isolation

No DANUS scheduler or source is needed. N1.13 reuses Noespire's already adapted Codex, Fact, verifier, and persistence paths. Real Architect invocations run with theorem-specific isolated working directories containing no reference proof or prior run evidence; prompts are identical apart from theorem/allowed-Fact input. The frozen command ignores user config/rules, uses `approval_policy=never`, restricts the managed network surface to an unused loopback host, and disables web/search/browser/apps/plugins/computer-use/subagent features. A non-mathematical capability probe observed that all three attempted shell commands—including HTTPS—were rejected before execution; host snapshots independently recorded an empty workspace before and after. DANUS remains clean and unmodified.
