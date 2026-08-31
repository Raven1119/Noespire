// THROWAWAY PROTOTYPE — badges and glyphs. Color semantics are reserved:
// blue-cyan = LLM-verified/SOLVED (never green), amber = OPEN, blue pulse =
// RUNNING, red = runtime error (ADR-0004).
import type { AttemptEvidence, DisplayStatus, FailureClass } from '../fixtures'
import { failureClass } from '../fixtures'

export function StatusBadge({ status }: { status: DisplayStatus }) {
  switch (status) {
    case 'SOLVED':
      return <span className="badge badge-solved">Solved</span>
    case 'OPEN':
      return <span className="badge badge-open">Open</span>
    case 'RUNNING':
      return (
        <span className="badge badge-running">
          <span className="live-dot" /> Running
        </span>
      )
    case 'ERROR':
      return <span className="badge badge-error">Open · runtime error</span>
  }
}

/** ADR-0004: always "LLM-verified", never bare "Verified", never green. */
export function LlmVerifiedBadge() {
  return (
    <span className="badge badge-llm" title="Verified by a fresh LLM session — not kernel-verified">
      LLM-verified
    </span>
  )
}

export const FAILURE_META: Record<
  FailureClass,
  { glyph: string; label: string; suggestion: string }
> = {
  contract: {
    glyph: '≠',
    label: 'Contract failure',
    suggestion:
      'The proposal violated the submission contract — the fresh verifier was never called. Suggested next: Revise & Fork with a sharpened statement, or Retry.',
  },
  rejection: {
    glyph: '✕',
    label: 'Verification rejection',
    suggestion: 'Suggested next: Retry — the obligation is back to OPEN and the verifier’s gap is kept as evidence.',
  },
  runtime: {
    glyph: '⚠',
    label: 'Runtime error',
    suggestion: 'Suggested next: Retry — no mathematical content was produced.',
  },
}

/** Per-attempt glyph for timelines: reflects verdict + derived failure class. */
export function AttemptGlyph({ attempt }: { attempt: AttemptEvidence }) {
  const fc = failureClass(attempt)
  if (attempt.verdict === 'PASS') return <span className="attempt-glyph ag-pass">✓</span>
  if (attempt.verdict === 'RUNNING') return <span className="attempt-glyph"><span className="live-dot" /></span>
  if (fc === 'contract') return <span className="attempt-glyph ag-contract">≠</span>
  if (fc === 'rejection') return <span className="attempt-glyph ag-fail">✕</span>
  return <span className="attempt-glyph ag-error">⚠</span>
}
