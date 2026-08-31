import { useState } from "react";
import type { Fact, WorkspaceReadModel } from "../types";
import { KatexStatement } from "../components/KatexStatement";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { MathParagraphs, MathText } from "../components/MathText";
import { factNames } from "./factNames";

type Props = {
  model: WorkspaceReadModel;
  onInspectFact: (fact: Fact) => void;
};

function statementSnippet(statement: string): string {
  const flat = statement.replace(/\s+/g, " ").trim();
  return flat.length > 80 ? `${flat.slice(0, 80)}…` : flat;
}

function ProofDocument({
  fact,
  title,
  names,
  onFactRef,
  onInspect,
}: {
  fact: Fact;
  title: string;
  names: Map<string, string>;
  onFactRef: (factId: string) => void;
  onInspect?: (fact: Fact) => void;
}) {
  return (
    <article className="proof-document">
      <header className="proof-document-header">
        <h2 className="proof-document-title">{title}</h2>
        <LlmVerifiedBadge />
        {onInspect ? (
          <button
            type="button"
            className="button--icon"
            aria-label={`Inspect ${title}`}
            title="Inspect Fact"
            onClick={() => onInspect(fact)}
          >
            ⓘ
          </button>
        ) : null}
      </header>
      <section className="proof-statement">
        <h3 className="proof-section-heading">Statement</h3>
        <MathText text={fact.statement} />
      </section>
      <section className="proof-body">
        <h3 className="proof-section-heading">Proof</h3>
        <MathParagraphs text={fact.proof} factNames={names} onFactRef={onFactRef} />
      </section>
    </article>
  );
}

export function ProofTab({ model, onInspectFact }: Props) {
  const [focusedFactId, setFocusedFactId] = useState<string | null>(null);

  const names = factNames(model);
  const factsById = new Map(model.supporting_closure.map((f) => [f.fact_id, f]));
  const target = model.target_fact;

  if (model.status !== "SOLVED" || target === null) {
    return (
      <div className="proof-empty">
        <p className="proof-empty-title">No verified proof yet</p>
        <p className="proof-empty-note">
          Candidate proofs live under the Attempts tab until one passes verification.
        </p>
      </div>
    );
  }

  const focused = focusedFactId === null ? undefined : factsById.get(focusedFactId);

  return (
    <div className="proof-tab">
      {focused ? (
        <div className="proof-focused">
          <button type="button" className="button--ghost" onClick={() => setFocusedFactId(null)}>
            ← Back to main theorem
          </button>
          <ProofDocument
            fact={focused}
            title={names.get(focused.fact_id) ?? focused.fact_id}
            names={names}
            onFactRef={setFocusedFactId}
            onInspect={onInspectFact}
          />
        </div>
      ) : (
        <ProofDocument
          fact={target}
          title="Main theorem"
          names={names}
          onFactRef={setFocusedFactId}
          onInspect={onInspectFact}
        />
      )}

      <section className="closure-section">
        <h3 className="proof-section-heading">Supporting closure</h3>
        {model.supporting_closure.length <= 1 ? (
          <p className="closure-note">This proof has no supporting Fact dependencies.</p>
        ) : (
          <ol className="closure-list">
            {model.supporting_closure.map((fact) => (
              <li key={fact.fact_id} className="closure-item">
                <button
                  type="button"
                  className="closure-item-button"
                  aria-label={names.get(fact.fact_id) ?? fact.fact_id}
                  onClick={() => setFocusedFactId(fact.fact_id)}
                >
                  <span className="closure-item-name">{names.get(fact.fact_id) ?? fact.fact_id}</span>
                  . <KatexStatement statement={statementSnippet(fact.statement)} />
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
