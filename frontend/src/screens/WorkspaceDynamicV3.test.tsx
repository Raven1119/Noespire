/**
 * DYNAMIC_PROOF_V3 workspace rendering: AND/OR route tree, run-state panels,
 * v3 attempt labels, refutation cards, refinement history.
 * All states in the fixtures are backend-derived projections — the UI must
 * render them verbatim and never infer viability or truth.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type {
  Attempt,
  ProofGraphObligation,
  ProofGraphProjection,
  ProofGraphRoute,
  WorkspaceReadModel,
} from "../types";
import { AttemptsTab } from "../workspace/AttemptsTab";
import {
  LEMMA_ONE,
  LEMMA_TWO,
  MAIN_FACT,
  makeAttempt,
  makeModel,
} from "../test-support/workspaceFixtures";

afterEach(cleanup);

const TARGET_ID = "ob-target";
const LEMMA_A_ID = "ob-lemma-a";
const LEMMA_B_ID = "ob-lemma-b";

function obligation(overrides: Partial<ProofGraphObligation>): ProofGraphObligation {
  return {
    obligation_id: TARGET_ID,
    goal: MAIN_FACT.statement,
    context: "",
    statement: MAIN_FACT.statement,
    truth_state: "OPEN",
    resolved_fact_id: null,
    resolved_route_id: null,
    refutation_id: null,
    latest_attempt_id: null,
    ...overrides,
  };
}

function route(overrides: Partial<ProofGraphRoute>): ProofGraphRoute {
  return {
    route_id: "route-direct",
    target_obligation_id: TARGET_ID,
    prerequisite_obligation_ids: [],
    support_fact_ids: [],
    kind: "DIRECT",
    lifecycle: "OPEN",
    derived_state: "READY",
    exhaustion_reason: null,
    origin_patch_id: null,
    ...overrides,
  };
}

function graph(overrides: Partial<ProofGraphProjection>): ProofGraphProjection {
  return {
    target_obligation_id: TARGET_ID,
    obligations: [obligation({})],
    routes: [route({})],
    frontiers: [],
    ...overrides,
  };
}

function v3Attempt(overrides: Partial<Attempt>): Attempt {
  return makeAttempt({
    obligation_id: TARGET_ID,
    obligation_goal: MAIN_FACT.statement,
    route_id: "route-direct",
    ...overrides,
  });
}

function v3Model(overrides: Partial<WorkspaceReadModel>): WorkspaceReadModel {
  return makeModel({
    execution_mode: "DYNAMIC_PROOF_V3",
    obligation: null,
    ...overrides,
  });
}

function renderAttempts(model: WorkspaceReadModel) {
  return render(
    <MemoryRouter>
      <AttemptsTab model={model} onInspectAttempt={() => undefined} />
    </MemoryRouter>
  );
}

/** Blocked: direct route exhausted by three rejected proofs; strategist
 *  declined; run terminally STOPPED. */
function blockedModel(): WorkspaceReadModel {
  const rejected = (id: string) =>
    v3Attempt({
      attempt_id: id,
      verdict: "FAIL",
      outcome: "PROOF_REJECTED",
      failure_class: "rejection",
      candidate: {
        statement: MAIN_FACT.statement,
        proof: "missing argument",
        predecessors: [],
        kind: "PROOF_CANDIDATE",
        counterexample: "",
      },
      verifier: { accepted: false, reason: "The triangular identity is not justified." },
    });
  return v3Model({
    dynamic: {
      run_id: "run-1",
      phase: "STOPPED",
      stop_reason: "STRATEGIST_DECLINE",
      error: null,
      frontier_obligation_id: null,
    },
    proof_graph: graph({
      routes: [
        route({
          lifecycle: "EXHAUSTED",
          derived_state: "EXHAUSTED",
          exhaustion_reason: "The triangular identity is not justified.",
        }),
      ],
    }),
    attempts: [
      rejected("attempt-000001"),
      rejected("attempt-000002"),
      rejected("attempt-000003"),
    ],
  });
}

