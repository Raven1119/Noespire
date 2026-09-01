/**
 * Shared WorkspaceReadModel fixtures for Slice 4 workspace tests.
 * Every fixture conforms to ../types exactly — no invented fields.
 */

import type { Attempt, Fact, ProofNode, WorkspaceReadModel } from "../types";

export const LEMMA_ONE: Fact = {
  fact_id: "1111111111111111",
  statement: "Every even perfect number $n$ satisfies $2 \\mid n$.",
  proof: "By definition an even perfect number is even.\n\nHence $2 \\mid n$.",
  predecessors: [],
};

export const LEMMA_TWO: Fact = {
  fact_id: "2222222222222222",
  statement: "If $n = 2^{p-1}(2^p - 1)$ with $2^p - 1$ prime, then $n = T_{2^p - 1}$.",
  proof:
    "Compute $T_{2^p - 1} = \\frac{(2^p - 1)2^p}{2} = 2^{p-1}(2^p - 1) = n$.\n\nThe triangular identity is exact.",
  predecessors: [LEMMA_ONE.fact_id],
};

export const MAIN_FACT: Fact = {
  fact_id: "ffffffffffffffff",
  statement: "Every even perfect number is triangular.",
  proof:
    "Let $n$ be an even perfect number, so $n = 2^{p-1}(2^p - 1)$ with $2^p - 1$ prime.\n\n" +
    `By ${LEMMA_ONE.fact_id} the number $n$ is even, and by ${LEMMA_TWO.fact_id} we have $n = T_{2^p - 1}$.\n\n` +
    "Therefore $n$ is triangular.",
  predecessors: [LEMMA_TWO.fact_id],
};

export function makeAttempt(overrides: Partial<Attempt>): Attempt {
  return {
    attempt_id: "attempt-000001",
    verdict: "FAIL",
    failure_class: null,
    candidate: null,
    verifier: null,
    error: null,
    started_at: null,
    finished_at: null,
    obligation_id: null,
    scaffold_node_id: null,
    ...overrides,
  };
}

export function makeModel(overrides: Partial<WorkspaceReadModel>): WorkspaceReadModel {
  const model: WorkspaceReadModel = {
    problem_id: "p-1",
    statement: "Every even perfect number is triangular.",
    status: "OPEN",
    display_status: "OPEN",
    execution_mode: "LEGACY_DIRECT",
    derived_from: null,
    archived: false,
    obligation: {
      obligation_id: "root:p-1",
      goal: "Every even perfect number is triangular.",
      premises: [],
      route_id: "root",
      status: "OPEN",
      resolved_by_fact_id: null,
    },
    attempts: [],
    target_fact: null,
    supporting_closure: [],
    proof_structure: null,
    last_execution_failure: null,
    running_phase_hint: null,
    ...overrides,
  };
  // Legacy attempts belong to the root obligation (server-parsed field).
  model.attempts = model.attempts.map((attempt) =>
    attempt.obligation_id === null
      ? { ...attempt, obligation_id: `root:${model.problem_id}` }
      : attempt
  );
  return model;
}

const CANDIDATE = {
  statement: "Every even perfect number is triangular.",
  proof: "Let $n = 2^{p-1}(2^p - 1)$.\n\nThen $n = T_{2^p - 1}$, so $n$ is triangular.",
  predecessors: [] as string[],
};

/** SOLVED with a three-fact closure (Lemma 1, Lemma 2, Main theorem). */
export function solvedMultiFactModel(): WorkspaceReadModel {
  return makeModel({
    status: "SOLVED",
    display_status: "SOLVED",
    obligation: {
      obligation_id: "root:p-1",
      goal: "Every even perfect number is triangular.",
      premises: [],
      route_id: "root",
      status: "DISCHARGED",
      resolved_by_fact_id: MAIN_FACT.fact_id,
    },
    attempts: [
      makeAttempt({
        verdict: "PASS",
        candidate: { ...CANDIDATE, predecessors: [LEMMA_TWO.fact_id] },
        verifier: { accepted: true, reason: "The proof is correct." },
        started_at: "2026-08-31T10:15:00+08:00",
        finished_at: "2026-08-31T10:18:00+08:00",
      }),
    ],
    target_fact: MAIN_FACT,
    supporting_closure: [LEMMA_ONE, LEMMA_TWO, MAIN_FACT],
  });
}

/** SOLVED with a single-fact closure. */
export function solvedSingleFactModel(): WorkspaceReadModel {
  return makeModel({
    status: "SOLVED",
    display_status: "SOLVED",
    attempts: [
      makeAttempt({
        verdict: "PASS",
        candidate: CANDIDATE,
        verifier: { accepted: true, reason: "The proof is correct." },
      }),
    ],
    target_fact: { ...MAIN_FACT, predecessors: [] },
    supporting_closure: [{ ...MAIN_FACT, predecessors: [] }],
  });
}

