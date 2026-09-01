# N1.13 Static Scaffold Architect MVP Report

## Verdict

`STATIC_SCAFFOLD_ARCHITECT_VALIDATED`

The frozen experiment met all nine validation checks: three real theorem inputs, three mechanically valid multi-node proposals, two target PASS results, multi-Fact supporting closures for both solved cases, the existing verifier gate on every executed node, no retry/repair, unique fresh threads, and a mechanically confirmed blind boundary for every Architect.

## Source reuse

N1.13 adds one proposal boundary in front of the unchanged N1.12 execution path:

```text
ProblemSpec
→ fresh ScaffoldArchitect.propose()
→ untrusted ScaffoldProposal
→ validate_scaffold_proposal()
→ ValidatedScaffoldProposal
→ materialize_scaffold()
→ existing solve_scaffold()
→ existing obligation/worker/verifier/Fact admission
→ SupportingClosure(target)
```

`FactGraph`, `ProofObligation`, attempt evidence, ready-node scheduling, Fact admission, downstream unlocking, and supporting-closure traversal are reused. The only N1.12 adaptation is the extraction of its new-scaffold checks into the pure `validate_scaffold_definition()` function, which `ProofScaffold.create()` still calls. No second scheduler or proof path was added.

## Architect contract

The structured proposal schema contains only:

- node `node_id`;
- complete mathematical `goal`;
- proposal-local `depends_on` IDs;
- explicitly allowed accepted `premise_fact_ids`;
- one `target_node_id`.

It contains no proof, confidence, priority, token estimate, embedding, or reasoning trace. The prompt states that the task is decomposition rather than proof, requires a finite compact AND-DAG, forbids administrative nodes and new assumptions, and requires the target goal to reproduce the complete theorem. Product configuration allows one node; the frozen experiment used `require_intermediate=true` and `max_nodes=6`.

The Architect receives only `problem_id`, the complete theorem, and IDs/statements of explicitly allowed Facts. It does not receive Fact proofs, the full graph, attempts, worker/verifier traces, DANUS memory, reference material, prior theorem output, or Lean data.

## Mechanical validation and truth boundary

Before any worker invocation, validation checks:

- nonempty proposal, configured node limit, and unique normalized node IDs;
- known target and exact normalized target-goal equality;
- no self-reference, dangling edge, cycle, duplicate exact node, or target-equivalent ancestor;
- at least one target ancestor when the experiment requires an intermediate;
- exact allowed-Fact set, Fact existence/content, matching `problem_id`, and proposal references confined to that set;
- no pre-resolved/future Fact ID.

Only a validated proposal can create a `ProofScaffold`; this operation writes no Fact. Every executed node is materialized as an ordinary obligation and can write a Fact only after the unchanged verifier accepts it. Arbitrary semantic hidden assumptions remain outside this mechanical validator and are reserved for a later structural-audit experiment.

## Failure semantics

The one-shot API exposes exactly the required terminal distinctions:

- `ARCHITECT_ERROR`: invocation, timeout, or parse failure;
- `ARCHITECT_INVALID`: mechanical proposal rejection before any worker/verifier/Fact write;
- `SYSTEM_ERROR`: a validated proposal that cannot be persisted/materialized;
- `EXECUTION_BLOCKED`: a valid frozen scaffold whose actual node execution fails or is rejected;
- `SOLVED`: the target Fact is verifier-accepted.

Architect is called once. Worker/verifier output is never fed back into it. There is no retry, repair, refinement, GraphPatch, or replan path.

## Persistence and blind boundary

Each successful proposal preserves separate `architect_proposal.json`, copied Architect invocation evidence, and normalized `validated_scaffold.json`, followed by final scaffold, attempts, Facts, closure, invocation/thread, and token evidence. Cross-case raw proposals also live under `architect_proposals/`; all role audits live under `codex_audits/`.

Each theorem used one new empty temporary workspace and one fresh ephemeral Codex process per role invocation. The frozen command pinned `gpt-5.6-sol` at `medium`, ignored user config/rules, denied approvals, restricted the managed network surface to unused loopback, and disabled hosted search/browser/apps/plugins/computer-use/subagents. The preserved capability probe has a conservative model self-report because shell execution itself was denied; mechanical assessment is PASS because the host snapshots were empty and all three attempted commands, including HTTPS, were rejected before execution. No theorem was rerun.

## Deterministic tests

The N1.13 tests cover:

- valid linear `H1 → H2 → Target` execution;
- valid diamond gating;
- cycle, target weakening, target-equivalent ancestor, duplicate exact node, excess nodes, and experimental single-node rejection;
- hidden/unexposed and fake Fact references;
- Architect exception/timeout evidence and distinct materialization-system failure;
- execution BLOCKED after verifier rejection with successful prior Fact preserved;
- blind Codex command pinning and retrieval-surface disabling.

Command: `pytest -q tests`

Result: `231 passed, 4 skipped, 1 warning, 40 subtests passed`.

