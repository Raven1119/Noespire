import { useState } from "react";
import type { Attempt, WorkspaceReadModel } from "../types";
import { LlmVerifiedBadge } from "../components/LlmVerifiedBadge";
import { MathParagraphs, MathText } from "../components/MathText";
import { failurePanel } from "./failureMeta";
import { RunningIndicator } from "./RunningIndicator";

type Props = {
  model: WorkspaceReadModel;
  onInspectAttempt: (attempt: Attempt, ordinal: number) => void;
};

/** Candidate proof register. Unverified attempts get the dashed/amber
 *  "Unverified" banner; a PASS attempt keeps the candidate visible as the
 *  accepted historical artifact that became the target Fact (never
 *  disguised as a second proof). */
function CandidateCard({
  attempt,
  accepted = false,
}: {
  attempt: Attempt;
  accepted?: boolean;
}) {
  if (attempt.candidate === null) return null;
  return (
    <div className={`candidate-card${accepted ? " candidate-card--accepted" : ""}`}>
      <div className="candidate-card__banner">
        {accepted ? (
          <span>Accepted candidate · became the target Fact</span>
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

function AttemptBody({
  model,
  attempt,
}: {
  model: WorkspaceReadModel;
  attempt: Attempt;
}) {
  const accepted =
    attempt.verdict === "PASS" && model.status === "SOLVED";
  const panel = failurePanel(attempt);

  return (
    <div className="attempt-card__body">
      {accepted ? (
        <>
          <div className="attempt-accepted">
            <span className="attempt-accepted__label">Accepted</span>
            <LlmVerifiedBadge />
          </div>
          <CandidateCard attempt={attempt} accepted />
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

/**
 * Attempts timeline: newest first, latest expanded by default, earlier
 * attempts collapsed (spec §9). Candidates render in the unverified register;
 * ids and artifacts stay in the Inspector.
 */
export function AttemptsTab({ model, onInspectAttempt }: Props) {
  const latestId =
    model.attempts.length > 0
      ? model.attempts[model.attempts.length - 1].attempt_id
      : null;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (model.attempts.length === 0 && model.status !== "RUNNING") {
    return (
      <p className="attempts-empty">
        Attempts appear here once the first attempt has run.
      </p>
    );
  }

  const newestFirst = [...model.attempts].reverse();

  return (
    <div className="attempts-tab">
      {model.status === "RUNNING" && (
        <RunningIndicator phaseHint={model.running_phase_hint} />
      )}
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
