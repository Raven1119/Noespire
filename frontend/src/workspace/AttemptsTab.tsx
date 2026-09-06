import { useState } from "react";
import type { Attempt, V3AttemptOutcome, WorkspaceReadModel } from "../types";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { MathParagraphs, MathText } from "../components/MathText";
import { executionFailurePanel, failurePanel, showExecutionFailure } from "./failureMeta";
import { DynamicProofPlan } from "./DynamicProofPlan";
import { ProofPlan } from "./ProofPlan";
import { RunningIndicator } from "./RunningIndicator";

type Props = {
  model: WorkspaceReadModel;
  onInspectAttempt: (attempt: Attempt, ordinal: number) => void;
};

/** Candidate proof register. Unverified attempts get the dashed/amber
 *  "Unverified" banner; a PASS attempt keeps the candidate visible as the
 *  accepted historical artifact that became a verified Fact (never disguised
 *  as a second proof). v3 counterexample candidates render their
 *  counterexample, not an empty proof. */
function CandidateCard({
  attempt,
  acceptedBanner = null,
}: {
  attempt: Attempt;
  /** Exact accepted-artifact copy; null → unverified register. */
  acceptedBanner?: string | null;
}) {
  if (attempt.candidate === null) return null;
  const accepted = acceptedBanner !== null && acceptedBanner !== undefined;
  const counterexample = attempt.candidate.counterexample || null;
  return (
    <div className={`candidate-card${accepted ? " candidate-card--accepted" : ""}`}>
      <div className="candidate-card__banner">
        {accepted ? (
          <span>{acceptedBanner}</span>
        ) : (
          <>
            <span>
              {counterexample !== null
                ? "Unverified — candidate counterexample"
                : "Unverified — candidate proof"}
            </span>
            <span>{counterexample !== null ? "not a Refutation" : "not a Fact"}</span>
          </>
        )}
      </div>
      <div className="candidate-card__statement">
        <MathText text={attempt.candidate.statement} />
      </div>
      <div className="candidate-card__proof">
        <MathParagraphs
          text={counterexample !== null ? counterexample : attempt.candidate.proof}
        />
      </div>
    </div>
  );
}

/** Node attribution for scaffold attempts: "Proof node: <statement>" with
 *  the statement looked up in proof_structure; falls back to the raw node_id
 *  when the projection is absent. The frontend never parses obligation ids. */
function nodeStatementFor(
  model: WorkspaceReadModel,
  attempt: Attempt
): string | null {
  if (attempt.scaffold_node_id === null) return null;
  const node = model.proof_structure?.nodes.find(
    (n) => n.node_id === attempt.scaffold_node_id
  );
  return node?.statement ?? attempt.scaffold_node_id;
}

/**
 * A PASS attempt is always the accepted historical artifact — in scaffold
 * mode an intermediate node's PASS lands while the problem is still OPEN;
 * in v3 mode an intermediate obligation's FACT_ADMITTED likewise. The
 * banner names what the candidate became: the target Fact for a legacy
 * root attempt, the scaffold/v3 target, or a verified Fact otherwise.
 */
function acceptedBanner(model: WorkspaceReadModel, attempt: Attempt): string {
  if (attempt.outcome !== null) {
    // v3: attribution by target obligation, resolved server-side.
    return attempt.obligation_id === model.proof_graph?.target_obligation_id
      ? "Accepted candidate · became the target Fact"
      : "Accepted candidate · became a verified Fact";
  }
  const isScaffoldNode = attempt.scaffold_node_id !== null;
  const isTargetNode =
    isScaffoldNode &&
    attempt.scaffold_node_id === model.proof_structure?.target_node_id;
  return isTargetNode || !isScaffoldNode
    ? "Accepted candidate · became the target Fact"
    : "Accepted candidate · became a verified Fact";
}

/** Precise per-outcome labels for v3 attempts (the shared `verdict` field
 *  is only a coarse display mapping). */