/** OPEN after a fresh-verifier rejection. */
export function openRejectionModel(): WorkspaceReadModel {
  return makeModel({
    attempts: [
      makeAttempt({
        verdict: "FAIL",
        failure_class: "rejection",
        candidate: CANDIDATE,
        verifier: { accepted: false, reason: "The triangular identity is not justified." },
        started_at: "2026-08-31T10:15:00+08:00",
        finished_at: "2026-08-31T10:17:00+08:00",
      }),
    ],
  });
}

/** OPEN after a contract-guard failure (verifier never called). */
export function openContractModel(): WorkspaceReadModel {
  return makeModel({
    attempts: [
      makeAttempt({
        verdict: "FAIL",
        failure_class: "contract",
        candidate: {
          ...CANDIDATE,
          statement: "Every even perfect number is a triangle number.", // mismatched
        },
        verifier: {
          accepted: false,
          reason: "candidate statement does not match obligation goal",
        },
        started_at: "2026-08-31T10:15:00+08:00",
        finished_at: "2026-08-31T10:15:30+08:00",
      }),
    ],
  });
}

/** OPEN displaying ERROR after a worker runtime error. */
export function errorModel(): WorkspaceReadModel {
  return makeModel({
    display_status: "ERROR",
    attempts: [
      makeAttempt({
        verdict: "ERROR",
        failure_class: "runtime",
        error: "scripted worker error",
        started_at: "2026-08-31T10:15:00+08:00",
        finished_at: "2026-08-31T10:15:05+08:00",
      }),
    ],
  });
}

/** OPEN after an interrupted execution (residual RUNNING attempt file). */
export function interruptedModel(verifierCalled: boolean): WorkspaceReadModel {
  return makeModel({
    attempts: [
      makeAttempt({
        verdict: "RUNNING",
        failure_class: "interrupted",
        candidate: verifierCalled ? CANDIDATE : null,
        verifier_called: verifierCalled,
      }),
    ],
  });
}

/** OPEN with an unclassified FAIL (no outcome record survives). */
export function openUnclassifiedModel(): WorkspaceReadModel {
  return makeModel({
    attempts: [
      makeAttempt({
        verdict: "FAIL",
        failure_class: null,
        candidate: CANDIDATE,
        verifier: { accepted: false, reason: "pre-V1 evidence" },
      }),
    ],
  });
}

/** RUNNING before the candidate exists. */
export function runningGeneratingModel(): WorkspaceReadModel {
  return makeModel({
    status: "RUNNING",
    display_status: "RUNNING",
    attempts: [makeAttempt({ attempt_id: "attempt-000007", verdict: "RUNNING" })],
    running_phase_hint: "generating",
    live: { running: true, current_attempt_id: "attempt-000007" },
  });
}

/** RUNNING while the fresh verifier checks the candidate. */
export function runningCheckingModel(): WorkspaceReadModel {
  return makeModel({
    status: "RUNNING",
    display_status: "RUNNING",
    attempts: [
      makeAttempt({ attempt_id: "attempt-000007", verdict: "RUNNING", candidate: CANDIDATE }),
    ],
    running_phase_hint: "checking",
    live: { running: true, current_attempt_id: "attempt-000007" },
  });
}

/* ---------- STATIC_SCAFFOLD fixtures (N1.14P contract) ---------- */

export const SCAFFOLD_STATEMENT =
  "For every integer $n$, $n^5 - n$ is divisible by $5$.";

export const SCAFFOLD_FACT_BASE: Fact = {
  fact_id: "aaaaaaaabbbbcccc",
  statement: "$5 \\mid 0^5 - 0$.",
  proof: "Compute $0^5 - 0 = 0$, and $5 \\mid 0$.",
  predecessors: [],
};

export const SCAFFOLD_FACT_STEP: Fact = {
  fact_id: "ddddddddabcdeeee",
  statement:
    "For every integer $k$, if $5 \\mid k^5 - k$ then $5 \\mid (k+1)^5 - (k+1)$.",
  proof:
    "Expand $(k+1)^5 - (k+1) = (k^5 - k) + 5(k^4 + 2k^3 + 2k^2 + k)$.\n\n" +
    `By ${SCAFFOLD_FACT_BASE.fact_id} the claim holds at $k = 0$; the displayed identity lifts it from $k$ to $k+1$.\n\n` +
    "Hence the induction step is valid.",
  predecessors: [SCAFFOLD_FACT_BASE.fact_id],
};

