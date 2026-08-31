// THROWAWAY PROTOTYPE — Home: restrained problem list. Forks are collapsed
// under their origin problem (ADR-0001: failed forks accumulate, never delete).
import { useState } from 'react'
import { displayStatus, WORKSPACES, type WorkspaceModel } from '../fixtures'
import { StatusBadge } from '../components/Badges'
import { MathText } from '../components/Katex'
import { useToast } from '../components/Toast'

export function Home({ onOpen }: { onOpen: (problemId: string) => void }) {
  const roots = WORKSPACES.filter((w) => !w.derived_from)
  const forksOf = (id: string) => WORKSPACES.filter((w) => w.derived_from === id)
  return (
    <div className="app-shell">
      <h1 className="home-title">Noespire</h1>
      <p className="home-sub">Problems — throwaway layout prototype</p>
      {roots.map((m) => (
        <RootRow key={m.spec.problem_id} model={m} forks={forksOf(m.spec.problem_id)} onOpen={onOpen} />
      ))}
    </div>
  )
}

function RootRow({
  model,
  forks,
  onOpen,
}: {
  model: WorkspaceModel
  forks: WorkspaceModel[]
  onOpen: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div>
      <ProblemRow model={model} onOpen={onOpen} />
      {forks.length > 0 && (
        <>
          <button className="fork-toggle" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '▾' : '▸'} {forks.length} fork{forks.length > 1 ? 's' : ''} (revised statements)
          </button>
          {expanded && (
            <div className="fork-group">
              {forks.map((f) => (
                <ProblemRow key={f.spec.problem_id} model={f} onOpen={onOpen} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ProblemRow({ model, onOpen }: { model: WorkspaceModel; onOpen: (id: string) => void }) {
  const toast = useToast()
  return (
    <button
      type="button"
      className="problem-row"
      onClick={() => onOpen(model.spec.problem_id)}
    >
      <span className="problem-row-head">
        <StatusBadge status={displayStatus(model)} />
        {model.derived_from && <span className="fork-chip">fork of {model.derived_from}</span>}
      </span>
      <span className="problem-row-statement">
        <MathText text={model.spec.statement} />
      </span>
      <span className="problem-row-meta">
        <span>
          {model.attempts.length} attempt{model.attempts.length === 1 ? '' : 's'}
        </span>
        <span>last activity {model.last_activity}</span>
        <span
          role="button"
          tabIndex={-1}
          style={{ marginLeft: 'auto', textDecoration: 'underline dotted' }}
          onClick={(e) => {
            e.stopPropagation()
            toast.show('Archive — prototype stub')
            console.log('[prototype stub] archive', model.spec.problem_id)
          }}
        >
          Archive
        </span>
      </span>
    </button>
  )
}
