import type {
  PatchRecord,
  ProofGraphObligation,
  ProofGraphProjection,
  ProofGraphRoute,
  RouteDerivedState,
} from "../types";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { MathText } from "../components/MathText";

const ROUTE_STATE_LABEL: Record<RouteDerivedState, string> = {
  READY: "Ready",
  WAITING: "Waiting",
  EXHAUSTED: "Exhausted",
  IMPOSSIBLE: "Impossible",
};

const ROUTE_KIND_LABEL: Record<ProofGraphRoute["kind"], string> = {
  DIRECT: "Direct",
  SPLIT: "Split",
  CUT: "Cut set",
  ALTERNATIVE: "Alternative",
};

/** Static captions for derived route states — fixed semantic labels from the
 *  core's state vocabulary, never computed here. */
const ROUTE_STATE_CAPTION: Partial<Record<RouteDerivedState, string>> = {
  WAITING: "Waiting on unverified prerequisites.",
  IMPOSSIBLE: "A prerequisite was refuted — this route can never succeed.",
};

function snippet(text: string, max = 72): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

function ObligationState({ obligation }: { obligation: ProofGraphObligation }) {
  if (obligation.truth_state === "DISCHARGED") return <LlmVerifiedBadge />;
  if (obligation.truth_state === "REFUTED")
    return <span className="proof-plan__state proof-plan__state--refuted">Refuted</span>;
  return <span className="proof-plan__state">Open</span>;
}

/**
 * Dynamic proof plan (Proof Core v3): a readable AND/OR route tree over the
 * backend projection. Each obligation lists its routes (OR alternatives);
 * each route lists its prerequisite obligations (AND — all required). The
 * connectives are made explicit so the tree is never misread as a linear
 * proof outline. All states arrive backend-derived — this component follows
 * ids but never infers viability, truth, or frontiers.
 *
 * Frontier markers are shown only while the run can still act on them (phase
 * ≠ STOPPED): on a terminal run nothing will pursue a frontier, so the
 * marker is withheld and the stop panel explains the outcome instead.
 *
 * Search/truth styling rule: only DISCHARGED obligations wear the
 * LLM-verified badge; OPEN routes and obligations stay neutral/muted;
 * REFUTED uses the amber failure accent. Graph structure is never
 * presented as proof.
 */
