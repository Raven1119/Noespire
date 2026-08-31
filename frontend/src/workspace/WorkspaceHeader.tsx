import { Link } from "react-router-dom";
import { KatexStatement } from "../components/KatexStatement";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { StatusBadge } from "../components/StatusBadge";
import type { WorkspaceReadModel } from "../types";

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
}

/**
 * Workspace header (spec §9): serif KaTeX statement, status badge, the
 * LLM-verified badge ONLY when SOLVED, and state-gated actions — fresh OPEN
 * (no attempts) → "Start proving"; OPEN/ERROR/interrupted → "Retry"; RUNNING
 * → Retry disabled with an honest hint; SOLVED → no retry action. "Revise &
 * Fork" is a disabled stub until Slice 5. Machine metadata stays out of the
 * header (ADR-0003) — the ⓘ button opens the Inspector drawer.
 */
export function WorkspaceHeader({
  model,
  starting,
  onStartAttempt,
  onOpenInspector,
  derivedFrom,
}: WorkspaceHeaderProps) {
  const solved = model.status === "SOLVED";
  const running = model.status === "RUNNING";
  const noAttempts = model.attempts.length === 0;

  return (
    <header className="workspace-header-block">
      <div className="workspace-header">
        <StatusBadge status={model.display_status} />
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
          <button
            className="button"
            disabled
            title="Coming in the next slice"
          >
            Revise &amp; Fork
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
    </header>
  );
}

function snippet(statement: string): string {
  return statement.length > 80 ? `${statement.slice(0, 77)}…` : statement;
}