const V3_OUTCOME_LABELS: Record<V3AttemptOutcome, string> = {
  RUNNING: "RUNNING",
  NO_RESULT: "NO RESULT",
  PROOF_REJECTED: "FAIL · verifier rejected",
  COUNTEREXAMPLE_REJECTED: "FAIL · counterexample rejected",
  TIMEOUT: "TIMEOUT",
  ERROR: "ERROR",
  INTERRUPTED: "INTERRUPTED",
  FACT_ADMITTED: "PASS",
  REFUTATION_ADMITTED: "REFUTED",
};

function AttemptBody({
  model,
  attempt,
}: {
  model: WorkspaceReadModel;
  attempt: Attempt;
}) {
  const accepted = attempt.verdict === "PASS";
  const refuted = attempt.outcome === "REFUTATION_ADMITTED";
  // A typed timeout is not a generic runtime error: name it honestly. The
  // shared failure classifier maps TIMEOUT to "runtime" (coarse); the v3
  // outcome is the precise display source.
  const panel =
    attempt.outcome === "TIMEOUT"
      ? {
          glyph: "⏱",
          title: "Attempt timed out",
          reason: attempt.error,
          lines: [
            "The model produced no answer within the bounded time limit; no verdict was recorded for this attempt.",
          ],
        }
      : failurePanel(attempt);
  const nodeStatement = nodeStatementFor(model, attempt);
  const obligationGoal = attempt.obligation_goal;
  const refutation =
    attempt.refutation_id !== null
      ? (model.refutations.find((r) => r.refutation_id === attempt.refutation_id) ??
        null)
      : null;

  return (
    <div className="attempt-card__body">
      {nodeStatement !== null && (
        <p className="attempt-node">
          Proof node: <MathText text={nodeStatement} />
        </p>
      )}
      {obligationGoal !== null && (
        <p className="attempt-node">
          Obligation: <MathText text={obligationGoal} />
        </p>
      )}
      {refuted ? (
        <>
          <div className="attempt-accepted">
            <span className="attempt-accepted__label attempt-accepted__label--refuted">
              LLM-verified refutation
            </span>
          </div>
          <CandidateCard
            attempt={attempt}
            acceptedBanner="Accepted counterexample · refuted this obligation"
          />
          {refutation !== null && refutation.reason !== null && (
            <p className="attempt-note">
              <MathText text={refutation.reason} />
            </p>
          )}
        </>
      ) : accepted ? (
        <>
          <div className="attempt-accepted">
            <span className="attempt-accepted__label">Accepted</span>
            <LlmVerifiedBadge />
          </div>
          <CandidateCard attempt={attempt} acceptedBanner={acceptedBanner(model, attempt)} />
        </>
      ) : (
        <CandidateCard attempt={attempt} />
      )}

      {panel !== null ? (
        <div className={`failure-panel failure-panel--${attempt.failure_class ?? ""}`}>
          <p className="failure-panel__title">
            <span className="failure-panel__glyph" aria-hidden="true">
              {panel.glyph}
            </span>{" "}
            {panel.title}
          </p>
          {panel.reason !== null && (
            <p className="failure-panel__reason">
              <MathText text={panel.reason} />
            </p>
          )}
          {panel.lines.map((line) => (
            <p key={line} className="failure-panel__line">
              {line}
            </p>
          ))}
        </div>
      ) : (
        attempt.verdict === "FAIL" && (
          <p className="attempt-note">
            {attempt.outcome === "NO_RESULT"
              ? "The worker returned no result for this obligation."
              : "This attempt failed, but no failure classification survives — the record predates outcome classification."}
          </p>
        )
      )}
    </div>
  );
}

/** Execution-level failure (architect-stage, pre-attempt runtime, crash
 *  recovery) — rendered above the attempt list since it produced no node
 *  attempts. Same visual language as per-attempt failure panels. */
function ExecutionFailurePanel({ model }: { model: WorkspaceReadModel }) {
  const failure = model.last_execution_failure;
  if (failure === null) return null;
  const panel = executionFailurePanel(failure);
  if (panel === null) return null;
  return (
    <div className="failure-panel failure-panel--execution">
      <p className="failure-panel__title">
        <span className="failure-panel__glyph" aria-hidden="true">
          {panel.glyph}
        </span>{" "}
        {panel.title}
      </p>
      {panel.reason !== null && (
        <p className="failure-panel__reason">
          <MathText text={panel.reason} />
        </p>
      )}
      {panel.lines.map((line) => (
        <p key={line} className="failure-panel__line">
          {line}
        </p>
      ))}
    </div>
  );
}

