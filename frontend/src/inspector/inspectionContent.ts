import type { Attempt, Fact, WorkspaceReadModel } from "../types";
import type { InspectorField } from "./InspectorDrawer";

/**
 * Maps an inspectable object to drawer content (spec §9: ids, artifacts, raw
 * JSON live ONLY here). Object-agnostic — Problem, Fact, and Attempt share
 * the one drawer. Never fabricate fields the read model does not provide
 * (e.g. Fact has no author).
 */
export type Inspection =
  | { kind: "problem" }
  | { kind: "fact"; fact: Fact }
  | { kind: "attempt"; attempt: Attempt; ordinal: number };

export interface DrawerContent {
  title: string;
  subtitle?: string;
  fields: InspectorField[];
  raw: unknown;
}

export function drawerContent(
  model: WorkspaceReadModel,
  inspection: Inspection
): DrawerContent {
  switch (inspection.kind) {
    case "problem":
      return {
        title: "Problem",
        subtitle: model.statement,
        fields: [
          { label: "problem_id", value: model.problem_id, mono: true },
          { label: "derived_from", value: model.derived_from ?? "—", mono: true },
          { label: "archived", value: model.archived ? "true" : "false" },
          {
            label: "obligation status",
            value: model.obligation?.status ?? "— (no obligation yet)",
          },
        ],
        raw: model,
      };
    case "fact":
      return {
        title: "Fact",
        subtitle: inspection.fact.statement,
        fields: [
          { label: "fact_id", value: inspection.fact.fact_id, mono: true },
          {
            label: "predecessors",
            value:
              inspection.fact.predecessors.length > 0
                ? inspection.fact.predecessors.join(", ")
                : "—",
            mono: true,
          },
          { label: "statement", value: inspection.fact.statement },
        ],
        raw: inspection.fact,
      };
    case "attempt": {
      const { attempt } = inspection;
      const fields: InspectorField[] = [
        { label: "attempt_id", value: attempt.attempt_id, mono: true },
        { label: "verdict", value: attempt.verdict },
        { label: "failure_class", value: attempt.failure_class ?? "—" },
        {
          label: "candidate artifact",
          value:
            attempt.candidate !== null ? JSON.stringify(attempt.candidate, null, 2) : "—",
          mono: true,
        },
        {
          label: "verifier artifact",
          value:
            attempt.verifier !== null ? JSON.stringify(attempt.verifier, null, 2) : "—",
          mono: true,
        },
        { label: "error", value: attempt.error ?? "—" },
        { label: "started_at", value: attempt.started_at ?? "—", mono: true },
        { label: "finished_at", value: attempt.finished_at ?? "—", mono: true },
      ];
      if (attempt.verifier_called !== undefined) {
        fields.push({
          label: "verifier_called",
          value: attempt.verifier_called ? "true" : "false",
        });
      }
      return {
        title: "Attempt",
        subtitle: `Attempt ${inspection.ordinal} of problem ${model.problem_id}`,
        fields,
        raw: attempt,
      };
    }
  }
}