/** Solved after one SPLIT refinement: two lemma obligations discharged,
 *  target discharged through the split route; multi-Fact closure. */
function solvedSplitModel(): WorkspaceReadModel {
  return v3Model({
    status: "SOLVED",
    display_status: "SOLVED",
    dynamic: {
      run_id: "run-1",
      phase: "STOPPED",
      stop_reason: "TARGET_SOLVED",
      error: null,
      frontier_obligation_id: null,
    },
    proof_graph: graph({
      obligations: [
        obligation({
          truth_state: "DISCHARGED",
          resolved_fact_id: MAIN_FACT.fact_id,
          resolved_route_id: "route-split",
        }),
        obligation({
          obligation_id: LEMMA_A_ID,
          goal: LEMMA_ONE.statement,
          statement: LEMMA_ONE.statement,
          truth_state: "DISCHARGED",
          resolved_fact_id: LEMMA_ONE.fact_id,
          resolved_route_id: "route-a",
        }),
        obligation({
          obligation_id: LEMMA_B_ID,
          goal: LEMMA_TWO.statement,
          statement: LEMMA_TWO.statement,
          truth_state: "DISCHARGED",
          resolved_fact_id: LEMMA_TWO.fact_id,
          resolved_route_id: "route-b",
        }),
      ],
      routes: [
        route({ lifecycle: "EXHAUSTED", derived_state: "EXHAUSTED", exhaustion_reason: "x" }),
        route({
          route_id: "route-split",
          kind: "SPLIT",
          prerequisite_obligation_ids: [LEMMA_A_ID, LEMMA_B_ID],
          origin_patch_id: "patch-1",
        }),
        route({ route_id: "route-a", target_obligation_id: LEMMA_A_ID }),
        route({ route_id: "route-b", target_obligation_id: LEMMA_B_ID }),
      ],
    }),
    patches: [
      {
        step: 1,
        patch_id: "patch-1",
        operator: "SPLIT",
        target_obligation_id: TARGET_ID,
        obligation_goals: [LEMMA_ONE.statement, LEMMA_TWO.statement],
      },
    ],
    target_fact: MAIN_FACT,
    supporting_closure: [LEMMA_ONE, LEMMA_TWO, MAIN_FACT],
    attempts: [
      v3Attempt({
        verdict: "PASS",
        outcome: "FACT_ADMITTED",
        route_id: "route-split",
        fact_id: MAIN_FACT.fact_id,
        candidate: {
          statement: MAIN_FACT.statement,
          proof: MAIN_FACT.proof,
          predecessors: [LEMMA_TWO.fact_id],
          kind: "PROOF_CANDIDATE",
          counterexample: "",
        },
        verifier: { accepted: true, reason: "The proof is correct." },
      }),
    ],
  });
}