export const SCAFFOLD_FACT_TARGET: Fact = {
  fact_id: "0123456789abcdef",
  statement: SCAFFOLD_STATEMENT,
  proof:
    "By induction on $|n|$.\n\n" +
    `The base case is ${SCAFFOLD_FACT_BASE.fact_id} and the step is ${SCAFFOLD_FACT_STEP.fact_id}.\n\n` +
    "For $n < 0$ apply the result to $-n$ and note $n^5 - n$ is odd in $n$.",
  predecessors: [SCAFFOLD_FACT_STEP.fact_id],
};

function makeProofNode(overrides: Partial<ProofNode>): ProofNode {
  return {
    node_id: "target",
    statement: SCAFFOLD_STATEMENT,
    dependency_node_ids: [],
    resolved_fact_id: null,
    latest_attempt_id: null,
    state: "PLANNED",
    ...overrides,
  };
}

/** Base model shared by the scaffold fixtures: STATIC_SCAFFOLD, no root
 *  obligation (node state lives in proof_structure). */
function makeScaffoldModel(
  overrides: Partial<WorkspaceReadModel>
): WorkspaceReadModel {
  return makeModel({
    statement: SCAFFOLD_STATEMENT,
    execution_mode: "STATIC_SCAFFOLD",
    obligation: null,
    ...overrides,
  });
}

/** (a) STATIC_SCAFFOLD RUNNING: helper VERIFIED, step RUNNING, target
 *  PLANNED. Nodes arrive sorted by node_id — deliberately NOT topological
 *  (a_step < b_target < c_base) to exercise the client-side topo sort. */
export function scaffoldRunningModel(): WorkspaceReadModel {
  return makeScaffoldModel({
    status: "RUNNING",
    display_status: "RUNNING",
    proof_structure: {
      target_node_id: "b_target",
      nodes: [
        makeProofNode({
          node_id: "a_step",
          statement: SCAFFOLD_FACT_STEP.statement,
          dependency_node_ids: ["c_base"],
          latest_attempt_id: "attempt-000002",
          state: "RUNNING",
        }),
        makeProofNode({
          node_id: "b_target",
          statement: SCAFFOLD_STATEMENT,
          dependency_node_ids: ["a_step"],
        }),
        makeProofNode({
          node_id: "c_base",
          statement: SCAFFOLD_FACT_BASE.statement,
          resolved_fact_id: SCAFFOLD_FACT_BASE.fact_id,
          latest_attempt_id: "attempt-000001",
          state: "VERIFIED",
        }),
      ],
    },
    attempts: [
      makeAttempt({
        attempt_id: "attempt-000001",
        verdict: "PASS",
        candidate: {
          statement: SCAFFOLD_FACT_BASE.statement,
          proof: "Compute $0^5 - 0 = 0$, and $5 \\mid 0$.",
          predecessors: [],
        },
        verifier: { accepted: true, reason: "The computation is correct." },
        started_at: "2026-08-31T10:15:00+08:00",
        finished_at: "2026-08-31T10:16:00+08:00",
        obligation_id: "scaffold:p-1:c_base",
        scaffold_node_id: "c_base",
      }),
      makeAttempt({
        attempt_id: "attempt-000002",
        verdict: "RUNNING",
        candidate: {
          statement: SCAFFOLD_FACT_STEP.statement,
          proof: "Expand $(k+1)^5 - (k+1)$ by the binomial theorem.",
          predecessors: [SCAFFOLD_FACT_BASE.fact_id],
        },
        started_at: "2026-08-31T10:17:00+08:00",
        obligation_id: "scaffold:p-1:a_step",
        scaffold_node_id: "a_step",
      }),
    ],
    supporting_closure: [SCAFFOLD_FACT_BASE],
    running_phase_hint: "checking",
    live: { running: true, current_attempt_id: "attempt-000002" },
  });
}

/** (b) STATIC_SCAFFOLD BLOCKED, status OPEN: lemma1 VERIFIED, lemma2 BLOCKED
 *  with a rejected attempt, target PLANNED (latest_attempt_id null). */
