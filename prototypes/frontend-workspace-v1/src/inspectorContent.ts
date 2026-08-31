// THROWAWAY PROTOTYPE — builders that turn backend-mirrored objects into
// Inspector drawer content (machine metadata + raw JSON only).
import type { InspectorContent } from './components/Inspector'
import type { AttemptEvidence, Fact, WorkspaceModel } from './fixtures'
import { factLabel, getFact } from './fixtures'

export function problemInspector(m: WorkspaceModel): InspectorContent {
  return {
    title: 'Problem — Inspector',
    subtitle: 'Machine metadata for this problem and its root obligation',
    fields: [
      { label: 'problem_id', value: m.spec.problem_id, mono: true },
      { label: 'obligation_id', value: m.obligation.obligation_id, mono: true },
      { label: 'route_id', value: m.obligation.route_id, mono: true },
      { label: 'obligation status', value: m.obligation.status, mono: true },
      { label: 'premise_fact_ids', value: m.spec.premise_fact_ids.length ? m.spec.premise_fact_ids.join(', ') : '—', mono: true },
      { label: 'resolved_by_fact_id', value: m.obligation.resolved_by_fact_id ?? '—', mono: true },
      { label: 'lineage (derived_from)', value: m.derived_from ?? '—', mono: true },
    ],
    raw: { problem: m.spec, obligation: m.obligation, derived_from: m.derived_from ?? null },
  }
}

export function factInspector(m: WorkspaceModel, fact: Fact): InspectorContent {
  return {
    title: 'Verified Fact — Inspector',
    subtitle: factLabel(m, fact.fact_id),
    fields: [
      { label: 'fact_id', value: fact.fact_id, mono: true },
      { label: 'problem_id', value: fact.problem_id, mono: true },
      { label: 'author', value: fact.author, mono: true },
      {
        label: 'predecessors',
        value: fact.predecessors.length
          ? fact.predecessors.map((p) => `${factLabel(m, p)} (${p})`).join(', ')
          : '—',
        mono: true,
      },
      { label: 'verification', value: 'LLM-verified (fresh verifier session) — not kernel-verified' },
    ],
    raw: fact,
  }
}

export function attemptInspector(m: WorkspaceModel, attempt: AttemptEvidence, index: number): InspectorContent {
  const preds = attempt.candidate_artifact?.predecessors ?? []
  return {
    title: `Attempt ${index + 1} — Inspector`,
    subtitle: 'Durable attempt evidence (never deleted)',
    fields: [
      { label: 'attempt_id', value: attempt.attempt_id, mono: true },
      { label: 'problem_id', value: attempt.problem_id, mono: true },
      { label: 'obligation_id', value: attempt.obligation_id, mono: true },
      { label: 'route_id', value: m.obligation.route_id, mono: true },
      { label: 'verdict', value: attempt.verdict, mono: true },
      {
        label: 'candidate artifact',
        value: attempt.candidate_artifact
          ? `statement (${attempt.candidate_artifact.statement.length} chars), proof (${attempt.candidate_artifact.proof.length} chars), predecessors: ${preds.length ? preds.join(', ') : '[]'}`
          : 'null — no candidate was produced',
        mono: true,
      },
      {
        label: 'verifier artifact',
        value: attempt.verifier_artifact
          ? `accepted: ${attempt.verifier_artifact.accepted} — ${attempt.verifier_artifact.reason}`
          : 'null — the verifier never ran',
        mono: true,
      },
      { label: 'error', value: attempt.error ?? 'null', mono: true },
      { label: 'lineage (derived_from)', value: m.derived_from ?? '—', mono: true },
    ],
    raw: attempt,
  }
}

export { getFact }
