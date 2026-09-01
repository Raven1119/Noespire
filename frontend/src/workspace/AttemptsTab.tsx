import { useState } from "react";
import type { Attempt, WorkspaceReadModel } from "../types";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { MathParagraphs, MathText } from "../components/MathText";
import { executionFailurePanel, failurePanel, showExecutionFailure } from "./failureMeta";
import { ProofPlan } from "./ProofPlan";
import { RunningIndicator } from "./RunningIndicator";

type Props = {
  model: WorkspaceReadModel;
  onInspectAttempt: (attempt: Attempt, ordinal: number) => void;
};

/** Candidate proof register. Unverified attempts get the dashed/amber
 *  "Unverified" banner; a PASS attempt keeps the candidate visible as the
 *  accepted historical artifact that became a verified Fact (never disguised
 *  as a second proof). */
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
  return (
    <div className={`candidate-card${accepted ? " candidate-card--accepted" : ""}`}>
      <div className="candidate-card__banner">
        {accepted ? (
          <span>{acceptedBanner}</span>
        ) : (
          <>
            <span>Unverified — candidate proof</span>
            <span>not a Fact</span>
          </>
        )}
      </div>
      <div className="candidate-card__statement">
        <MathText text={attempt.candidate.statement} />
      </div>
      <div className="candidate-card__proof">
        <MathParagraphs text={attempt.candidate.proof} />
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
 * mode an intermediate node's PASS lands while the problem is still OPEN.
 * The banner names what the candidate became: the target Fact for a legacy
 * root attempt or the scaffold's target node; a verified Fact otherwise.
 */
function acceptedBanner(model: WorkspaceReadModel, attempt: Attempt): string {
  const isScaffoldNode = attempt.scaffold_node_id !== null;
  const isTargetNode =
    isScaffoldNode &&
    attempt.scaffold_node_id === model.proof_structure?.target_node_id;
  return isTargetNode || !isScaffoldNode
    ? "Accepted candidate · became the target Fact"
    : "Accepted candidate · became a verified Fact";
}

function AttemptBody({
  model,
  attempt,
}: {
  model: WorkspaceReadModel;
  attempt: Attempt;
}) {
  const accepted = attempt.verdict === "PASS";
  const panel = failurePanel(attempt);
  const nodeStatement = nodeStatementFor(model, attempt);

  return (
    <div className="attempt-card__body">
      {nodeStatement !== null && (
        <p className="attempt-node">
          Proof node: <MathText text={nodeStatement} />
        </p>
      )}
      {accepted ? (
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
            This attempt failed, but no failure classification survives — the
            record predates outcome classification.
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

/**
 * Attempts timeline: newest first, latest expanded by default, earlier
 * attempts collapsed (spec §9). Scaffold workspaces (N1.14P) additionally
 * show the Proof plan projection at the top and an execution-level failure
 * panel. Candidates render in the unverified register; ids and artifacts
 * stay in the Inspector.
 */
export function AttemptsTab({ model, onInspectAttempt }: Props) {
  const latestId =
    model.attempts.length > 0
      ? model.attempts[model.attempts.length - 1].attempt_id
      : null;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const hasPlan = model.proof_structure !== null;
  const hasExecutionFailure = showExecutionFailure(model);

  if (
    model.attempts.length === 0 &&
    model.status !== "RUNNING" &&
    !hasPlan &&
    !hasExecutionFailure
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
        />
      )}
      {hasPlan && <ProofPlan structure={model.proof_structure!} />}
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
                  <span className="attempt-card__verdict"> · {attempt.verdict}</span>
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
