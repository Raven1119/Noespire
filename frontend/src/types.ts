/**
 * Mirrors the REST contract exactly (spec §5/§6). Nothing else lives here.
 * The frontend consumes these types only; it never invents its own shapes.
 */

export type ProblemStatus = "OPEN" | "RUNNING" | "SOLVED";

/** Obligation truth stays OPEN; a latest ERROR attempt only changes display. */
export type DisplayStatus = ProblemStatus | "ERROR";

export type FailureClass = "contract" | "rejection" | "runtime" | "interrupted";

export interface ProblemSummary {
  problem_id: string;
  statement: string;
  status: ProblemStatus;
  display_status: DisplayStatus;
  attempt_count: number;
  derived_from: string | null;
  archived: boolean;
  last_activity: string | null;
}

export interface ProblemListResponse {
  problems: ProblemSummary[];
}

export interface CreateProblemResponse {
  problem_id: string;
  statement: string;
  status: ProblemStatus;
  derived_from: string | null;
  archived: boolean;
}

/** POST /api/problems/{id}/attempts → 202. The body carries no attempt id
 *  (freeze ruling 3); the frontend learns it by polling the read model. */
export interface StartAttemptResponse {
  status: string;
}

export interface Obligation {
  obligation_id: string;
  goal: string;
  premises: string[];
  route_id: string;
  status: "OPEN" | "RUNNING" | "DISCHARGED";
  resolved_by_fact_id: string | null;
}

export interface Candidate {
  statement: string;
  proof: string;
  predecessors: string[];
}

export interface VerifierArtifact {
  accepted: boolean;
  reason: string;
}

export interface Attempt {
  attempt_id: string;
  verdict: "RUNNING" | "PASS" | "FAIL" | "ERROR";
  failure_class: FailureClass | null;
  candidate: Candidate | null;
  verifier: VerifierArtifact | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  verifier_called?: boolean;
}

export interface Fact {
  fact_id: string;
  statement: string;
  proof: string;
  predecessors: string[];
}

/** GET /api/problems/{id} — the single aggregate the workspace UI needs. */
export interface WorkspaceReadModel {
  problem_id: string;
  statement: string;
  status: ProblemStatus;
  display_status: DisplayStatus;
  derived_from: string | null;
  archived: boolean;
  obligation: Obligation | null;
  attempts: Attempt[];
  target_fact: Fact | null;
  supporting_closure: Fact[];
  running_phase_hint: "generating" | "checking" | null;
  /** Live execution state (spec §5); present only when status == RUNNING. */
  live?: { running: boolean; current_attempt_id: string | null };
}
