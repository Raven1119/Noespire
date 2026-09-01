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

/** POST /api/problems/{id}/fork → 201. Same shape as create (spec §6). */
export type ForkProblemResponse = CreateProblemResponse;

/** POST /api/problems/{id}/archive → 200 (spec §6). Idempotent. */
export interface ArchiveProblemResponse {
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

export type ExecutionMode = "LEGACY_DIRECT" | "STATIC_SCAFFOLD";

export type ProofNodeState =
  | "VERIFIED"
  | "RUNNING"
  | "BLOCKED"
  | "READY"
  | "PLANNED";

export interface ProofNode {
  node_id: string;
  statement: string;
  dependency_node_ids: string[];
  resolved_fact_id: string | null;
  latest_attempt_id: string | null;
  state: ProofNodeState;
}

/** Read-only projection of scaffold search state (never an authority). Null
 *  in legacy mode and before a scaffold is materialized. Nodes arrive sorted
 *  by node_id — NOT in topological order. */
export interface ProofStructure {
  target_node_id: string;
  nodes: ProofNode[];
}

export type ExecutionFailureStage =
  | "ARCHITECT_ERROR"
  | "ARCHITECT_INVALID"
  | "SYSTEM_ERROR"
  | "RUNTIME_ERROR"
  | "INTERRUPTED";

/** An execution-level failure that produced no node attempts (architect
 *  failure, pre-attempt runtime failure, architect-stage crash recovery). */
export interface LastExecutionFailure {
  outcome_stage: ExecutionFailureStage;
  error: string | null;
  finished_at: string | null;
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
  /** Server-parsed; the frontend NEVER parses obligation ids itself. */
  obligation_id: string | null;
  scaffold_node_id: string | null;
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
  execution_mode: ExecutionMode;
  derived_from: string | null;
  archived: boolean;
  /** Legacy root payload; null in scaffold mode (node state lives in
   *  `proof_structure`). */
  obligation: Obligation | null;
  attempts: Attempt[];
  target_fact: Fact | null;
  supporting_closure: Fact[];
  proof_structure: ProofStructure | null;
  last_execution_failure: LastExecutionFailure | null;
  running_phase_hint: "generating" | "checking" | null;
  /** Live execution state (spec §5); present only when status == RUNNING. */
  live?: { running: boolean; current_attempt_id: string | null };
}
