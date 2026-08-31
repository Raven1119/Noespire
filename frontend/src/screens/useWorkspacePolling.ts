import { useEffect } from "react";
import type { ProblemStatus } from "../types";

export const POLL_INTERVAL_MS = 1500;

/**
 * Refetch the workspace read model while it is RUNNING (spec §7.1). Terminal
 * states never poll; the interval is cleared on unmount and as soon as the
 * status leaves RUNNING. Plain HTTP polling — no WebSocket/SSE (§12).
 */
export function useWorkspacePolling(
  status: ProblemStatus | null,
  onPoll: () => void
): void {
  const running = status === "RUNNING";
  useEffect(() => {
    if (!running) return;
    const id = setInterval(onPoll, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [running, onPoll]);
}
