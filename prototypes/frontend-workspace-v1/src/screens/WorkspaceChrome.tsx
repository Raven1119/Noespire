// THROWAWAY PROTOTYPE — workspace chrome shared by all three variants:
// the constant header (statement, badges, actions, lineage) and the
// session-scoped elapsed clock. Variants themselves live in ../variants/.
import { useEffect, useState } from 'react'
import { displayStatus, type WorkspaceModel } from '../fixtures'
import { StatusBadge } from '../components/Badges'
import { MathText } from '../components/Katex'
import { useInspector } from '../components/Inspector'
import { useToast } from '../components/Toast'
import { problemInspector } from '../inspectorContent'

/** Session-scoped elapsed clock — starts when the workspace is opened,
 *  display only, never persisted (ADR-0003). */
export function useSessionElapsed(): string {
  const [start] = useState(() => Date.now())
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])
  const s = Math.max(0, Math.floor((now - start) / 1000))
  const h = Math.floor(s / 3600)
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

export function WorkspaceHeader({
  model,
  onBack,
  onOpenProblem,
}: {
  model: WorkspaceModel
  onBack: () => void
  onOpenProblem: (id: string) => void
}) {
  const status = displayStatus(model)
  const inspector = useInspector()
  const toast = useToast()
  const stub = (name: string) => () => {
    console.log(`[prototype stub] ${name}`, model.spec.problem_id)
    toast.show(`${name} — prototype stub`)
  }
  return (
    <>
      <button className="ws-back" onClick={onBack}>
        ← Problems
      </button>
      <header className="ws-header">
        <div className="ws-header-top">
          <div className="ws-header-badges">
            <StatusBadge status={status} />
          </div>
          <div className="ws-header-actions">
            {status === 'OPEN' || status === 'ERROR' ? (
              <>
                <button className="btn btn-primary" onClick={stub('Retry')}>
                  Retry
                </button>
                <button className="btn" onClick={stub('Revise & Fork')}>
                  Revise &amp; Fork
                </button>
              </>
            ) : status === 'RUNNING' ? (
              <button className="btn" disabled title="already running">
                Retry
              </button>
            ) : (
              <button className="btn" onClick={stub('Revise & Fork')}>
                Revise &amp; Fork
              </button>
            )}
            <button
              className="icon-btn"
              title="Inspect this problem"
              onClick={() => inspector.open(problemInspector(model))}
            >
              ⓘ
            </button>
          </div>
        </div>
        <div className="ws-statement">
          <MathText text={model.spec.statement} />
        </div>
        {model.derived_from && (
          <div className="ws-lineage">
            Derived from{' '}
            <button onClick={() => onOpenProblem(model.derived_from!)}>{model.derived_from}</button>{' '}
            — the original and its evidence are untouched (revision is fork, never edit)
          </div>
        )}
      </header>
    </>
  )
}
