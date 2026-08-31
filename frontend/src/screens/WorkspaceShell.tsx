import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getProblem, startAttempt } from "../api";
import type { WorkspaceReadModel } from "../types";
import { KatexStatement } from "../components/KatexStatement";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { RunningIndicator } from "../components/RunningIndicator";
import { StatusBadge } from "../components/StatusBadge";
import { FAILURE_CLASS_LABELS } from "../workspace/failureMeta";
import { useWorkspacePolling } from "./useWorkspacePolling";

type Tab = "proof" | "attempts";

/**
 * Workspace shell (Slice 3): header with state-gated start/Retry action,
 * `Proof | Attempts` tabs, polling while RUNNING, and a minimal RUNNING /
 * latest-attempt display. Slice 4 builds the real tab panes; until then they
 * hold honest minimal content only.
 */
export function WorkspaceShell() {
  const { problemId } = useParams<{ problemId: string }>();
  const [model, setModel] = useState<WorkspaceReadModel | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState<Tab>("attempts");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    if (!problemId) return;
    setModel(null);
    setError(null);
    setStartError(null);
    getProblem(problemId)
      .then((data) => {
        setModel(data);
        // State decides only the default tab: SOLVED → Proof, else Attempts.
        setTab(data.status === "SOLVED" ? "proof" : "attempts");
      })
      .catch((err: unknown) =>
        setError(
          err instanceof ApiError
            ? err
            : new ApiError(null, "Could not load this problem. Try again.")
        )
      );
  }, [problemId]);

  // Interval polling swallows transient failures: the last known state stays
  // on screen and the next tick retries.
  const poll = useCallback((): void => {
    if (!problemId) return;
    getProblem(problemId)
      .then(setModel)
      .catch(() => undefined);
  }, [problemId]);

  useWorkspacePolling(model?.status ?? null, poll);

  // User-triggered refresh surfaces failures inline instead of silently.
  const refresh = useCallback((): Promise<void> => {
    if (!problemId) return Promise.resolve();
    return getProblem(problemId)
      .then(setModel)
      .catch(() =>
        setStartError(
          "Could not refresh the workspace. Reload the page to see the latest state."
        )
      );
  }, [problemId]);

  const handleStartAttempt = useCallback(async (): Promise<void> => {
    if (!problemId || starting) return;
    setStartError(null);
    setStarting(true);
    try {
      await startAttempt(problemId);
      // 202 accepted — refetch to pick up RUNNING; polling takes over.
      await refresh();
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409 && err.code === "already_running") {
        // Someone else started it — follow the run by polling as usual.
        await refresh();
      } else if (err instanceof ApiError && err.status === 409 && err.code === "already_solved") {
        // Single refetch to show the solved state; no polling follows.
        await refresh();
      } else if (err instanceof ApiError && err.status === 404) {
        setStartError(
          "The server does not know this problem (404). Nothing is ever deleted — it may never have existed."
        );
      } else {
        setStartError(
          err instanceof ApiError
            ? err.message
            : "Could not start the attempt. Try again."
        );
      }
    } finally {
      setStarting(false);
    }
  }, [problemId, starting, refresh]);

  let body: React.ReactNode;
  if (error !== null) {
    body =
      error.status === 404 ? (
        <div className="state-message">
          <p>Problem not found.</p>
          <p>It may never have existed — nothing is ever deleted.</p>
        </div>
      ) : (
        <div className="state-message state-message--error">
          <p className="state-message__title">Could not load this problem</p>
          <p>{error.message}</p>
          <button
            className="button"
            onClick={() => {
              setError(null);
              if (problemId) {
                getProblem(problemId)
                  .then(setModel)
                  .catch((err: unknown) =>
                    setError(
                      err instanceof ApiError
                        ? err
                        : new ApiError(null, "Could not load this problem. Try again.")
                    )
                  );
              }
            }}
          >
            Retry
          </button>
        </div>
      );
  } else if (model === null) {
    body = (
      <div className="state-message">
        <p>Loading problem…</p>
      </div>
    );
  } else {
    const latestAttempt =
      model.attempts.length > 0 ? model.attempts[model.attempts.length - 1] : null;
    body = (
      <>
        <div className="workspace-header">
          <StatusBadge status={model.display_status} />
          {model.status === "SOLVED" && <LlmVerifiedBadge />}
          {model.status !== "SOLVED" && (
            <div className="workspace-actions">
              <button
                className="button button--primary"
                disabled={model.status === "RUNNING" || starting}
                onClick={() => void handleStartAttempt()}
              >
                {latestAttempt === null ? "Start attempt" : "Retry"}
              </button>
              {model.status === "RUNNING" && (
                <span className="workspace-actions__hint">
                  An attempt is already running.
                </span>
              )}
            </div>
          )}
        </div>
        {startError !== null && (
          <p className="workspace-actions__error" role="alert">
            {startError}
          </p>
        )}
        <p className="workspace-statement">
          <KatexStatement statement={model.statement} />
        </p>
        <div className="workspace-tabs" role="tablist">
          <button
            className="workspace-tab"
            role="tab"
            aria-selected={tab === "proof"}
            onClick={() => setTab("proof")}
          >
            Proof
          </button>
          <button
            className="workspace-tab"
            role="tab"
            aria-selected={tab === "attempts"}
            onClick={() => setTab("attempts")}
          >
            Attempts
          </button>
        </div>
        <div className="workspace-pane" role="tabpanel">
          {tab === "proof" ? (
            "The proof document appears here once the problem is solved."
          ) : model.status === "RUNNING" ? (
            <RunningIndicator phaseHint={model.running_phase_hint} />
          ) : latestAttempt !== null ? (
            <p className="attempt-line">
              Latest attempt {latestAttempt.attempt_id}: {latestAttempt.verdict}
              {latestAttempt.failure_class !== null &&
                ` — ${FAILURE_CLASS_LABELS[latestAttempt.failure_class]}`}
            </p>
          ) : (
            "Attempts appear here once the first attempt has run."
          )}
        </div>
      </>
    );
  }

  return (
    <div className="app-shell">
      <Link className="back-link" to="/">
        ← Problems
      </Link>
      {body}
    </div>
  );
}
