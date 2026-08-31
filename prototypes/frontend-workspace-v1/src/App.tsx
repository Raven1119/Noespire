// THROWAWAY PROTOTYPE — answers one question: how should the Problem
// Workspace layout divide Proof / Attempts content across SOLVED / OPEN /
// RUNNING? Three structurally different variants, switchable via
// ?variant=A|B|C (shareable URL, ←/→ keys, floating dev-only switcher).
// No router library, no backend, no persistence.
import { useCallback, useEffect, useState } from 'react'
import { getWorkspace } from './fixtures'
import { InspectorProvider } from './components/Inspector'
import { ToastProvider } from './components/Toast'
import { PrototypeSwitcher, type VariantDef } from './components/PrototypeSwitcher'
import { Home } from './screens/Home'
import { WorkspaceHeader, useSessionElapsed } from './screens/WorkspaceChrome'
import { VariantA } from './variants/VariantA'
import { VariantB } from './variants/VariantB'
import { VariantC } from './variants/VariantC'

export const VARIANTS: VariantDef[] = [
  { key: 'A', name: 'Status stage' },
  { key: 'B', name: 'Explicit tabs' },
  { key: 'C', name: 'Document + evidence rail' },
]

interface Route {
  problem: string | null
  variant: string
}

function readUrl(): Route {
  const p = new URLSearchParams(window.location.search)
  const v = (p.get('variant') ?? 'A').toUpperCase()
  return {
    problem: p.get('problem'),
    variant: VARIANTS.some((x) => x.key === v) ? v : 'A',
  }
}

export default function App() {
  const [route, setRoute] = useState<Route>(readUrl)

  useEffect(() => {
    const onPop = () => setRoute(readUrl())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback(
    (problem: string | null, variant: string, replace = false) => {
      const params = new URLSearchParams()
      if (problem) params.set('problem', problem)
      params.set('variant', variant)
      const url = `?${params.toString()}`
      if (replace) window.history.replaceState({}, '', url)
      else window.history.pushState({}, '', url)
      setRoute({ problem, variant })
    },
    [],
  )

  const cycleVariant = useCallback(
    (dir: 1 | -1) => {
      const idx = VARIANTS.findIndex((v) => v.key === route.variant)
      const next = VARIANTS[(idx + dir + VARIANTS.length) % VARIANTS.length].key
      navigate(route.problem, next, true)
    },
    [route, navigate],
  )

  // ←/→ cycle variants; never when typing in an input/textarea/contenteditable.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      cycleVariant(e.key === 'ArrowRight' ? 1 : -1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cycleVariant])

  const model = route.problem ? getWorkspace(route.problem) : undefined

  return (
    <ToastProvider>
      <InspectorProvider>
        {model ? (
          <Workspace
            model={model}
            variant={route.variant}
            onBack={() => navigate(null, route.variant)}
            onOpenProblem={(id) => navigate(id, route.variant)}
          />
        ) : (
          <Home onOpen={(id) => navigate(id, route.variant)} />
        )}
        <PrototypeSwitcher
          variants={VARIANTS}
          current={route.variant}
          onSelect={(key) => navigate(route.problem, key, true)}
        />
      </InspectorProvider>
    </ToastProvider>
  )
}

function Workspace({
  model,
  variant,
  onBack,
  onOpenProblem,
}: {
  model: ReturnType<typeof getWorkspace> & object
  variant: string
  onBack: () => void
  onOpenProblem: (id: string) => void
}) {
  const elapsed = useSessionElapsed()
  const Variant = variant === 'B' ? VariantB : variant === 'C' ? VariantC : VariantA
  return (
    <div className="app-shell">
      <WorkspaceHeader model={model} onBack={onBack} onOpenProblem={onOpenProblem} />
      {/* key remounts the variant subtree per problem, so per-variant state
          (default tab, focus, expansions) resets when navigating problems */}
      <Variant key={model.spec.problem_id} model={model} elapsed={elapsed} />
    </div>
  )
}