export function scaffoldBlockedModel(): WorkspaceReadModel {
  return makeModel({
    execution_mode: "STATIC_SCAFFOLD",
    obligation: null,
    proof_structure: {
      target_node_id: "target",
      nodes: [
        makeProofNode({
          node_id: "lemma1",
          statement: LEMMA_ONE.statement,
          resolved_fact_id: LEMMA_ONE.fact_id,
          latest_attempt_id: "attempt-000001",
          state: "VERIFIED",
        }),
        makeProofNode({
          node_id: "lemma2",
          statement: LEMMA_TWO.statement,
          dependency_node_ids: ["lemma1"],
          latest_attempt_id: "attempt-000002",
          state: "BLOCKED",
        }),
        makeProofNode({
          node_id: "target",
          statement: "Every even perfect number is triangular.",
          dependency_node_ids: ["lemma1", "lemma2"],
        }),
      ],
    },
    attempts: [
      makeAttempt({
        attempt_id: "attempt-000001",
        verdict: "PASS",
        candidate: {
          statement: LEMMA_ONE.statement,
          proof: LEMMA_ONE.proof,
          predecessors: [],
        },
        verifier: { accepted: true, reason: "The proof is correct." },
        started_at: "2026-08-31T10:15:00+08:00",
        finished_at: "2026-08-31T10:16:00+08:00",
        obligation_id: "scaffold:p-1:lemma1",
        scaffold_node_id: "lemma1",
      }),
      makeAttempt({
        attempt_id: "attempt-000002",
        verdict: "FAIL",
        failure_class: "rejection",
        candidate: {
          statement: LEMMA_TWO.statement,
          proof: "Compute $T_{2^p - 1}$ and compare.",
          predecessors: [LEMMA_ONE.fact_id],
        },
        verifier: {
          accepted: false,
          reason: "The triangular identity is not justified.",
        },
        started_at: "2026-08-31T10:17:00+08:00",
        finished_at: "2026-08-31T10:19:00+08:00",
        obligation_id: "scaffold:p-1:lemma2",
        scaffold_node_id: "lemma2",
      }),
    ],
    supporting_closure: [LEMMA_ONE],
  });
}

/** (c) STATIC_SCAFFOLD SOLVED: 3-node linear scaffold, all VERIFIED,
 *  multi-Fact closure in topo order (the real solved-example shape). */
export function scaffoldSolvedModel(): WorkspaceReadModel {
  const pass = (
    attemptId: string,
    nodeId: string,
    fact: Fact,
    minute: number
  ): Attempt =>
    makeAttempt({
      attempt_id: attemptId,
      verdict: "PASS",
      candidate: {
        statement: fact.statement,
        proof: fact.proof,
        predecessors: fact.predecessors,
      },
      verifier: { accepted: true, reason: "The proof is correct." },
      started_at: `2026-08-31T10:${minute}:00+08:00`,
      finished_at: `2026-08-31T10:${minute + 1}:00+08:00`,
      obligation_id: `scaffold:p-1:${nodeId}`,
      scaffold_node_id: nodeId,
    });
  return makeScaffoldModel({
    status: "SOLVED",
    display_status: "SOLVED",
    proof_structure: {
      target_node_id: "target",
      nodes: [
        makeProofNode({
          node_id: "base_case",
          statement: SCAFFOLD_FACT_BASE.statement,
          resolved_fact_id: SCAFFOLD_FACT_BASE.fact_id,
          latest_attempt_id: "attempt-000001",
          state: "VERIFIED",
        }),
        makeProofNode({
          node_id: "induction_step",
          statement: SCAFFOLD_FACT_STEP.statement,
          dependency_node_ids: ["base_case"],
          resolved_fact_id: SCAFFOLD_FACT_STEP.fact_id,
          latest_attempt_id: "attempt-000002",
          state: "VERIFIED",
        }),
        makeProofNode({
          node_id: "target",
          statement: SCAFFOLD_STATEMENT,
          dependency_node_ids: ["induction_step"],
          resolved_fact_id: SCAFFOLD_FACT_TARGET.fact_id,
          latest_attempt_id: "attempt-000003",
          state: "VERIFIED",
        }),
      ],
    },
    attempts: [
      pass("attempt-000001", "base_case", SCAFFOLD_FACT_BASE, 15),
      pass("attempt-000002", "induction_step", SCAFFOLD_FACT_STEP, 17),
      pass("attempt-000003", "target", SCAFFOLD_FACT_TARGET, 19),
    ],
    target_fact: SCAFFOLD_FACT_TARGET,
    supporting_closure: [SCAFFOLD_FACT_BASE, SCAFFOLD_FACT_STEP, SCAFFOLD_FACT_TARGET],
  });
}

/** (d) STATIC_SCAFFOLD architect failure: no scaffold materialized — no
 *  proof_structure, no attempts, status OPEN, execution-level failure. */
export function scaffoldArchitectFailureModel(): WorkspaceReadModel {
  return makeScaffoldModel({
    last_execution_failure: {
      outcome_stage: "ARCHITECT_INVALID",
      error: "proposed scaffold has a dependency cycle: target depends on itself",
      finished_at: "2026-08-31T10:12:00+08:00",
    },
  });
}
