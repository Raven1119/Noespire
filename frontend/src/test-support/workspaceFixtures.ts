/**
 * Shared WorkspaceReadModel fixtures for Slice 4 workspace tests.
 * Every fixture conforms to ../types exactly — no invented fields.
 */

import type { Attempt, Fact, WorkspaceReadModel } from "../types";

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
    ...overrides,
  };
}

export function makeModel(overrides: Partial<WorkspaceReadModel>): WorkspaceReadModel {
  return {
    problem_id: "p-1",
    statement: "Every even perfect number is triangular.",
    status: "OPEN",
    display_status: "OPEN",
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
    running_phase_hint: null,
    ...overrides,
  };
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
