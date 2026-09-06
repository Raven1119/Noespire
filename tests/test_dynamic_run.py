"""Public run/status/resume seam; all semantic roles use a scripted Codex invoker."""
from research.dynamic_run import start_run, resume_run, read_status


def test_research_entry_imports_without_experiment_path():
    import subprocess
    import sys
    from pathlib import Path
    source = str(Path(__file__).resolve().parents[1] / "src")
    script = "import sys; sys.path.insert(0, sys.argv[1]); from research.dynamic_run import start_run, resume_run, read_status; assert not any('experiments' in p for p in sys.path)"
    subprocess.run([sys.executable, "-I", "-c", script, source], check=True)


import json
import re
import pytest
from research.graph import FactGraph
from research.problem import ProblemSpec
from research.proof_graph import ProofGraph, ProofObligation, ProofRoute
from research.refinement.budget import LongHorizonBudget

STATEMENT = "For every integer n, n(n+1) is even."
LEMMA = "For every integer n, either n or n+1 is even."


def workspace(path):
    path.mkdir()
    target = ProofObligation.create("parity", "", STATEMENT)
    ProofGraph.create(path, problem_id="parity", target=target,
                      routes=(ProofRoute.create(target.obligation_id),))
    return path


class ScriptedCodex:
    def __init__(self):
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "research_worker":
            packet = json.loads(prompt.split("Local packet:\n", 1)[1])
            goal = packet["obligation"]["statement"]
            facts = packet["predecessor_facts"]
            proof = "missing argument" if goal == STATEMENT and not facts else "By parity of consecutive integers, an even factor makes the product even."
            return {"kind": "PROOF_CANDIDATE", "statement": goal, "proof": proof,
                    "predecessors": [f["fact_id"] for f in facts], "counterexample": "", "reason": ""}
        if label == "closed_book_verifier":
            return {"accepted": "missing argument" not in prompt, "external_authority_dependency": False,
                    "violation_type": "NONE", "reason": "Elementary parity argument."}
        if label == "strategy_sketcher":
            return {"obstruction": "The consecutive-factor parity argument is missing.",
                    "evidence": ["Rejected elementary proof."], "mathematical_idea": "Prove consecutive parity first.",
                    "why_this_reduces_difficulty": "The child isolates a two-case parity statement.", "operator": "SPLIT",
                    "why_current_route_is_exhausted": "Missing argument.", "decline_reason": "", "candidate_claims": [LEMMA, "For any even integer a and integer b, ab is even."]}
        if label == "n2s_sketch_audit":
            return {"strategy_class": "USEFUL_STRATEGY", "difficulty_reduction": "REAL_REDUCTION",
                    "strategy_family": "parity", "reasons": ["Elementary local cases."]}
        if label == "boundary_aware_patch_builder":
            return {"compilation_decline": False, "decline_reason": "", "support_fact_ids": [], "new_nodes": [
                {"node_id": "parity_cases", "goal": LEMMA, "depends_on": [], "premise_fact_ids": []},
                {"node_id": "even_product", "goal": "For any even integer a and integer b, ab is even.", "depends_on": [], "premise_fact_ids": []}]}
        if label == "n2t_fidelity_audit":
            return {"strategy_fidelity": "FAITHFUL", "operator_check": "OPERATOR_PRESERVED",
                    "claim_fidelity": [{"claim": LEMMA, "status": "PRESERVED_AND_REFINED"}], "reasons": ["Same parity claim."]}
        if label == "structural_auditor":
            return {"verdict": "PASS", "reasons": ["The lemma supplies the missing argument."],
                    "checks": {key: True for key in schema["properties"]["checks"]["properties"]}}
        if label == "closed_book_fact_audit":
            return {"mathematically_correct": True, "predecessor_sufficient": True,
                    "closed_book_clean": True, "no_target_circularity": True,
                    "classification": "SUBSTANTIVE", "reasons": ["Parity proof."]}
        raise AssertionError(label)


