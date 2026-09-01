import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, forkProblem } from "../api";

interface ForkDialogProps {
  problemId: string;
  /** Current statement — the fork textarea starts prefilled with it. */
  statement: string;
  onClose: () => void;
}

/**
 * Revise & Fork dialog (spec §6/§9, ADR-0001: revision is fork, never edit).
 * Fork is version identity, not a diff validator — an identical statement is
 * allowed; only a blank statement is blocked client-side. Server failures
 * (400/404/network) render inline and the dialog STAYS open. Success (201)
 * navigates to the new problem's workspace. Dialog semantics follow the
 * InspectorDrawer pattern: role=dialog, aria-modal, Esc closes, focus moves
 * into the dialog on open and returns to the trigger on close.
 */
export function ForkDialog({ problemId, statement, onClose }: ForkDialogProps) {
  const [value, setValue] = useState(statement);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    textareaRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused?.focus?.();
    };
  }, [onClose]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await forkProblem(problemId, value.trim());
      onClose();
      navigate(`/problems/${created.problem_id}`);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : "Could not create the fork. Try again."
      );
      setSubmitting(false);
    }
  }

  const blank = value.trim().length === 0;

  return (
    <>
      <div className="inspector-scrim" onClick={onClose} />
      <form
        className="fork-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Revise & Fork"
        onSubmit={handleSubmit}
      >
        <h2 className="fork-dialog__title">Revise &amp; Fork</h2>
        <p className="fork-dialog__note">
          Creates a new problem derived from this one. The original is never
          modified.
        </p>
        <label className="fork-dialog__label" htmlFor="fork-statement">
          Fork statement
        </label>
        <textarea
          id="fork-statement"
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          rows={5}
        />
        {error !== null && (
          <p className="fork-dialog__error" role="alert">
            {error}
          </p>
        )}
        <div className="fork-dialog__actions">
          <button
            className="button button--primary"
            type="submit"
            disabled={blank || submitting}
          >
            {submitting ? "Creating…" : "Create fork"}
          </button>
          <button className="button" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </>
  );
}
