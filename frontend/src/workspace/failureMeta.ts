import type { FailureClass } from "../types";

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
