// THROWAWAY PROTOTYPE — Variant B "Explicit tabs": persistent tab bar
// Proof | Attempts (+ disabled "Graph — future" to test additive growth,
// ADR-0002). State only picks the DEFAULT tab; the user can switch freely.
// RUNNING shows a "current attempt" banner on top of the Attempts tab.
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
  CandidateBlock,
  ClosureList,
  ElapsedLine,
  EmptyProof,
  FactBrowser,
  FailurePanel,
} from '../components/ProofBits'
import { useInspector } from '../components/Inspector'
import { attemptInspector } from '../inspectorContent'
import type { VariantProps } from './VariantA'

type Tab = 'proof' | 'attempts'

export function VariantB({ model, elapsed }: VariantProps) {
  const status = displayStatus(model)
  const [tab, setTab] = useState<Tab>(status === 'SOLVED' ? 'proof' : 'attempts')
  return (
    <div>
      <div className="tabbar" role="tablist">
        <button
          role="tab"
          aria-selected={tab === 'proof'}
          className={`tab${tab === 'proof' ? ' tab-active' : ''}`}
          onClick={() => setTab('proof')}
        >
          Proof
        </button>
        <button
          role="tab"
          aria-selected={tab === 'attempts'}
          className={`tab${tab === 'attempts' ? ' tab-active' : ''}`}
          onClick={() => setTab('attempts')}
        >
          Attempts
        </button>
        <button className="tab tab-disabled" disabled title="Research Graph — a future view inside the workspace (ADR-0002)">
          Graph<span className="tab-future">future</span>
        </button>
      </div>

      {tab === 'proof' ? (
        status === 'SOLVED' ? (
          <>
            <FactBrowser model={model} />
            <ClosureList model={model} />
          </>
        ) : (
          <EmptyProof model={model} />
        )
      ) : (
        <AttemptsTab model={model} elapsed={elapsed} />
      )}
    </div>
  )
}

function AttemptsTab({ model, elapsed }: { model: WorkspaceModel; elapsed: string }) {
  const running = model.obligation.status === 'RUNNING' ? latestAttempt(model) : undefined
  return (
    <div>
      {running && (
        <div className="current-banner">
          <span className="live-dot" />
          <span>
            Current attempt —{' '}
            {runningPhase(running) === 'generating' ? 'Generating candidate…' : 'Checking candidate…'}
            <span style={{ color: 'hsl(var(--text-tertiary))' }}> · phase inferred</span>
          </span>
          <ElapsedLine elapsed={elapsed} />
        </div>
      )}
      {[...model.attempts].reverse().map((a) => (
        <AttemptEntry key={a.attempt_id} model={model} attempt={a} />
      ))}
    </div>
  )
}

function AttemptEntry({ model, attempt }: { model: WorkspaceModel; attempt: AttemptEvidence }) {
  const [open, setOpen] = useState(false)
  const inspector = useInspector()
  const index = model.attempts.indexOf(attempt)
  const fc = failureClass(attempt)
  return (
    <div className="attempt-entry">
      <button type="button" className="attempt-entry-head" onClick={() => setOpen((v) => !v)}>
        <AttemptGlyph attempt={attempt} />
        <span className="attempt-entry-title">Attempt {index + 1}</span>
        <span className="attempt-entry-verdict">
          {attempt.verdict}
          {fc ? ` · ${FAILURE_META[fc].label.toLowerCase()}` : ''}
          {attempt.verdict === 'PASS' ? ' · LLM-verified' : ''}
        </span>
        <span className="attempt-entry-chevron">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="attempt-entry-body">
          {attempt.candidate_artifact && <CandidateBlock artifact={attempt.candidate_artifact} />}
          {fc && <FailurePanel model={model} attempt={attempt} />}
          {attempt.verdict === 'PASS' && attempt.verifier_artifact && (
            <p style={{ fontSize: 12.5, color: 'hsl(var(--text-secondary))' }}>
              Accepted by a fresh LLM verifier: {attempt.verifier_artifact.reason}
            </p>
          )}
          {!attempt.candidate_artifact && !fc && attempt.verdict !== 'PASS' && (
            <p style={{ fontSize: 12.5, color: 'hsl(var(--text-tertiary))' }}>
              No candidate artifact yet.
            </p>
          )}
          <div style={{ marginTop: 10 }}>
            <button
              className="btn btn-ghost"
              onClick={() => inspector.open(attemptInspector(model, attempt, index))}
            >
              ⓘ Inspect this attempt
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