export function DynamicProofPlan({
  projection,
  patches,
  showFrontiers = true,
}: {
  projection: ProofGraphProjection;
  /** Applied GraphPatch history (step order); empty before any refinement. */
  patches: PatchRecord[];
  /** False on terminal runs: no live frontier exists to mark. */
  showFrontiers?: boolean;
}) {
  const obligationsById = new Map(
    projection.obligations.map((o) => [o.obligation_id, o])
  );
  const routesByTarget = new Map<string, ProofGraphRoute[]>();
  for (const route of projection.routes) {
    const list = routesByTarget.get(route.target_obligation_id) ?? [];
    list.push(route);
    routesByTarget.set(route.target_obligation_id, list);
  }
  const frontierObligations = new Set(
    showFrontiers
      ? projection.frontiers
          .filter((f) => f.kind === "STRUCTURAL")
          .map((f) => f.obligation_id)
      : []
  );
  const frontierRoutes = new Set(
    showFrontiers
      ? projection.frontiers
          .filter((f) => f.kind === "PROOF" && f.route_id !== null)
          .map((f) => f.route_id as string)
      : []
  );

  const renderObligation = (obligationId: string, visited: Set<string>): React.ReactNode => {
    const obligation = obligationsById.get(obligationId);
    if (obligation === undefined) return null;
    const isTarget = obligationId === projection.target_obligation_id;
    // The core validates acyclicity; the visited guard only protects the
    // render against a corrupt payload — never hide nodes silently.
    const recurse = !visited.has(obligationId);
    const nextVisited = new Set(visited).add(obligationId);
    const routes = recurse ? routesByTarget.get(obligationId) ?? [] : [];
    return (
      <li
        key={obligationId}
        className={`proof-plan__item proof-plan__item--tree proof-plan__item--${obligation.truth_state.toLowerCase()}`}
      >
        <div className="proof-plan__row">
          <span className="proof-plan__glyph" aria-hidden="true">
            {obligation.truth_state === "DISCHARGED"
              ? "✓"
              : obligation.truth_state === "REFUTED"
                ? "×"
                : "○"}
          </span>
          <span className="proof-plan__statement">
            <MathText text={obligation.statement} />
          </span>
          <span className="proof-plan__badges">
            {isTarget && <span className="proof-plan__target">Target</span>}
            {frontierObligations.has(obligationId) && (
              <span className="proof-plan__frontier">◂ frontier</span>
            )}
            <ObligationState obligation={obligation} />
          </span>
        </div>
        {routes.length > 0 && (
          <div className="proof-plan__route-group">
            {routes.length > 1 && (
              <p className="proof-plan__connective">
                OR — any one route can discharge this obligation
              </p>
            )}
            <ol className="proof-plan__routes">
              {routes.map((route) => (
                <li
                  key={route.route_id}
                  className={`proof-plan__route proof-plan__route--${route.derived_state.toLowerCase()}`}
                >
                  <div className="proof-plan__route-head">
                    <span className="proof-plan__route-label">
                      {ROUTE_KIND_LABEL[route.kind]} route ·{" "}
                      {ROUTE_STATE_LABEL[route.derived_state]}
                    </span>
                    {frontierRoutes.has(route.route_id) && (
                      <span className="proof-plan__frontier">◂ frontier</span>
                    )}
                  </div>
                  {route.derived_state === "EXHAUSTED" &&
                    route.exhaustion_reason !== null && (
                      <p className="proof-plan__route-reason">
                        <MathText text={route.exhaustion_reason} />
                      </p>
                    )}
                  {ROUTE_STATE_CAPTION[route.derived_state] !== undefined && (
                    <p className="proof-plan__route-caption">
                      {ROUTE_STATE_CAPTION[route.derived_state]}
                    </p>
                  )}
                  {route.prerequisite_obligation_ids.length > 0 && (
                    <div className="proof-plan__and-group">
                      {route.prerequisite_obligation_ids.length > 1 && (
                        <p className="proof-plan__connective">
                          AND — every prerequisite must be verified
                        </p>
                      )}
                      <ol className="proof-plan__list">
                        {route.prerequisite_obligation_ids.map((childId) =>
                          renderObligation(childId, nextVisited)
                        )}
                      </ol>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
      </li>
    );
  };

  return (
    <section className="proof-plan">
      <h3 className="proof-plan__heading">Proof plan</h3>
      <ol className="proof-plan__list">
        {renderObligation(projection.target_obligation_id, new Set())}
      </ol>
      {patches.length > 0 && (
        <section className="proof-plan__refinements">
          <h4 className="proof-plan__refinements-heading">Refinements</h4>
          <ol className="proof-plan__refinements-list">
            {patches.map((patch) => {
              const target = obligationsById.get(patch.target_obligation_id);
              return (
                <li key={patch.patch_id} className="proof-plan__refinement">
                  <span className="proof-plan__refinement-label">
                    {patch.operator === "SPLIT"
                      ? "Split"
                      : patch.operator === "INSERT_CUT_SET"
                        ? "Cut set"
                        : patch.operator === "ADD_ALTERNATIVE_ROUTE"
                          ? "Alternative route"
                          : patch.operator}{" "}
                    · step {patch.step}
                    {target !== undefined && (
                      <span className="proof-plan__refinement-target">
                        {" "}
                        — applied to <MathText text={snippet(target.statement)} />
                      </span>
                    )}
                  </span>
                  <ul className="proof-plan__refinement-goals">
                    {patch.obligation_goals.map((goal) => (
                      <li key={goal}>
                        <MathText text={goal} />
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </section>
  );
}
