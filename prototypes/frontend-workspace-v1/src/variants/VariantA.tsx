// THROWAWAY PROTOTYPE — Variant A "Status stage": no tabs, one central canvas
// whose content morphs entirely by state. SOLVED → proof document + closure;
// OPEN → latest attempt (candidate + failure evidence) with collapsed attempt
// history at the bottom; RUNNING → phase indicator. Header stays constant.
import { useState } from 'react'
import {
  displayStatus,
  failureClass,
  latestAttempt,
  type AttemptEvidence,
  type WorkspaceModel,
} from '../fixtures'
import { AttemptGlyph, FAILURE_META } from '../components/Badges'
import {
  CandidateBlock,
  ClosureList,
  FactBrowser,
  FailurePanel,
  RunningIndicator,
} from '../components/ProofBits'
import { useInspector } from '../components/Inspector'
import { MathText } from '../components/Katex'
import { attemptInspector } from '../inspectorContent'

export interface VariantProps {
  model: WorkspaceModel
  elapsed: string
}

export function VariantA({ model, elapsed }: VariantProps) {
  const status = displayStatus(model)
  return (
    <div>
      {status === 'SOLVED' && (
        <>
          <FactBrowser model={model} />
          <ClosureList model={model} />
        </>
      )}
      {(status === 'OPEN' || status === 'ERROR') && <OpenStage model={model} />}
      {status === 'RUNNING' && (
        <div className="phase-panel">
          <RunningIndicator model={model} elapsed={elapsed} />
        </div>
      )}
    </div>
  )
}

function OpenStage({ model }: { model: WorkspaceModel }) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const latest = latestAttempt(model)
  if (!latest) return null
  const fc = failureClass(latest)
  return (
    <div>
      <h3 className="section-label">
        Latest attempt{fc ? ` — ${FAILURE_META[fc].label.toLowerCase()}` : ''}
      </h3>
      {latest.candidate_artifact ? (
        <CandidateBlock artifact={latest.candidate_artifact} />
      ) : (
        <p style={{ fontSize: 12.5, color: 'hsl(var(--text-tertiary))', margin: '0 0 4px' }}>
          No candidate artifact was produced in this attempt.
        </p>
      )}
      <FailurePanel model={model} attempt={latest} />

      {model.attempts.length > 1 && (
        <div style={{ marginTop: 28 }}>
          <button className="fork-toggle" style={{ fontSize: 12 }} onClick={() => setHistoryOpen((v) => !v)}>
            {historyOpen ? '▾' : '▸'} Attempt history ({model.attempts.length - 1} earlier)
          </button>
          {historyOpen && (
            <div style={{ marginTop: 10 }}>
              {[...model.attempts]
                .slice(0, -1)
                .reverse()
                .map((a) => (
                  <HistoryRow key={a.attempt_id} model={model} attempt={a} />
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function HistoryRow({ model, attempt }: { model: WorkspaceModel; attempt: AttemptEvidence }) {
  const inspector = useInspector()
  const index = model.attempts.indexOf(attempt)
  const fc = failureClass(attempt)
  const preview = attempt.verifier_artifact?.reason ?? attempt.error ?? 'no verifier artifact'
  return (
    <div className="attempt-entry">
      <button
        type="button"
        className="attempt-entry-head"
        onClick={() => inspector.open(attemptInspector(model, attempt, index))}
        title="Open in Inspector"
      >
        <AttemptGlyph attempt={attempt} />
        <span className="attempt-entry-title">Attempt {index + 1}</span>
        <span className="attempt-entry-verdict">
          {attempt.verdict}
          {fc ? ` · ${FAILURE_META[fc].label.toLowerCase()}` : ''}
        </span>
      </button>
      <div style={{ padding: '0 14px 10px 40px', fontSize: 12, color: 'hsl(var(--text-secondary))' }}>
        <MathText text={preview.length > 160 ? preview.slice(0, 160) + '…' : preview} />
      </div>
    </div>
  )
}
