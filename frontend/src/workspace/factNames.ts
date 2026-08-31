import type { WorkspaceReadModel } from "../types";

/**
 * Display names for Facts in topological closure order:
 * supporting Facts are "Lemma 1..N" and the target Fact is "Main theorem".
 */
export function factNames(model: WorkspaceReadModel): Map<string, string> {
  const names = new Map<string, string>();
  const targetId = model.target_fact?.fact_id ?? null;
  let lemma = 0;
  for (const fact of model.supporting_closure) {
    if (targetId !== null && fact.fact_id === targetId) {
      names.set(fact.fact_id, "Main theorem");
    } else {
      lemma += 1;
      names.set(fact.fact_id, `Lemma ${lemma}`);
    }
  }
  return names;
}
