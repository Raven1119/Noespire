import type { ProofNode, ProofNodeState, ProofStructure } from "../types";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { MathText } from "../components/MathText";

/**
 * Deterministic topological order for plan display: dependencies first,
 * target last, stable by arrival order among ready nodes. Nodes arrive
 * sorted by node_id (never topological), so the sort happens here. Any
 * malformed input (cycle, dangling dependency id) falls back to the given
 * order rather than hiding nodes.
 */
export function topologicalOrder(structure: ProofStructure): ProofNode[] {
  const byId = new Map(structure.nodes.map((node) => [node.node_id, node]));
  const ordered: ProofNode[] = [];
  const done = new Set<string>();
  const visiting = new Set<string>();
  let malformed = false;

  const visit = (node: ProofNode): void => {
    if (malformed || done.has(node.node_id)) return;
    if (visiting.has(node.node_id)) {
      malformed = true;
      return;
    }
    visiting.add(node.node_id);
    for (const depId of node.dependency_node_ids) {
      const dep = byId.get(depId);
      if (dep === undefined) {
        malformed = true;
        return;
      }
      visit(dep);
    }
    visiting.delete(node.node_id);
    done.add(node.node_id);
    ordered.push(node);
  };

  for (const node of structure.nodes) {
    visit(node);
    if (malformed) return structure.nodes;
  }
  return ordered;
}

const STATE_PRESENTATION: Record<
  Exclude<ProofNodeState, "VERIFIED">,
  { glyph: string; label: string }
> = {
  RUNNING: { glyph: "◐", label: "Running" },
  BLOCKED: { glyph: "×", label: "Blocked" },
  READY: { glyph: "○", label: "Ready" },
  PLANNED: { glyph: "·", label: "Planned" },
};

/**
 * Static proof-plan list (N1.14P): a restrained ordered list — state glyph,
 * node statement, state label; no graph library, no canvas. Search-state
 * styling rule (ADR-0003): only VERIFIED nodes wear verified-truth styling
 * (the LLM-verified badge); every other state stays neutral/muted, and
 * BLOCKED uses the amber failure accent.
 */
export function ProofPlan({ structure }: { structure: ProofStructure }) {
  const ordered = topologicalOrder(structure);
  return (
    <section className="proof-plan">
      <h3 className="proof-plan__heading">Proof plan</h3>
      <ol className="proof-plan__list">
        {ordered.map((node) => (
          <li
            key={node.node_id}
            className={`proof-plan__item proof-plan__item--${node.state.toLowerCase()}`}
          >
            <span className="proof-plan__glyph" aria-hidden="true">
              {node.state === "VERIFIED" ? "✓" : STATE_PRESENTATION[node.state].glyph}
            </span>
            <span className="proof-plan__statement">
              <MathText text={node.statement} />
            </span>
            {node.node_id === structure.target_node_id && (
              <span className="proof-plan__target">Target</span>
            )}
            {node.state === "VERIFIED" ? (
              <LlmVerifiedBadge />
            ) : (
              <span className="proof-plan__state">
                {STATE_PRESENTATION[node.state].label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