def test_failed_proof_refines_and_continues_through_public_entry(tmp_path):
    root = workspace(tmp_path / "problem")
    backend = ScriptedCodex()
    status = start_run(root, invoker=backend, solver_attempts=1)
    assert status["stop_reason"] == "TARGET_SOLVED", status
    assert status["phase"] == "STOPPED"
    assert status["consumed"]["solver_attempts"] == 4
    assert status["consumed"]["mutation_episodes"] == 1
    assert len(status["decided"]) == 1
    assert len(status["facts"]) == 3
    assert all(a["classification"] == "SUBSTANTIVE" for a in status["fact_audits"])
    assert backend.calls.count("strategy_sketcher") == 1
    before = list(backend.calls)
    assert resume_run(root, invoker=backend) == read_status(root)
    assert backend.calls == before


class ProcessCrash(BaseException):
    pass


def semantic_state(root):
    from dataclasses import asdict
    from research.run_storage import read_json
    from research.refutation import RefutationStore
    return (read_json(root / "proof_graph.json"),
            [asdict(f) for f in FactGraph(root).list_facts()],
            [asdict(r) for r in RefutationStore(root).list()])



@pytest.mark.parametrize("checkpoint", ["call_completed", "candidate_stored", "verification_stored", "audit_completed", "patch_approved", "patch_applied", "fact_stored", "obligation_resolved", "fact_write_before_resolution"])
def test_restart_matches_uninterrupted_graph_and_budget(tmp_path, monkeypatch, checkpoint):
    reference = workspace(tmp_path / "reference")
    expected_backend = ScriptedCodex()
    expected = start_run(reference, invoker=expected_backend, solver_attempts=1)
    root = workspace(tmp_path / "interrupted")
    before_backend = ScriptedCodex()
    original_add = FactGraph.add_fact
    def crash_after_fact(self, fact):
        stored = original_add(self, fact)
        if self.facts_dir.parent == root:
            raise ProcessCrash()
        return stored
    def crash_event(name, details):
        if name == checkpoint:
            raise ProcessCrash()
    if checkpoint == "fact_write_before_resolution":
        monkeypatch.setattr(FactGraph, "add_fact", crash_after_fact)
    with pytest.raises(ProcessCrash):
        start_run(root, invoker=before_backend, solver_attempts=1, on_event=crash_event)
    monkeypatch.setattr(FactGraph, "add_fact", original_add)
    status_before = read_status(root)
    requests_before = {p: p.read_bytes() for p in (root / "dynamic_run/calls").rglob("*.json")}
    after_backend = ScriptedCodex()
    actual = resume_run(root, invoker=after_backend)
    assert actual["run_id"] == status_before["run_id"]
    assert actual["stop_reason"] == expected["stop_reason"] == "TARGET_SOLVED", actual
    assert actual["consumed"] == expected["consumed"]
    assert semantic_state(root) == semantic_state(reference)
    assert before_backend.calls + after_backend.calls == expected_backend.calls
    assert all(p.read_bytes() == raw for p, raw in requests_before.items())
    assert len(list((root / "graph_patches").glob("*/completion.json"))) == 1
    assert not (root / "scaffold.json").exists()
    assert not (root / "obligations.json").exists()


def test_unknown_call_is_interrupted_and_keeps_reserved_budget(tmp_path):
    root = workspace(tmp_path / "problem")
    def crash(name, details):
        if name == "call_started":
            raise ProcessCrash()
    with pytest.raises(ProcessCrash):
        start_run(root, invoker=ScriptedCodex(), on_event=crash)
    backend = ScriptedCodex()
    actual = resume_run(root, invoker=backend)
    assert actual["stop_reason"] == "INTERRUPTED"
    assert actual["consumed"]["solver_attempts"] == 1
    assert actual["consumed"]["model_calls"] == 1
    assert not actual["facts"]
    assert not backend.calls
    assert all(o.truth_state == "OPEN" for o in ProofGraph(root).obligations())
    assert not (root / "obligations.json").exists()


