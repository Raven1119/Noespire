import { useEffect, useState } from "react";
import { MathText } from "../components/MathText";

type PhaseHint = "generating" | "checking" | null;

const PHASE_TEXT: Record<Exclude<PhaseHint, null>, string> = {
  generating: "Generating candidate…",
  checking: "Checking candidate…",
};

const NODE_PHASE_VERB: Record<Exclude<PhaseHint, null>, string> = {
  generating: "Proving",
  checking: "Checking",
};

/**
 * RUNNING display: the phase line is a UI heuristic from
 * `running_phase_hint` — never a claimed backend phase — so it carries a
 * `live · phase inferred` marker (spec §2, §9). When the read model projects
 * exactly one RUNNING scaffold node, the line names it ("Proving/Checking
 * <statement>…"); otherwise it stays generic. The elapsed clock is
 * session-scoped: it starts when the page first observes RUNNING and is
 * never persisted; it disappears with the component on terminal states.
 */
export function RunningIndicator({
  phaseHint,
  nodeStatement = null,
}: {
  phaseHint: PhaseHint;
  /** Statement of the single RUNNING scaffold node, when reliably known. */
  nodeStatement?: string | null;
}) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const id = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const mm = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
  const ss = String(elapsedSeconds % 60).padStart(2, "0");

  return (
    <div className="running-indicator">
      {phaseHint !== null && (
        <p className="running-indicator__phase">
          {nodeStatement !== null ? (
            <>
              {NODE_PHASE_VERB[phaseHint]} <MathText text={nodeStatement} />
              …{" "}
            </>
          ) : (
            <>{PHASE_TEXT[phaseHint]} </>
          )}
          <span className="running-indicator__marker">live · phase inferred</span>
        </p>
      )}
      <p className="running-indicator__elapsed">{mm}:{ss} on this page</p>
    </div>
  );
}
