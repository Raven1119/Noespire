import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getProblem } from "../api";
import type { WorkspaceReadModel } from "../types";
import { KatexStatement } from "../components/KatexStatement";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { StatusBadge } from "../components/StatusBadge";

type Tab = "proof" | "attempts";

/**
 * Minimal workspace shell (Slice 2): back link, statement, status, and the
 * empty `Proof | Attempts` tab bar. Slice 4 builds the real panes; until then
 * they hold honest placeholders only.
 */
export function WorkspaceShell() {
  const { problemId } = useParams<{ problemId: string }>();
  const [model, setModel] = useState<WorkspaceReadModel | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [tab, setTab] = useState<Tab>("attempts");

  useEffect(() => {
    if (!problemId) return;
    setModel(null);
    setError(null);
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
        <div className="workspace-header">
          <StatusBadge status={model.display_status} />
          {model.status === "SOLVED" && <LlmVerifiedBadge />}
        </div>
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
          {tab === "proof"
            ? "The proof document appears here once the problem is solved."
            : "Attempts appear here once the first attempt has run."}
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