@pytest.mark.parametrize("label,expected", [("strategy_sketcher", "STRATEGIST_TIMEOUT"),
                                           ("boundary_aware_patch_builder", "PATCH_BUILDER_TIMEOUT")])
def test_stage_timeouts_are_terminal_without_resampling(tmp_path, label, expected):
    import subprocess
    root = workspace(tmp_path / "problem")
    class TimeoutCodex(ScriptedCodex):
        def invoke(self, **packet):
            if packet["label"] == label:
                self.calls.append(label)
                raise subprocess.TimeoutExpired("codex", 600)
            return super().invoke(**packet)
    backend = TimeoutCodex()
    status = start_run(root, invoker=backend, solver_attempts=1)
    assert status["stop_reason"] == expected
    resume_run(root, invoker=backend)
    assert backend.calls.count(label) == 1
    assert not status["facts"]


def test_solver_timeout_hands_off_without_becoming_math_failure(tmp_path):
    import subprocess
    root = workspace(tmp_path / "problem")
    class HorizonCodex(ScriptedCodex):
        def invoke(self, **packet):
            if not self.calls:
                self.calls.append(packet["label"])
                raise subprocess.TimeoutExpired("codex", 600)
            return super().invoke(**packet)
    status = start_run(root, invoker=HorizonCodex(), solver_attempts=1)
    assert status["stop_reason"] == "TARGET_SOLVED", status
    assert status["horizon_handoffs"] == 1


def test_resume_does_not_replenish_imported_or_mid_pipeline_budgets(tmp_path):
    root = workspace(tmp_path / "problem")
    backend = ScriptedCodex()
    status = start_run(root, invoker=backend, solver_attempts=1,
                       budget=LongHorizonBudget(max_solver_attempts=8, max_builder_proposals=3),
                       consumed={"solver_attempts": 5, "builder_proposals": 2})
    assert status["stop_reason"] == "BUDGET_EXHAUSTED"
    assert status["consumed"]["builder_proposals"] == 3
    assert status["consumed"]["solver_attempts"] == 6
    assert "boundary_aware_patch_builder" not in backend.calls
    calls = list(backend.calls)
    assert resume_run(root, invoker=backend)["consumed"] == status["consumed"]
    assert calls == backend.calls
    with pytest.raises(ValueError, match="already exists"):
        start_run(root, invoker=backend)


