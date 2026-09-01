import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, createProblem, listProblems } from "../api";
import type { ProblemSummary } from "../types";
import { KatexStatement } from "../components/KatexStatement";
import { StatusBadge } from "../components/StatusBadge";

function formatActivity(iso: string | null): string {
  if (iso === null) return "No activity yet";
  return `Last activity ${new Date(iso).toLocaleString()}`;
}

function ProblemRow({
  problem,
  parentStatement,
}: {
  problem: ProblemSummary;
  /** Parent statement resolved from the same list payload; null → raw id. */
  parentStatement: string | null;
}) {
  return (
    <li className="problem-row-item">
      <Link className="problem-row" to={`/problems/${problem.problem_id}`}>
        <div className="problem-row__statement">
          <KatexStatement statement={problem.statement} />
        </div>
        <div className="problem-row__meta">
          <StatusBadge status={problem.display_status} />
          <span>
            {problem.attempt_count === 1
              ? "1 attempt"
              : `${problem.attempt_count} attempts`}
          </span>
          <span>{formatActivity(problem.last_activity)}</span>
        </div>
      </Link>
      {problem.derived_from !== null && (
        <span className="problem-row__lineage">
          Derived from{" "}
          <Link to={`/problems/${problem.derived_from}`}>
            {parentStatement !== null
              ? snippet(parentStatement)
              : problem.derived_from}
          </Link>
        </span>
      )}
    </li>
  );
}

function snippet(statement: string): string {
  return statement.length > 80 ? `${statement.slice(0, 77)}…` : statement;
}

function NewProblemForm({ onCancel }: { onCancel: () => void }) {
  const [statement, setStatement] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await createProblem(statement.trim());
      navigate(`/problems/${created.problem_id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setError(err.message);
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Could not create the problem. Try again."
        );
      }
      setSubmitting(false);
    }
  }

  return (
    <form className="new-problem-form" onSubmit={handleSubmit}>
      <label htmlFor="new-problem-statement">
        Mathematical problem / theorem statement
      </label>
      <textarea
        id="new-problem-statement"
        value={statement}
        onChange={(e) => setStatement(e.target.value)}
        placeholder="Every even perfect number is triangular."
        autoFocus
      />
      {error !== null && (
        <p className="new-problem-form__error" role="alert">
          {error}
        </p>
      )}
      <div className="new-problem-form__actions">
        <button className="button button--primary" type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create Problem"}
        </button>
        <button className="button" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

export function Home() {
  const [problems, setProblems] = useState<ProblemSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(() => {
    setError(null);
    listProblems()
      .then((data) => setProblems(data.problems))
      .catch((err: unknown) =>
        setError(
          err instanceof Error
            ? err.message
            : "Could not load problems. Try again."
        )
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = (problems ?? []).filter((p) => showArchived || !p.archived);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1 className="app-title">Noespire</h1>
        <button
          className="button button--primary"
          onClick={() => setFormOpen((open) => !open)}
        >
          + New Problem
        </button>
      </header>

      {formOpen && <NewProblemForm onCancel={() => setFormOpen(false)} />}

      {error !== null ? (
        <div className="state-message state-message--error">
          <p className="state-message__title">Could not load problems</p>
          <p>{error}</p>
          <button className="button" onClick={load}>
            Retry
          </button>
        </div>
      ) : problems === null ? (
        <div className="state-message">
          <p>Loading problems…</p>
        </div>
      ) : (
        <>
          {problems.length === 0 ? (
            <div className="state-message">
              <p>No problems yet.</p>
              <p>Create your first mathematical problem.</p>
            </div>
          ) : (
            <>
              <label className="archive-toggle">
                <input
                  type="checkbox"
                  checked={showArchived}
                  onChange={(e) => setShowArchived(e.target.checked)}
                />
                Show archived
              </label>
              {visible.length === 0 ? (
                <div className="state-message">
                  <p>All problems are archived.</p>
                </div>
              ) : (
                <ul className="problem-list">
                  {visible.map((problem) => (
                    <ProblemRow
                      key={problem.problem_id}
                      problem={problem}
                      parentStatement={
                        problem.derived_from !== null
                          ? (problems.find(
                              (item) => item.problem_id === problem.derived_from
                            )?.statement ?? null)
                          : null
                      }
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
