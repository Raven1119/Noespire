"""N2Z public live and result interfaces; no model calls."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for rel in ("src", "experiments/n2l_closed_book_long_horizon",
            "experiments/n2m_horizon_handoff", "experiments/n2p_mathematical_strategist",
            "experiments/n2q_auditor_guided_revision", "experiments/n2r_strategist_stability",
            "experiments/n2s_strategy_patch_separation", "experiments/n2t_strategy_patch_compilation",
            "experiments/n2u_live_two_stage", "experiments/n2v_two_stage_replication",
            "experiments/n2y_local_verified_boundary", "experiments/n2z_live_boundary"):
    sys.path.insert(0, str(ROOT / rel))

import run_n2u
from boundary_builder import BoundaryAwarePatchBuilder


@pytest.mark.parametrize("injected", [False, True, "runner"])
def test_live_uses_selected_builder_without_changing_solver(monkeypatch, tmp_path, injected):
    from functools import partial
    from experiment_fixtures import failed_baseline
    from research.problem import ProblemSpec

    n2l = run_n2u.n2l
    baseline = failed_baseline(
        tmp_path / "baseline", ProblemSpec(n2l.ERDOS67_PROBLEM_ID, n2l.ERDOS67_PROBLEM))
    monkeypatch.setattr(n2l, "ERDOS67_BASELINE", baseline)
    monkeypatch.setattr(n2l, "prepare_erdos67", partial(n2l.prepare_erdos67, baseline_dir=baseline))
    calls = []

    class ScriptedInvoker:
        def __init__(self, **kwargs):
            kwargs["audit_dir"].mkdir(parents=True)

        def invoke(self, *, prompt, schema, label):
            calls.append((label, prompt))
            if label == "research_worker":
                goal = prompt.split("Current subgoal:\n", 1)[1].split("\n\nExisting accepted facts:", 1)[0]
                return {"statement": goal, "proof": "Incomplete proof.", "predecessors": []}
            if label == "closed_book_verifier":
                return {"accepted": False, "reason": "Missing argument", "external_authority_dependency": False, "violation_type": "NONE"}
            if label == "strategy_sketcher":
                return {"obstruction": "Missing bound", "evidence": ["Rejected proof"],
                        "mathematical_idea": "Prove two bounds", "why_this_reduces_difficulty": "Separate estimates",
                        "operator": "INSERT_CUT_SET", "why_current_route_is_exhausted": "Missing bound",
                        "decline_reason": "", "candidate_claims": ["First bound", "Second bound"]}
            if label == "n2s_sketch_audit":
                return {"strategy_class": "USEFUL_STRATEGY", "strategy_family": "bounds", "reasons": [], "difficulty_reduction": "UNCLEAR"}
            if label.endswith("patch_builder"):
                return {"compilation_decline": True, "decline_reason": "Cannot compile", "new_nodes": []}
            raise AssertionError(label)

    monkeypatch.setattr(run_n2u, "ClosedBookCodexInvoker", ScriptedInvoker)
    if injected == "runner":
        import run_n2z
        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, "test-version", ""))
        case = tmp_path / "new_run"
        result = run_n2z.run_live(case)
        manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
        assert "experiments/n2y_local_verified_boundary/boundary_builder.py" in manifest["file_hashes"]
        assert result["n2z"]["attempts"]["historical"]["count"] == 3
        assert result["n2z"]["historical_attempts_unchanged"]
        assert json.loads((case / "input_check_after.json").read_text())["source_unchanged"]
    else:
        kwargs = {"builder_factory": BoundaryAwarePatchBuilder} if injected else {}
        result = run_n2u.run_live(tmp_path, **kwargs)
    builders = [(label, prompt) for label, prompt in calls if label.endswith("patch_builder")]
    assert len(builders) == 1
    assert builders[0][0] == ("boundary_aware_patch_builder" if injected else "strategy_bound_patch_builder")
    assert ("VERIFIED LOCAL BOUNDARY INPUTS" in builders[0][1]) == bool(injected)
    assert result["metrics"]["solver_attempts_during_run"] == 3
    assert result["metrics"]["fact_count"] == 0


def test_summary_separates_historical_errors(tmp_path):
    from n2z_results import summarize_run
    (tmp_path / "attempts").mkdir()
    for name, record in {"old": {"verdict": "ERROR", "error": "TimeoutExpired: timeout"},
                         "new": {"verdict": "ERROR", "error": "ValueError: broken"}}.items():
        (tmp_path / "attempts" / f"{name}.json").write_text(json.dumps(record))
    result = summarize_run(tmp_path, {"fact_audit": []}, initial_attempt_ids=["old.json"])
    assert result["attempts"]["historical"]["timeouts"] == 1
    assert result["attempts"]["during_run"]["timeouts"] == 0
    assert result["attempts"]["during_run"]["other_errors"] == 1


@pytest.mark.parametrize("ancestor_audit", ["SUBSTANTIVE", "AUDIT_ERROR", "INVALID", None])
@pytest.mark.parametrize("replacement", [False, True])
def test_only_applied_cut_descendants_with_complete_audits_count(tmp_path, ancestor_audit, replacement):
    from n2z_results import summarize_run
    from research.fact import Fact
    from research.graph import FactGraph
    graph = FactGraph(tmp_path)
    def fact(statement, predecessors=()):
        return graph.add_fact(Fact.create(problem_id="p", author="worker", statement=statement,
                                         proof="Proof", predecessors=predecessors))
    ancestor = fact("Ancestor")
    boundary = fact("Boundary", [ancestor.fact_id])
    child = fact("Child", [boundary.fact_id])
    unrelated = fact("Unrelated", [boundary.fact_id])
    nodes = [{"node_id": "new_child", "resolved_by_fact_id": child.fact_id, "depends_on": []},
             {"node_id": "unrelated", "resolved_by_fact_id": unrelated.fact_id, "depends_on": []}]
    (tmp_path / "scaffold.json").write_text(json.dumps({"target_node_id": "new_child", "nodes": nodes}))
    (tmp_path / "local_refinements").mkdir()
    record = {
        "applied": True, "outcome": "APPLIED", "blocked_node_id": "blocked",
        "context": {"allowed_operation": "INSERT_CUT_SET",
                    "verified_boundary": [{"fact_id": boundary.fact_id}]},
        "proposal": {"proposal_id": "cut-final", "children": [
            {"node_id": "new_child", "premise_fact_ids": [boundary.fact_id]}]},
    }
    (tmp_path / "local_refinements" / "cut-final.json").write_text(json.dumps(record))
    if replacement:
        nodes[0]["resolved_by_fact_id"] = None
        nodes[0]["superseded_by"] = "cut-replacement"
        nodes.append({"node_id": "replacement", "resolved_by_fact_id": child.fact_id, "depends_on": []})
        (tmp_path / "scaffold.json").write_text(json.dumps({"target_node_id": "replacement", "nodes": nodes}))
        replacement_record = json.loads(json.dumps(record))
        replacement_record["blocked_node_id"] = "new_child"
        replacement_record["proposal"] = {"proposal_id": "cut-replacement", "children": [{"node_id": "replacement", "premise_fact_ids": [boundary.fact_id]}]}
        (tmp_path / "local_refinements" / "cut-replacement.json").write_text(json.dumps(replacement_record))
    audits = [{"fact_id": f.fact_id, "classification": "SUBSTANTIVE"} for f in (boundary, child, unrelated)]
    if ancestor_audit:
        audits.append({"fact_id": ancestor.fact_id, "classification": ancestor_audit})
    result = summarize_run(tmp_path, {"fact_audit": audits}, initial_attempt_ids=[])
    assert result["target"]["resolved"] is True
    assert result["target"]["audited_success"] == (ancestor_audit == "SUBSTANTIVE")
    cut = result["refinements"][0]
    assert cut["cited_boundary_ids"] == [boundary.fact_id]
    assert cut["audited_descendant_fact_ids"] == ([child.fact_id] if ancestor_audit == "SUBSTANTIVE" else [])


def test_new_live_refuses_existing_directory_without_touching_evidence(tmp_path):
    from run_n2z import run_live
    marker = tmp_path / "evidence.txt"
    marker.write_text("Keep this evidence")
    with pytest.raises(FileExistsError):
        run_live(tmp_path)
    assert marker.read_text() == "Keep this evidence"