/** v3 run-state panel: an interrupted (crashed) run that Retry resumes, or
 *  a terminally stopped run with its persisted stop reason. Shown only when
 *  the workspace is not RUNNING/SOLVED — live runs speak through the
 *  RunningIndicator, solved runs through the Proof tab. */
function DynamicRunPanel({ model }: { model: WorkspaceReadModel }) {
  const dynamic = model.dynamic;
  if (dynamic === null) return null;
  if (model.status === "RUNNING" || model.status === "SOLVED") return null;

  if (dynamic.phase !== "STOPPED") {
    return (
      <div className="failure-panel failure-panel--interrupted">
        <p className="failure-panel__title">
          <span className="failure-panel__glyph" aria-hidden="true">
            ⚠
          </span>{" "}
          Run interrupted
        </p>
        <p className="failure-panel__line">
          The previous run stopped mid-phase ({dynamic.phase}). Retry resumes
          it: completed model calls are replayed from the durable journal, not
          re-computed.
        </p>
      </div>
    );
  }
  if (dynamic.stop_reason === null) return null;

  const copy = stopReasonCopy(dynamic.stop_reason);
  return (
    <div className="failure-panel failure-panel--stopped">
      <p className="failure-panel__title">
        <span className="failure-panel__glyph" aria-hidden="true">
          ■
        </span>{" "}
        {copy.title}
      </p>
      {dynamic.error !== null && (
        <p className="failure-panel__reason">
          <MathText text={dynamic.error} />
        </p>
      )}
      <p className="failure-panel__line">{copy.line}</p>
      <p className="failure-panel__line">
        This run is terminal — it cannot be retried. Revise &amp; Fork starts
        a fresh lineage with its own run.
      </p>
    </div>
  );
}

const STOP_REASON_COPY: Record<string, { title: string; line: string }> = {
  TARGET_REFUTED: {
    title: "Target refuted",
    line: "A verified counterexample falsifies the statement. Revise & Fork to adjust it.",
  },
  FRONTIER_EXHAUSTED: {
    title: "Search exhausted",
    line: "Every viable route was tried; no frontier remains within budget.",
  },
  BUDGET_EXHAUSTED: {
    title: "Budget exhausted",
    line: "The run reached its bounded call/attempt budget before a result.",
  },
  STRATEGIST_DECLINE: {
    title: "No useful decomposition",
    line: "The strategist declined to refine the exhausted frontier.",
  },
  STRATEGIST_TIMEOUT: {
    title: "Strategist timeout",
    line: "The strategy step timed out.",
  },
  MECHANICAL_FAIL: {
    title: "Refinement failed validation",
    line: "The proposed graph change failed mechanical validation, so no refinement was applied.",
  },
  PATCH_COMPILATION_INVALID: {
    title: "Refinement could not be compiled",
    line: "The strategist's proposal could not be compiled into a valid graph change.",
  },
  PATCH_BUILDER_TIMEOUT: {
    title: "Refinement timed out",
    line: "Compiling the proposed graph change exceeded its time limit.",
  },
  REVISION_FAILED: {
    title: "Refinement revision failed",
    line: "The single allowed revision of the proposed graph change did not pass.",
  },
  STRATEGY_GATE_REJECT: {
    title: "Strategy rejected at the gate",
    line: "The proposed strategy did not pass the difficulty-reduction gate.",
  },
  INTERRUPTED: {
    title: "Run interrupted",
    line: "A model call was interrupted; the run stopped conservatively rather than guessing a result.",
  },
  SYSTEM_ERROR: {
    title: "System error",
    line: "The run stopped on a runtime error, not a mathematical verdict.",
  },
  ATTENTION_LIMIT: {
    title: "Attention limit",
    line: "A local packet exceeded the bounded context limit; the run failed closed.",
  },
};

/** Structural-auditor rejections carry the audit verdict in the stop reason
 *  (``STRUCTURAL_AUDITOR_<VERDICT>``); map the family, not every suffix. */
