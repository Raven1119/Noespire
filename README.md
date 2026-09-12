# Noespire

The optional [Continuous Research Proof Network](docs/CONTINUOUS_RESEARCH.md)
starts from an original problem and preserves local Study continuations, shared
verified Supports and fair revisits. Run it with `python -m research.continuous_research`.
It is separate from the preserved v3 product mode described below; no whole
proof graph is planned in advance and no cumulative failure count ends research.

Noespire develops a resumable AND/OR natural-language mathematical proof core.
Obligations have stable mathematical identities; alternative routes share them.
Fresh Codex workers propose proofs or counterexamples, and independent closed-book
verifiers admit Facts or Refutations. Failed routes expose local structural
frontiers for the existing two-stage refinement pipeline.

```
Problem workspace -> NodeSolver -> closed-book verifier -> accepted Fact
                         |
                  failure / local horizon
                         v
Strategist -> Strategy Gate -> BoundaryAware Patch Builder -> fidelity
    -> mechanical validation -> Structural Auditor / one bounded revision
    -> local GraphPatch -> continue NodeSolver
```

The current architecture entry is [Current Research Core](docs/CURRENT_RESEARCH_CORE.md).
The [earlier natural-language design](docs/Noespire_Natural_Language_Proof_Engine_Design_v2.md)
and [original Dual-DAG design](docs/Dual_DAG_Math_Research_Architecture.md) remain
historical references. Cross-DAG compilation and Lean verification are deferred;
an accepted Research Fact is an LLM-verified mathematical claim, not a Lean theorem.

## Run, inspect, resume

Install the source checkout with `pip install -e .`. A v3 problem workspace
contains `proof_graph.json` and separate Fact, Refutation, and execution evidence.
Import a legacy scaffold once into a fresh destination; its source stays intact.
Real runs require Docker, the `noespire-codex-isolated:local` image, and Codex
authentication; models never mount the problem workspace. New runs pin GPT-5.6 Sol,
`xhigh`, the local image digest and CLI version, with a 600-second call limit.

```powershell
python -m research.legacy_import LEGACY_PROBLEM FRESH_V3_PROBLEM
python -m research.dynamic_run run PATH_TO_PROBLEM --max-solver-attempts 6 --max-mutation-episodes 1 --max-builder-proposals 3 --max-auditor-calls 4
python -m research.dynamic_run status PATH_TO_PROBLEM
python -m research.dynamic_run resume PATH_TO_PROBLEM
```

The installed `noespire-research` command provides the same interface. `status`
requires no Docker or model call. `resume` retains the run ID and frozen budgets;
a completed run stays stopped. To import an earlier continuation's accounting,
pass `run --consumed counters.json`; use the names documented in the
[current core contract](docs/CURRENT_RESEARCH_CORE.md).

`--pause-after call_completed` deliberately exits at a durable checkpoint for a
restart probe. Use `resume` afterward. Run metadata and model evidence live under
the problem's ignored `dynamic_run/` directory. Keep the workspace exclusive to
this runner while the run is active.

## Development

```powershell
python -m pytest tests
```

Deterministic tests use a scripted Codex adapter with the real pipeline. Real
Codex smoke tests remain opt-in. See [repository contents policy](docs/REPOSITORY_CONTENTS.md):
source, tests, and maintained docs belong in Git; local runs and raw evidence do not.

The existing frontend remains the static proof workspace. Run it with
`python -m application.dev` after installing dependencies in `frontend/`.
Proof Core v3 does not connect dynamic refinement to the frontend.
