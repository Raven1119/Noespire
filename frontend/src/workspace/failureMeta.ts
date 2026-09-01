import type {
  Attempt,
  FailureClass,
  LastExecutionFailure,
  WorkspaceReadModel,
} from "../types";

/**
 * The single place failure-class branching lives (spec §10). Slice 3 uses the
 * labels only; Slice 4 adds the class-specific glyphs and next-action copy
 * (spec §8.3) here. Never a generic "Verifier Failed".
 */
export const FAILURE_CLASS_LABELS: Record<FailureClass, string> = {
  contract: "Contract failure",
  rejection: "Verification rejection",
  runtime: "Runtime error",
  interrupted: "Interrupted",
};

export interface FailurePanelData {
  glyph: string;
  title: string;
  /** Persisted evidence line (verifier reason or runtime error), if any. */
  reason: string | null;
  /** Class-specific explanation + next action (spec §8.3, prototype copy). */
  lines: string[];
}

/**
 * Panel content for a classified failure. Returns null when
 * `failure_class` is null — an unclassified FAIL must never be shown under
 * an invented label.
 */
export function failurePanel(attempt: Attempt): FailurePanelData | null {
  switch (attempt.failure_class) {
    case "contract":
      return {
        glyph: "≠",
        title: FAILURE_CLASS_LABELS.contract,
        reason: attempt.verifier?.reason ?? null,
        lines: [
          "The proposal violated the submission contract — the fresh verifier was never called.",
          "Suggested next: Revise & Fork with a sharpened statement, or Retry.",
        ],
      };
    case "rejection":
      return {
        glyph: "✕",
        title: FAILURE_CLASS_LABELS.rejection,
        reason: attempt.verifier?.reason ?? null,
        lines: [
          "Suggested next: Retry — the obligation is back to OPEN and the verifier's gap is kept as evidence.",
        ],
      };
    case "runtime":
      return {
        glyph: "⚠",
        title: FAILURE_CLASS_LABELS.runtime,
        reason: attempt.error ?? "unknown runtime error",
        lines: ["Suggested next: Retry — no mathematical content was produced."],
      };
    case "interrupted":
      return {
        glyph: "⚠",
        title: FAILURE_CLASS_LABELS.interrupted,
        reason: null,
        lines: [
          attempt.verifier_called === true
            ? "Execution stopped after the fresh verifier was called — no verdict was recorded."
            : "Execution stopped before the fresh verifier was called — no verdict was recorded.",
          "Suggested next: Retry.",
        ],
      };
    case null:
      return null;
  }
}

const RETRY_LINE = "Suggested next: Retry.";

/**
 * Panel content for an execution-level failure (`last_execution_failure`) —
 * an application/UI outcome classification (architect-stage failure,
 * pre-attempt runtime failure, crash recovery), NOT a mathematical failure
 * taxonomy. Such failures produced no node attempts, so they live above the
 * attempt list, not on a card.
 */
export function executionFailurePanel(
  failure: LastExecutionFailure
): FailurePanelData | null {
  switch (failure.outcome_stage) {
    case "ARCHITECT_ERROR":
      return {
        glyph: "⚠",
        title: "Architect error",
        reason: failure.error,
        lines: [
          "The proof plan could not be produced. No proof nodes ran.",
          RETRY_LINE,
        ],
      };
    case "ARCHITECT_INVALID":
      return {
        glyph: "⚠",
        title: "Invalid proof plan",
        reason: failure.error,
        lines: [
          "The Architect's proposal failed mechanical validation. No proof nodes ran.",
          RETRY_LINE,
        ],
      };
    case "SYSTEM_ERROR":
    case "RUNTIME_ERROR":
      return {
        glyph: "⚠",
        title: "Runtime error",
        reason: failure.error,
        lines: [RETRY_LINE],
      };
    case "INTERRUPTED":
      return {
        glyph: "⚠",
        title: "Interrupted",
        reason: null,
        lines: [
          "The execution ended before a final outcome was recorded.",
          RETRY_LINE,
        ],
      };
  }
}

/**
 * Whether the execution-level failure panel is visible: the failure is
 * current only while the workspace is unfinished (OPEN/ERROR — never
 * SOLVED/RUNNING), and only when no attempt supersedes it. When timestamps
 * are missing or incomparable, show it — the honest default.
 */
export function showExecutionFailure(model: WorkspaceReadModel): boolean {
  const failure = model.last_execution_failure;
  if (failure === null) return false;
  if (model.display_status !== "OPEN" && model.display_status !== "ERROR") {
    return false;
  }
  if (model.attempts.length === 0) return true;
  if (failure.finished_at === null) return true;
  const latestFinished = model.attempts[model.attempts.length - 1]?.finished_at ?? null;
  if (latestFinished === null) return true;
  return failure.finished_at >= latestFinished;
}