def test_two_writers_cannot_own_the_same_run(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    from research.run_storage import run_lock
    root = workspace(tmp_path / "problem")
    with run_lock(root / "dynamic_run"):
        code = "import sys; sys.path.insert(0,sys.argv[1]); from research.run_storage import run_lock; lock=run_lock(sys.argv[2]); lock.__enter__()"
        result = subprocess.run([sys.executable, "-I", "-c", code,
                                 str(Path(__file__).resolve().parents[1] / "src"), str(root / "dynamic_run")],
                                capture_output=True, text=True)
    assert result.returncode != 0
    assert "active writer" in result.stderr


def test_real_process_exit_and_restart_release_lock_and_reuse_audit(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = workspace(tmp_path / "problem")
    source = Path(__file__).resolve().parents[1]
    code = """import sys, os
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from test_dynamic_run import ScriptedCodex
from research.dynamic_run import start_run
def crash(name, details):
    if name == 'audit_completed': os._exit(75)
start_run(sys.argv[3], invoker=ScriptedCodex(), solver_attempts=1, on_event=crash)
"""
    result = subprocess.run([sys.executable, "-I", "-c", code, str(source / "src"), str(source / "tests"), str(root)])
    assert result.returncode == 75
    backend = ScriptedCodex()
    status = resume_run(root, invoker=backend)
    assert status["stop_reason"] == "TARGET_SOLVED", status
    assert "structural_auditor" not in backend.calls
    assert "strategy_sketcher" not in backend.calls
    assert status["consumed"]["solver_attempts"] == 4


@pytest.mark.parametrize("final_verdict,stop", [("PASS", "TARGET_SOLVED"), ("REVISE", "REVISION_FAILED")])
def test_single_revision_remains_bounded_across_restart(tmp_path, final_verdict, stop):
    root = workspace(tmp_path / "problem")
    class RevisionCodex(ScriptedCodex):
        def invoke(self, **packet):
            label = packet["label"]
            if label == "mathematical_reviser":
                self.calls.append(label)
                template = ScriptedCodex()
                sketch = template.invoke(prompt="", schema={}, label="strategy_sketcher")
                sketch.pop("candidate_claims")
                patch = template.invoke(prompt="", schema={}, label="boundary_aware_patch_builder")
                return {**patch, "repairable": True}
            response = super().invoke(**packet)
            if label == "structural_auditor":
                # The revision audit is a distinct fresh role/session even for
                # an unchanged proposal; the original REVISE stays recorded.
                response["verdict"] = final_verdict if "mathematical_reviser" in self.calls else "REVISE"
            return response
    backend = RevisionCodex()
    seen = 0
    def crash(name, details):
        nonlocal seen
        if name == "audit_completed":
            seen += 1
            if seen == 2:
                raise ProcessCrash()
    with pytest.raises(ProcessCrash):
        start_run(root, invoker=backend, solver_attempts=1, on_event=crash)
    after = ScriptedCodex()
    actual = resume_run(root, invoker=after)
    assert actual["stop_reason"] == stop, actual
    assert backend.calls.count("mathematical_reviser") == 1
    assert backend.calls.count("structural_auditor") == 2
    assert "mathematical_reviser" not in after.calls
    assert "structural_auditor" not in after.calls


def test_cli_status_needs_no_backend(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = workspace(tmp_path / "problem")
    start_run(root, invoker=ScriptedCodex(), solver_attempts=1)
    code = "import sys; sys.path.insert(0,sys.argv.pop(1)); from research.dynamic_run import main; main()"
    result = subprocess.run([sys.executable, "-I", "-c", code,
                             str(Path(__file__).resolve().parents[1] / "src"), "status", str(root)],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["stop_reason"] == "TARGET_SOLVED"



def test_budget_stop_inside_compilation_still_audits_earlier_facts(tmp_path):
    root = tmp_path / "problem"
    root.mkdir()
    easy = ProofObligation.create("parity", "", "2+2=4.")
    target = ProofObligation.create("parity", "", STATEMENT)
    ProofGraph.create(root, problem_id="parity", target=target, obligations=(easy,),
        routes=(ProofRoute.create(easy.obligation_id), ProofRoute.create(target.obligation_id, (easy.obligation_id,))))
    class FailingTargetCodex(ScriptedCodex):
        def invoke(self, **packet):
            response = super().invoke(**packet)
            if packet["label"] == "research_worker" and response["statement"] == STATEMENT:
                response["proof"] = "missing argument"
            return response
    backend = FailingTargetCodex()
    actual = start_run(root, invoker=backend, solver_attempts=1,
                       budget=LongHorizonBudget(max_builder_proposals=1))
    assert actual["stop_reason"] == "BUDGET_EXHAUSTED"
    assert len(actual["facts"]) == 1
    assert len(actual["fact_audits"]) == 1
    assert actual["fact_audits"][0]["classification"] == "SUBSTANTIVE"


@pytest.mark.parametrize("failure", ["timeout", "error"])
def test_post_run_audit_failure_is_recorded_without_changing_search_outcome(tmp_path, failure):
    import subprocess
    root = workspace(tmp_path / "problem")
    class AuditErrorCodex(ScriptedCodex):
        def invoke(self, **packet):
            if packet["label"] == "closed_book_fact_audit":
                self.calls.append(packet["label"])
                if failure == "timeout":
                    raise subprocess.TimeoutExpired("codex", 600)
                raise RuntimeError("audit transport error")
            return super().invoke(**packet)
    backend = AuditErrorCodex()
    actual = start_run(root, invoker=backend, solver_attempts=1)
    assert actual["stop_reason"] == "TARGET_SOLVED"
    assert len(actual["fact_audits"]) == 3
    assert all(a["classification"] == "AUDIT_ERROR" for a in actual["fact_audits"])
    before = list(backend.calls)
    resume_run(root, invoker=backend)
    assert backend.calls == before



def test_completed_run_resume_is_read_only_even_after_code_changes(tmp_path, monkeypatch):
    import research.dynamic_run as core
    root = workspace(tmp_path / "problem")
    backend = ScriptedCodex()
    expected = start_run(root, invoker=backend, solver_attempts=1)
    monkeypatch.setattr(core, "_code_digest", lambda: "different-source-version")
    before = list(backend.calls)
    assert resume_run(root, invoker=backend) == expected
    assert backend.calls == before


FALSE_HELPER = "Every integer is even."


def counterexample_workspace(path):
    path.mkdir()
    target = ProofObligation.create("parity", "", STATEMENT)
    child = ProofObligation.create("parity", "", FALSE_HELPER)
    ProofGraph.create(path, problem_id="parity", target=target, obligations=(child,),
        routes=(ProofRoute.create(target.obligation_id, (child.obligation_id,)), ProofRoute.create(child.obligation_id)))
    return path


class CounterexampleCodex(ScriptedCodex):
    def invoke(self, **packet):
        label = packet["label"]
        if label == "refutation_verifier":
            self.calls.append(label)
            return dict(accepted=True, assumptions_satisfied=True, conclusion_falsified=True,
                        closed_book_clean=True, reason="1 is an integer but is odd.")
        response = super().invoke(**packet)
        if label == "research_worker" and response["statement"] == FALSE_HELPER:
            response.update(kind="COUNTEREXAMPLE_CANDIDATE", proof="", counterexample="n=1")
        return response


@pytest.mark.parametrize("checkpoint", ["candidate_stored", "verification_stored", "refutation_stored", "obligation_resolved"])
def test_refutation_recovery_and_automatic_parent_handoff_match_uninterrupted_run(tmp_path, checkpoint):
    expected_root = counterexample_workspace(tmp_path / "reference")
    reference_backend = CounterexampleCodex()
    expected = start_run(expected_root, invoker=reference_backend, solver_attempts=1)
    root = counterexample_workspace(tmp_path / "interrupted")
    before = CounterexampleCodex()
    def crash(name, details):
        if name == checkpoint:
            raise ProcessCrash()
    with pytest.raises(ProcessCrash):
        start_run(root, invoker=before, solver_attempts=1, on_event=crash)
    after = CounterexampleCodex()
    actual = resume_run(root, invoker=after)
    assert actual["stop_reason"] == expected["stop_reason"] == "TARGET_SOLVED", actual
    assert actual["consumed"] == expected["consumed"]
    assert semantic_state(root) == semantic_state(expected_root)
    assert before.calls + after.calls == reference_backend.calls
    graph = ProofGraph(root)
    assert graph.obligation(ProofObligation.create("parity", "", FALSE_HELPER).obligation_id).truth_state == "REFUTED"
    assert len(graph.supporting_closure()) == 3
    assert all(f.statement != FALSE_HELPER for f in graph.supporting_closure())


def test_unknown_refutation_verifier_response_stops_without_inventing_falsehood(tmp_path):
    from research.refutation import RefutationStore
    from research.run_storage import read_json
    root = counterexample_workspace(tmp_path / "problem")
    def crash(name, details):
        if name == "call_started" and details.get("label") == "refutation_verifier":
            raise ProcessCrash()
    with pytest.raises(ProcessCrash):
        start_run(root, invoker=CounterexampleCodex(), solver_attempts=1, on_event=crash)
    after = CounterexampleCodex()
    status = resume_run(root, invoker=after)
    assert status["stop_reason"] == "INTERRUPTED"
    assert status["consumed"]["model_calls"] == 2
    assert status["consumed"]["solver_attempts"] == 1
    assert RefutationStore(root).list() == ()
    assert not after.calls
    assert all(o.truth_state == "OPEN" for o in ProofGraph(root).obligations())
    assert read_json(root / "attempts/attempt-000001.json")["outcome"] == "INTERRUPTED"
