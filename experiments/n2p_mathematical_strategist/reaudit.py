"""One-off evidence repair (code-review fix): regenerate the three persisted
proposal audits with de-anchored, decision-time packets.

The originally persisted audits were built from packets that (a) included
the frozen pipeline's own mechanical/auditor outcomes (anchoring risk) and
(b) for the live case were rebuilt from post-run workspace state. The
mutation-free workspaces make the rebuilt context content-identical to
decision-time (no attempts/Facts were added after the decisions), so this
script rebuilds the context, re-parses the persisted strategist packet, and
re-audits. Summaries are updated in place; the new invocation artifacts are
persisted under each case's evidence dir like any other invocation.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_n2p as runner  # noqa: E402  (sets sys.path, owns PID/_agents)
from proposal_audit import build_audit_packet  # noqa: E402
from research.local_refinement import _build_context  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.scaffold import ProofScaffold  # noqa: E402
from strategist import parse_strategist_output  # noqa: E402


def _packet_for(problem_dir: Path, blocked_node_id: str) -> dict:
    packets = sorted((problem_dir / "strategist").glob(f"*-{blocked_node_id}.json"))
    if not packets:
        raise FileNotFoundError(f"no strategist packet for {blocked_node_id}")
    return json.loads(packets[0].read_text(encoding="utf-8"))


def _reaudit_one(invoker, problem_dir: Path, blocked_node_id: str) -> dict:
    packet = _packet_for(problem_dir, blocked_node_id)
    decision = parse_strategist_output(packet["raw"], blocked_node_id=blocked_node_id)
    context = _build_context(
        scaffold=ProofScaffold(problem_dir / "scaffold.json"),
        graph=FactGraph(problem_dir),
        registry=ObligationRegistry(problem_dir / "obligations.json"),
        problem_id=runner.PID,
        blocked_node_id=blocked_node_id,
    )
    auditor = runner.ProposalAuditor(invoker)
    audit = auditor.audit(build_audit_packet(context, decision))
    audit["blocked_node_id"] = blocked_node_id
    return audit


def reaudit(case: str) -> None:
    case_root = HERE / "runs" / case
    problem_dir = case_root / "workspace" / runner.PID
    evidence_dir = case_root / "evidence"
    summary_path = evidence_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    invoker, *_ = runner._agents(evidence_dir)
    if case == "erdos67":
        audits = [
            _reaudit_one(invoker, problem_dir, episode["blocked_node_id"])
            for episode in summary["episodes"]
        ]
        summary["proposal_audits"] = audits
    else:
        summary["proposal_audit"] = _reaudit_one(invoker, problem_dir, summary["frontier"])
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{case}: re-audited")


if __name__ == "__main__":
    for case in sys.argv[1:] or ("replay_state_a", "replay_state_b", "erdos67"):
        reaudit(case)
