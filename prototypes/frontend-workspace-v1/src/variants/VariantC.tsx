// THROWAWAY PROTOTYPE — Variant C "Document + evidence rail": the proof
// document (or its empty state) always owns the center; a persistent ~260px
// LEFT rail holds the attempt timeline (newest first, expandable). No tabs,
// no state-switched canvas — state only changes what the center shows.
import { useState } from 'react'
import {
  displayStatus,
  failureClass,
  latestAttempt,
  runningPhase,
  type AttemptEvidence,
  type WorkspaceModel,
} from '../fixtures'
import { AttemptGlyph, FAILURE_META } from '../components/Badges'
import {
  ClosureList,
  ElapsedLine,
  EmptyProof,
  FactBrowser,
} from '../components/ProofBits'
import { useInspector } from '../components/Inspector'
import { MathText } from '../components/Katex'
import { attemptInspector } from '../inspectorContent'
import type { VariantProps } from './VariantA'

export function VariantC({ model, elapsed }: VariantProps) {
  const status = displayStatus(model)
  return (
    <div className="vc-grid">
      <aside className="rail">
        <h3 className="section-label">Attempts · newest first</h3>
        <RailCurrent model={model} elapsed={elapsed} />
        {[...model.attempts].reverse().map((a) => (
          <RailEntry key={a.attempt_id} model={model} attempt={a} />
        ))}
      </aside>
      <div>
        {status === 'SOLVED' ? (
          <>
            <FactBrowser model={model} />
            <ClosureList model={model} />
          </>
        ) : (
          <EmptyProof model={model} />
        )}
      </div>
    </div>
  )
}

function RailCurrent({ model, elapsed }: { model: WorkspaceModel; elapsed: string }) {
  if (model.obligation.status !== 'RUNNING') return null
  const running = latestAttempt(model)
  if (!running) return null
  return (
    <div className="rail-current">
      <span className="live-dot" />{' '}
      {runningPhase(running) === 'generating' ? 'Generating candidate…' : 'Checking candidate…'}
      <div style={{ color: 'hsl(var(--text-tertiary))', fontSize: 10.5 }}>live · phase inferred</div>
      <ElapsedLine elapsed={elapsed} />
    </div>
  )
}

function RailEntry({ model, attempt }: { model: WorkspaceModel; attempt: AttemptEvidence }) {
  const [open, setOpen] = useState(false)
  const inspector = useInspector()
  const index = model.attempts.indexOf(attempt)
  const fc = failureClass(attempt)
  const snippet = attempt.candidate_artifact?.statement
  const reason = attempt.verifier_artifact?.reason ?? attempt.error ?? null
  return (
    <div className="rail-entry">
      <button type="button" className="rail-entry-head" onClick={() => setOpen((v) => !v)}>
        <AttemptGlyph attempt={attempt} />
        <span>
          <span className="rail-entry-title">Attempt {index + 1}</span>
          <br />
          <span className="rail-entry-verdict">
            {attempt.verdict}
            {fc ? ` · ${FAILURE_META[fc].label.toLowerCase()}` : ''}
          </span>
        </span>
      </button>
      {open && (
        <div className="rail-entry-body">
          {snippet && (
            <div className="snippet">
              <MathText text={snippet.length > 140 ? snippet.slice(0, 140) + '…' : snippet} />
            </div>
          )}
          {reason && (
            <div>
              <MathText text={reason.length > 200 ? reason.slice(0, 200) + '…' : reason} />
            </div>
          )}
          {!snippet && !reason && <div>No artifacts yet.</div>}
          <div style={{ marginTop: 6 }}>
            <button
              className="btn btn-ghost"
              style={{ fontSize: 11, padding: '3px 8px' }}
              onClick={() => inspector.open(attemptInspector(model, attempt, index))}
            >
              ⓘ Inspect
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