Running unscoped `pytest -q` at repository root is not the parent-project suite: it also discovers the independent nested DANUS repository (whose optional MCP/Linux dependencies are not installed in the Windows Noespire environment) and historical experiment trees with duplicate test module names. The canonical Noespire regression boundary is `tests/`.

## Real experiment

Protocol: `n113-static-scaffold-architect-v1`; same prompt, model, reasoning effort, node limit, blind surface, worker, and verifier for all cases. There were no allowed base Facts or reference proofs. Direct single-node baseline execution was deferred to avoid doubling this MVP run, so no performance or comparative-benefit claim is made.

| Theorem | Architect | Nodes / edges / target depth | Attempts | Verifier PASS / FAIL | Result | Closure | Outside closure | Wall time |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Odd-sum induction | valid | 3 / 2 / 1 | 3 | 3 / 0 | SOLVED | 3 | 0 | 65.31 s |
| Integer divisibility | valid | 3 / 2 / 1 | 1 | 0 / 1 | EXECUTION_BLOCKED | 0 | 0 | 30.73 s |
| Zero-sum cubes | valid | 2 / 1 / 1 | 2 | 2 / 0 | SOLVED | 2 | 0 | 54.53 s |

All three Architect proposals were mechanically valid and multi-node. The two solved cases wrote five verifier-accepted Facts in total, with every intermediate Fact present in its target supporting closure. Across theorem runs there were 15 unique non-null thread IDs: three Architect, six worker, and six verifier sessions. Aggregate reanalysis also mechanically confirmed the exact blind command option set and empty pre/post workspace for each Architect.

Review hardening added an explicit prompt clause and validator rule against using a target-equivalent theorem as the target's ancestor. The frozen real Architect prompts predate that explicit clause and are preserved unchanged. No theorem was rerun: all three raw proposals independently pass the hardened final validator, recorded by `post_review_mechanical_revalidation_pass=true` in the recomputed aggregate.

The divisibility scaffold was a mathematically sensible diamond (`divisible by 2`, `divisible by 3` → target). The first worker correctly proved the parity lemma, but the unchanged verifier rejected it for not proving divisibility by 6—the complete problem rather than the current node. Execution immediately stopped with zero Fact writes and no second Architect call. This is preserved evidence of an existing verifier/subgoal-context limitation, not repaired in N1.13.

## Token breakdown

Counts are the Codex `turn.completed` usage fields. Cached input was zero in every invocation.

| Theorem | Architect in / out | Worker in / out | Verifier in / out | Total in / out |
| --- | ---: | ---: | ---: | ---: |
| Odd-sum induction | 9,379 / 360 | 28,218 / 579 | 28,452 / 280 | 66,049 / 1,219 |
| Integer divisibility | 9,338 / 200 | 9,205 / 142 | 9,252 / 144 | 27,795 / 486 |
| Zero-sum cubes | 9,354 / 194 | 18,735 / 421 | 18,958 / 361 | 47,047 / 976 |
| **Total** | **28,071 / 754** | **56,158 / 1,142** | **56,662 / 785** | **140,891 / 2,681** |

Derived combined input-plus-output cost per verified Fact was 22,422.67 for odd-sum induction and 24,011.50 for zero-sum cubes; the blocked divisibility case wrote no Fact. The same values are tokens per scaffold node for the two fully executed cases. These observations are not a comparison with direct proof.

## Known limitations

- Mechanical validation cannot establish semantic soundness, useful granularity, or absence of implicit assumptions.
- There is no fresh structural LLM audit in N1.13 by design.
- The inherited verifier prompt may judge an intermediate lemma against the full theorem, as the divisibility case demonstrated.
- The sample has three small theorems and supports feasibility only, not solve-rate generalization or efficiency gains.
- The experiment requires an intermediate; the production API intentionally continues to allow a single target node.
- Host policy denied all probe shell execution, so the blind evidence establishes absence of shell/network access rather than successful read-only shell capability.

## Scope audit

Not implemented: Adaptive Cut, Cheap Probe, failure-driven refinement, GraphPatch, Local Graph Surgery, retries, fan-out, parallel rollout, OR routes, iterative Architect conversation, structural critic, retrieval/memory redesign, Lean, frontend, Cross-DAG, or graph database. DANUS source and its frozen Git worktree were not modified.

## Review gate

The dual-axis `/code-review` found one spec blocker: a target-equivalent ancestor could satisfy the experimental intermediate condition without being an actual decomposition. The final prompt and mechanical validator now reject it before any worker call, with a deterministic regression test. Review also identified two evidence/status defects: materialization errors were mislabeled as architect-invalid, and blind PASS relied too heavily on model self-report. The final code uses `SYSTEM_ERROR` after successful validation, mechanically parses the preserved probe stderr, validates the exact frozen blind option sequence, and includes blind checks plus hardened-proposal revalidation in aggregate acceptance. After these fixes and documentation synchronization, both Spec and Standards axes PASS with no remaining code or architecture findings.