function stopReasonCopy(reason: string): { title: string; line: string } {
  const exact = STOP_REASON_COPY[reason];
  if (exact !== undefined) return exact;
  if (reason.startsWith("STRUCTURAL_AUDITOR_")) {
    return {
      title: "Refinement rejected on audit",
      line: "The structural auditor rejected the proposed graph change.",
    };
  }
  return {
    title: "Run stopped",
    line: "The run stopped before reaching a verified result.",
  };
}

/** Attempts timeline: newest first, latest expanded by default, earlier
 * attempts collapsed (spec §9). Scaffold workspaces (N1.14P) show the Proof
 * plan projection at the top; v3 workspaces show the AND/OR route tree
 * (DynamicProofPlan) plus run-state panels. Candidates render in the
 * unverified register; ids and artifacts stay in the Inspector. */
function goalSnippet(text: string, max = 56): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

export function AttemptsTab({ model, onInspectAttempt }: Props) {
  const latestId =
    model.attempts.length > 0
      ? model.attempts[model.attempts.length - 1].attempt_id
      : null;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const hasPlan = model.proof_structure !== null || model.proof_graph !== null;
  const hasExecutionFailure = showExecutionFailure(model);

  if (
    model.attempts.length === 0 &&
    model.status !== "RUNNING" &&
    !hasPlan &&
    !hasExecutionFailure &&
    model.dynamic === null
  ) {
    return (
      <p className="attempts-empty">
        Attempts appear here once the first attempt has run.
      </p>
    );
  }

  // Node-specific running copy only when exactly one node projects RUNNING;
  // otherwise the conservative generic copy. Never guess (spec §5).
  const runningNodes =
    model.status === "RUNNING"
      ? model.proof_structure?.nodes.filter((n) => n.state === "RUNNING") ?? []
      : [];
  const runningStatement =
    runningNodes.length === 1 ? runningNodes[0].statement : null;

  const newestFirst = [...model.attempts].reverse();

  return (
    <div className="attempts-tab">
      {model.status === "RUNNING" && (
        <RunningIndicator
          phaseHint={model.running_phase_hint}
          nodeStatement={runningStatement}
          dynamicPhase={model.dynamic?.phase ?? null}
        />
      )}
      <DynamicRunPanel model={model} />
      {model.proof_structure !== null && (
        <ProofPlan structure={model.proof_structure} />
      )}
      {model.proof_graph !== null && (
        <DynamicProofPlan
          projection={model.proof_graph}
          patches={model.patches}
          showFrontiers={model.dynamic?.phase !== "STOPPED"}
        />
      )}
      {hasExecutionFailure && <ExecutionFailurePanel model={model} />}
      <ol className="attempt-list">
        {newestFirst.map((attempt) => {
          const ordinal =
            model.attempts.findIndex((a) => a.attempt_id === attempt.attempt_id) + 1;
          const isExpanded = expanded[attempt.attempt_id] ??
            attempt.attempt_id === latestId;
          return (
            <li
              key={attempt.attempt_id}
              className={`attempt-card${isExpanded ? "" : " attempt-card--collapsed"}`}
            >
              <div className="attempt-card__head">
                <button
                  type="button"
                  className="attempt-card__toggle"
                  aria-expanded={isExpanded}
                  onClick={() =>
                    setExpanded((prev) => ({
                      ...prev,
                      [attempt.attempt_id]: !isExpanded,
                    }))
                  }
                >
                  Attempt {ordinal}
                  <span className="attempt-card__verdict">
                    {" "}
                    ·{" "}
                    {attempt.outcome !== null
                      ? V3_OUTCOME_LABELS[attempt.outcome]
                      : attempt.verdict}
                  </span>
                  {!isExpanded && attempt.obligation_goal !== null && (
                    <span className="attempt-card__goal">
                      {" — "}
                      <MathText text={goalSnippet(attempt.obligation_goal)} />
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  className="button--icon"
                  aria-label={`Inspect attempt ${ordinal}`}
                  title="Inspect attempt"
                  onClick={() => onInspectAttempt(attempt, ordinal)}
                >
                  ⓘ
                </button>
              </div>
              {isExpanded && <AttemptBody model={model} attempt={attempt} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
