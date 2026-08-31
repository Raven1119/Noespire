import type { DisplayStatus } from "../types";

const LABELS: Record<DisplayStatus, string> = {
  OPEN: "Open",
  RUNNING: "Running",
  SOLVED: "Solved",
  ERROR: "Error",
};

/**
 * Problem status badge. Colors follow the frozen discipline: SOLVED renders
 * blue-cyan (never green — green is reserved for a future kernel-verified
 * state, ADR-0004), OPEN amber, RUNNING blue, ERROR red.
 */
export function StatusBadge({ status }: { status: DisplayStatus }) {
  return (
    <span className={`badge badge--${status.toLowerCase()}`}>
      {LABELS[status]}
    </span>
  );
}
