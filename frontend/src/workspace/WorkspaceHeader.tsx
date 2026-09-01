import { useState } from "react";
import { Link } from "react-router-dom";
import { KatexStatement } from "../components/KatexStatement";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { StatusBadge } from "../components/StatusBadge";
import type { WorkspaceReadModel } from "../types";
import { ForkDialog } from "./ForkDialog";

export interface DerivedFromInfo {
  problem_id: string;
  /** Parent statement when listProblems() resolves it; null → plain-text id. */
  statement: string | null;
}

interface WorkspaceHeaderProps {
  model: WorkspaceReadModel;
  starting: boolean;
  onStartAttempt: () => void;
  onOpenInspector: () => void;
  derivedFrom: DerivedFromInfo | null;
  archiving: boolean;
  onToggleArchive: () => void;
}

/**
 * Workspace header (spec §9): serif KaTeX statement, status badge, the
 * LLM-verified badge ONLY when SOLVED, and state-gated actions — fresh OPEN
 * (no attempts, no execution-level failure) → "Start proving"; OPEN/ERROR/
 * interrupted/failed runs → "Retry"; RUNNING
 * → Retry disabled with an honest hint; SOLVED → no retry action. "Revise &
 * Fork" opens the fork dialog (allowed in every state — forking a RUNNING
 * parent never blocks or stops its execution). Archive/Unarchive is a
 * metadata-only toggle shown as a SECONDARY "Archived" badge; the main
 * status badge stays OPEN/RUNNING/SOLVED. Machine metadata stays out of the
 * header (ADR-0003) — the ⓘ button opens the Inspector drawer.
 */
export function WorkspaceHeader({
  model,
  starting,
  onStartAttempt,
  onOpenInspector,
  derivedFrom,
  archiving,
  onToggleArchive,
}: WorkspaceHeaderProps) {
  const [forkOpen, setForkOpen] = useState(false);
  const solved = model.status === "SOLVED";
  const running = model.status === "RUNNING";
  // An execution-level failure (e.g. architect-stage) leaves no attempts but
  // is still a failed run — the action is "Retry", not "Start proving".
  const noAttempts =
    model.attempts.length === 0 && model.last_execution_failure === null;

  return (
    <header className="workspace-header-block">
      <div className="workspace-header">
        <StatusBadge status={model.display_status} />
        {model.archived && <span className="badge badge--archived">Archived</span>}
        {solved && <LlmVerifiedBadge />}
        <div className="workspace-actions">
          {!solved && (
            <>
              <button
                className="button button--primary"
                disabled={running || starting}
                onClick={onStartAttempt}
              >
                {noAttempts ? "Start proving" : "Retry"}
              </button>
              {running && (
                <span className="workspace-actions__hint">
                  An attempt is already running.
                </span>
              )}
            </>
          )}
          <button className="button" onClick={() => setForkOpen(true)}>
            Revise &amp; Fork
          </button>
          <button
            className="button"
            disabled={archiving}
            onClick={onToggleArchive}
          >
            {model.archived ? "Unarchive" : "Archive"}
          </button>
          <button
            className="button button--icon"
            aria-label="Open inspector"
            title="Inspector"
            onClick={onOpenInspector}
          >
            ⓘ
          </button>
        </div>
      </div>
      <p className="workspace-statement">
        <KatexStatement statement={model.statement} />
      </p>
      {derivedFrom !== null && (
        <p className="workspace-lineage">
          Derived from{" "}
          {derivedFrom.statement !== null ? (
            <Link to={`/problems/${derivedFrom.problem_id}`}>
              {snippet(derivedFrom.statement)}
            </Link>
          ) : (
            derivedFrom.problem_id
          )}
        </p>
      )}
      {forkOpen && (
        <ForkDialog
          problemId={model.problem_id}
          statement={model.statement}
          onClose={() => setForkOpen(false)}
        />
      )}
    </header>
  );
}

function snippet(statement: string): string {
  return statement.length > 80 ? `${statement.slice(0, 77)}…` : statement;
}
