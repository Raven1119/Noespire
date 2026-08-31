import type { Attempt, FailureClass } from "../types";

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
