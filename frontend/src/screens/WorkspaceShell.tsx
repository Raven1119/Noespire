import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getProblem, listProblems, setProblemArchived, startAttempt } from "../api";
import type { WorkspaceReadModel } from "../types";
import { InspectorDrawer } from "../inspector/InspectorDrawer";
import type { Inspection } from "../inspector/inspectionContent";
import { drawerContent } from "../inspector/inspectionContent";
import { AttemptsTab } from "../workspace/AttemptsTab";
import { ProofTab } from "../workspace/ProofTab";
import { WorkspaceHeader } from "../workspace/WorkspaceHeader";
import type { DerivedFromInfo } from "../workspace/WorkspaceHeader";
import { useWorkspacePolling } from "./useWorkspacePolling";

type Tab = "proof" | "attempts";

/**
 * Workspace shell: header with state-gated actions, `Proof | Attempts` tabs,
 * polling while RUNNING, and the Inspector drawer. State decides only the
 * default tab (applied on initial load / problemId change); the user's manual
 * tab choice is never overridden by polling or status transitions (spec §9).
 */
export function WorkspaceShell() {
  const { problemId } = useParams<{ problemId: string }>();
  const [model, setModel] = useState<WorkspaceReadModel | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState<Tab>("attempts");
  const [starting, setStarting] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [derivedFrom, setDerivedFrom] = useState<DerivedFromInfo | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);

  useEffect(() => {
    if (!problemId) return;
    setModel(null);
    setError(null);
    setStartError(null);
    setInspection(null);
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

  // Resolve the lineage link target against the problem list; failure or a
  // missing parent falls back to the plain-text id (never blocks the header).
  const derivedFromId = model?.derived_from ?? null;
  useEffect(() => {
    if (derivedFromId === null) {
      setDerivedFrom(null);
      return;
    }
    let cancelled = false;
    listProblems()
      .then((response) => {
        if (cancelled) return;
        const parent = response.problems.find(
          (item) => item.problem_id === derivedFromId
        );
        setDerivedFrom({
          problem_id: derivedFromId,
          statement: parent?.statement ?? null,
        });
      })
      .catch(() => {
        if (!cancelled) setDerivedFrom({ problem_id: derivedFromId, statement: null });
      });
    return () => {
      cancelled = true;
    };
  }, [derivedFromId]);

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

  // Archive is metadata-only (spec §6): toggle, then refetch the read model
  // in place — no redirect, no execution interaction.
  const handleToggleArchive = useCallback(async (): Promise<void> => {
    if (!problemId || !model || archiving) return;
    setStartError(null);
    setArchiving(true);
    try {
      await setProblemArchived(problemId, !model.archived);
      await refresh();
    } catch (err: unknown) {
      setStartError(
        err instanceof ApiError
          ? err.message
          : "Could not update the archive flag. Try again."
      );
    } finally {
      setArchiving(false);
    }
  }, [problemId, model, archiving, refresh]);

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
    body = (
      <>
        <WorkspaceHeader
          model={model}
          starting={starting}
          onStartAttempt={() => void handleStartAttempt()}
          onOpenInspector={() => setInspection({ kind: "problem" })}
          derivedFrom={derivedFrom}
          archiving={archiving}
          onToggleArchive={() => void handleToggleArchive()}
        />
        {startError !== null && (
          <p className="workspace-actions__error" role="alert">
            {startError}
          </p>
        )}
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
            <ProofTab
              model={model}
              onInspectFact={(fact) => setInspection({ kind: "fact", fact })}
            />
          ) : (
            <AttemptsTab
              model={model}
              onInspectAttempt={(attempt, ordinal) =>
                setInspection({ kind: "attempt", attempt, ordinal })
              }
            />
          )}
        </div>
        {inspection !== null && (
          <InspectorDrawer
            {...drawerContent(model, inspection)}
            onClose={() => setInspection(null)}
          />
        )}
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