describe("DynamicProofPlan (v3 route tree)", () => {
  it("renders the exhausted direct route with its reason and the terminal stop panel", () => {
    renderAttempts(blockedModel());
    expect(screen.getByText("Proof plan")).toBeTruthy();
    expect(screen.getByText("Direct route · Exhausted")).toBeTruthy();
    expect(
      screen.getAllByText("The triangular identity is not justified.").length
    ).toBeGreaterThan(0);
    expect(screen.getByText("Open")).toBeTruthy();
    // Stop panel: honest terminal state, no Retry promise.
    expect(screen.getByText("No useful decomposition")).toBeTruthy();
    expect(
      screen.getByText(/This run is terminal — it cannot be retried/)
    ).toBeTruthy();
  });

  it("renders split routes as an AND tree with verified children and refinement history", () => {
    renderAttempts(solvedSplitModel());
    expect(screen.getByText("Split route · Ready")).toBeTruthy();
    expect(screen.getByText("Target")).toBeTruthy();
    // Verified obligations wear the LLM-verified badge (target + 2 lemmas);
    // the admitted-Fact attempt card carries its own badge outside the plan.
    const plan = screen.getByRole("heading", { name: "Proof plan" })
      .closest("section") as HTMLElement;
    expect(within(plan).getAllByText("LLM-verified")).toHaveLength(3);
    expect(screen.getByText("Refinements")).toBeTruthy();
    expect(screen.getByText(/Split · step 1/)).toBeTruthy();
    // No stop panel on a solved run.
    expect(screen.queryByText(/This run is terminal/)).not.toBeTruthy();
  });

  it("marks the current frontier from the projection", () => {
    const model = v3Model({
      status: "RUNNING",
      display_status: "RUNNING",
      dynamic: {
        run_id: "run-1",
        phase: "SOLVE",
        stop_reason: null,
        error: null,
        frontier_obligation_id: TARGET_ID,
      },
      proof_graph: graph({
        frontiers: [{ kind: "PROOF", obligation_id: TARGET_ID, route_id: "route-direct" }],
      }),
      live: { running: true, current_attempt_id: "attempt-000001" },
      attempts: [v3Attempt({ verdict: "RUNNING", outcome: "RUNNING" })],
    });
    renderAttempts(model);
    expect(screen.getByText("◂ frontier")).toBeTruthy();
    // The authoritative persisted phase, not the inferred hint.
    expect(screen.getByText(/Proving the current obligation…/)).toBeTruthy();
    expect(screen.queryByText(/phase inferred/)).not.toBeTruthy();
  });
});

describe("v3 attempts", () => {
  it("labels rejected proofs with the precise outcome and obligation goal", () => {
    renderAttempts(blockedModel());
    expect(screen.getAllByText(/FAIL · verifier rejected/)).toHaveLength(3);
    expect(screen.getAllByText(/^Obligation:/).length).toBeGreaterThan(0);
  });

  it("renders a verified refutation as refutation, never as a proven Fact", () => {
    const model = v3Model({
      dynamic: {
        run_id: "run-1",
        phase: "STOPPED",
        stop_reason: "TARGET_REFUTED",
        error: null,
        frontier_obligation_id: null,
      },
      proof_graph: graph({
        obligations: [
          obligation({ truth_state: "REFUTED", refutation_id: "ref-1" }),
        ],
      }),
      refutations: [
        {
          refutation_id: "ref-1",
          obligation_id: TARGET_ID,
          goal: MAIN_FACT.statement,
          context: "",
          counterexample: "n = 0.5 falsifies the integrality reading.",
          reason: "The counterexample satisfies the context and falsifies the goal.",
        },
      ],
      attempts: [
        v3Attempt({
          verdict: "PASS",
          outcome: "REFUTATION_ADMITTED",
          refutation_id: "ref-1",
          candidate: {
            statement: MAIN_FACT.statement,
            proof: "",
            predecessors: [],
            kind: "COUNTEREXAMPLE_CANDIDATE",
            counterexample: "n = 0.5 falsifies the integrality reading.",
          },
          verifier: {
            accepted: true,
            reason: "The counterexample satisfies the context and falsifies the goal.",
          },
        }),
      ],
    });
    renderAttempts(model);
    expect(screen.getByText("LLM-verified refutation")).toBeTruthy();
    expect(screen.getByText("Refuted")).toBeTruthy();
    // The truth badge for Facts must not appear anywhere.
    expect(screen.queryByText("LLM-verified")).not.toBeTruthy();
    expect(screen.getByText("Target refuted")).toBeTruthy();
  });

  it("shows the resume hint for a crashed (phase ≠ STOPPED) run", () => {
    const model = v3Model({
      dynamic: {
        run_id: "run-1",
        phase: "SOLVE",
        stop_reason: null,
        error: null,
        frontier_obligation_id: TARGET_ID,
      },
      proof_graph: graph({}),
      attempts: [v3Attempt({ verdict: "RUNNING", outcome: "INTERRUPTED", failure_class: "interrupted" })],
    });
    renderAttempts(model);
    expect(screen.getByText("Run interrupted")).toBeTruthy();
    expect(screen.getByText(/Retry resumes it/)).toBeTruthy();
  });
});
