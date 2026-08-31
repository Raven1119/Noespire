// THROWAWAY PROTOTYPE — shared LEAF content components. Variants own their
// layout; these leaves just render one object each in the correct register:
// verified = solid paper, candidate = dashed amber "Unverified" (ADR-0003).
import { useState } from 'react'
import type { AttemptEvidence, Fact, WorkspaceModel } from '../fixtures'
import { factLabel, failureClass, getFact, latestAttempt, runningPhase } from '../fixtures'
import { FAILURE_META, LlmVerifiedBadge } from './Badges'
import { useInspector } from './Inspector'
import { attemptInspector, factInspector } from '../inspectorContent'
import { MathParagraphs, MathText } from './Katex'

/**
 * Fact browsing with in-place swap: clicking a mathematical reference
 * ("by Lemma 1") swaps the document to that Fact, with a crumb back.
 * (Chosen over opening the drawer: the Inspector is for machine metadata.)
 */
export function FactBrowser({ model }: { model: WorkspaceModel }) {
  const targetId = model.obligation.resolved_by_fact_id
  const [focusId, setFocusId] = useState<string | null>(null)
  const focus = getFact(model, focusId ?? targetId ?? '')
  if (!focus) return null
  return (
    <div>
      {focus.fact_id !== targetId && targetId && (
        <button className="back-crumb" onClick={() => setFocusId(null)}>
          ← Back to main theorem
        </button>
      )}
      <ProofDocument model={model} fact={focus} onFactRef={setFocusId} />
    </div>
  )
}

/** One Verified Fact as a Proof Document (reader-facing, math only). */
export function ProofDocument({
  model,
  fact,
  onFactRef,
}: {
  model: WorkspaceModel
  fact: Fact
  onFactRef?: (id: string) => void
}) {
  const inspector = useInspector()
  return (
    <article className="doc">
      <div className="doc-head">
        <div className="doc-head-left">
          <span className="section-label" style={{ margin: 0 }}>
            {factLabel(model, fact.fact_id)}
          </span>
          <LlmVerifiedBadge />
        </div>
        <button
          className="icon-btn"
          title="Inspect this Fact"
          onClick={() => inspector.open(factInspector(model, fact))}
        >
          ⓘ
        </button>
      </div>
      <div className="doc-statement">
        <MathText text={fact.statement} />
      </div>
      <div className="doc-proof">
        <MathParagraphs text={fact.proof} onFactRef={onFactRef} />
      </div>
    </article>
  )
}

/** Supporting closure as an ordered list with a visible dependency chain. */
export function ClosureList({ model }: { model: WorkspaceModel }) {
  const inspector = useInspector()
  return (
    <section className="closure">
      <h3 className="section-label">Supporting closure · {model.closure_fact_ids.length} verified Facts</h3>
      {model.closure_fact_ids.map((id, i) => {
        const fact = getFact(model, id)
        if (!fact) return null
        const isTarget = model.obligation.resolved_by_fact_id === id
        return (
          <div key={id}>
            {i > 0 && <div className="closure-arrow">↑ depends on</div>}
            <button
              type="button"
              className={`closure-item${isTarget ? ' is-target' : ''}`}
              onClick={() => inspector.open(factInspector(model, fact))}
              title="Open in Inspector"
            >
              <span className="closure-step">{isTarget ? 'Target' : `Step ${i + 1}`}</span>
              <span className="closure-body">
                <span className="closure-statement">
                  <MathText text={fact.statement} />
                </span>
                <span className="closure-meta" style={{ display: 'block' }}>
                  {factLabel(model, id)} · LLM-verified
                </span>
              </span>
            </button>
          </div>
        )
      })}
    </section>
  )
}

/** Candidate proof in the unverified register — always with the banner. */
export function CandidateBlock({ artifact }: { artifact: NonNullable<AttemptEvidence['candidate_artifact']> }) {
  return (
    <div className="candidate">
      <div className="candidate-banner">
        <span>Unverified — candidate proof</span>
        <span>not a Fact</span>
      </div>
      <div className="candidate-body">
        <div className="candidate-statement">
          <MathText text={artifact.statement} />
        </div>
        <div className="candidate-proof">
          <MathParagraphs text={artifact.proof} />
        </div>
      </div>
    </div>
  )
}

/** Failure evidence: three classes, each with own label/glyph/next action. */
export function FailurePanel({ model, attempt }: { model: WorkspaceModel; attempt: AttemptEvidence }) {
  const inspector = useInspector()
  const index = model.attempts.indexOf(attempt)
  const fc = failureClass(attempt)
  if (!fc) return null
  const meta = FAILURE_META[fc]
  // Both contract-guard and fresh-verifier rejections persist their reason in
  // verifier_artifact (the guard's is a synthetic VerificationResult), so the
  // persisted reason text is used directly for either class.
  const reason =
    fc === 'runtime'
      ? attempt.error ?? 'unknown runtime error'
      : attempt.verifier_artifact?.reason ?? ''
  return (
    <div className={`failure-panel fc-${fc}`}>
      <div className="failure-head">
        <span className="failure-title">
          <span className="failure-glyph">{meta.glyph}</span>
          {meta.label}
        </span>
        <button
          className="icon-btn"
          title="Inspect this attempt"
          onClick={() => inspector.open(attemptInspector(model, attempt, index))}
        >
          ⓘ
        </button>
      </div>
      <div className="failure-reason">
        <MathText text={reason} />
      </div>
      <div className="failure-next">{meta.suggestion}</div>
    </div>
  )
}

/** Empty state used wherever the proof area has no verified content. */
export function EmptyProof({ model }: { model: WorkspaceModel }) {
  const running = model.obligation.status === 'RUNNING'
  return (
    <div className="empty-state">
      <p className="empty-title">No verified proof yet</p>
      <p className="empty-sub">
        {running
          ? 'An attempt is in progress — its candidate will appear under Attempts, unverified, until it passes.'
          : 'Nothing here is verified. Candidate proofs and their outcomes live with the attempt history.'}
      </p>
    </div>
  )
}

/** Session-scoped elapsed line (ADR-0003: display only, never persisted). */
export function ElapsedLine({ elapsed }: { elapsed: string }) {
  return <div className="phase-elapsed">{elapsed} on this page</div>
}

/** "Generating candidate…" / "Checking candidate…", labelled as inferred. */
export function RunningIndicator({ model, elapsed }: { model: WorkspaceModel; elapsed: string }) {
  const attempt = latestAttempt(model)
  const phase = attempt ? runningPhase(attempt) : 'generating'
  return (
    <>
      <span className="live-dot" style={{ width: 10, height: 10 }} />
      <div className="phase-text">
        {phase === 'generating' ? 'Generating candidate…' : 'Checking candidate…'}
      </div>
      <div className="phase-sub">live · phase inferred from attempt evidence</div>
      <ElapsedLine elapsed={elapsed} />
    </>
  )
}
