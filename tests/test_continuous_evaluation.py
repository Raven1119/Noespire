"""External evaluation pauses preserve the formal continuous research lifecycle."""
import json
import pytest

from experiments.continuous_proof_network.evaluate import Observation
from research.continuous_research import start_run, resume_run


class Direct:
    def __init__(self):
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "continuous_worker":
            return {"continuation": "Addition is complete.", "next_work": "",
                    "candidate": {"kind": "FACT", "goal": "1 + 1 = 2", "context": "",
                                  "proof": "By addition, 1 + 1 = 2.", "predecessors": []}}
        assert label == "closed_book_verifier"
        return {"accepted": True, "external_authority_dependency": False,
                "violation_type": "NONE", "reason": "Complete elementary proof."}


def test_first_return_pause_preserves_call_and_resume_verifies_without_repeating_worker(tmp_path):
    case = tmp_path / "case"
    workspace = case / "workspace"
    model = Direct()
    observer = Observation(case, deadline=1200, restart_probe=True, clock=lambda: 10)
    first = start_run(workspace, problem_id="addition", statement="1 + 1 = 2",
                      invoker=model, on_event=observer)
    assert first["status"] == "PAUSED"
    assert first["pause_reason"] == "evaluation recovery checkpoint"
    assert first["completed_calls"] == 1
    requests = {p.parent.name: p.read_bytes() for p in (workspace / "continuous_run/calls").glob("*/request.json")}
    second = resume_run(workspace, invoker=model,
                        on_event=Observation(case, deadline=1200, restart_probe=False, clock=lambda: 20))
    assert second["status"] == "SOLVED"
    assert model.calls == ["continuous_worker", "closed_book_verifier"]
    assert all((workspace / "continuous_run/calls" / key / "request.json").read_bytes() == value
               for key, value in requests.items())
    assert (case / "recovery_checkpoint.json").exists()


def test_expired_external_window_leaves_original_claim_open(tmp_path):
    case = tmp_path / "case"
    observer = Observation(case, deadline=10, restart_probe=False, clock=lambda: 11)
    result = start_run(case / "workspace", problem_id="addition", statement="1 + 1 = 2",
                       invoker=Direct(), on_event=observer)
    assert result["status"] == "PAUSED"
    assert result["pause_reason"] == "evaluation observation window"
    assert result["target_state"] == "OPEN"
    assert result["completed_calls"] == 0  # expired before the direct selection completed


def test_compute_collection_does_not_turn_unknown_usage_into_zero(tmp_path):
    from experiments.continuous_proof_network.evaluate import invocation_metrics, write_once
    write_once(tmp_path / "001.json", {"label": "continuous_worker", "elapsed_seconds": 7,
        "events": [{"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 25,
                    "cached_input_tokens": 80, "reasoning_output_tokens": 20}}]})
    write_once(tmp_path / "002.json", {"label": "continuous_worker", "elapsed_seconds": 600,
                                       "events": [], "error": "TIMEOUT"})
    data = invocation_metrics(tmp_path)
    assert data["actual_calls"] == 2
    assert data["reported_input_output_tokens"] == 125
    assert data["unknown_usage_calls"] == 1
    assert data["token_totals_complete"] is False
    assert data["by_role"]["continuous_worker"]["elapsed_seconds"] == 607
    assert invocation_metrics(tmp_path / "empty")["reported_input_output_tokens"] is None


def test_write_once_never_overwrites_historical_result(tmp_path):
    from experiments.continuous_proof_network.evaluate import write_once
    path = tmp_path / "result.json"
    write_once(path, {"old": True})
    with pytest.raises(FileExistsError):
        write_once(path, {"old": False})
    assert json.loads(path.read_text()) == {"old": True}


def test_freeze_rejects_wrong_feature_commit_before_runtime_or_evidence_creation(tmp_path):
    from experiments.continuous_proof_network.evaluate import freeze
    with pytest.raises(ValueError, match="feature SHA"):
        freeze(tmp_path, tmp_path / "evaluation", "0" * 40)
    assert not (tmp_path / "evaluation").exists()


def test_original_input_manifest_mismatch_is_not_silently_accepted(tmp_path):
    import experiments.continuous_proof_network.evaluate as evaluation
    path = tmp_path / "workspaces/n3d_eval/run_01/manifest.json"
    evaluation.write_once(path, {"modified": True})
    with pytest.raises(ValueError, match="source manifest"):
        evaluation.original_inputs(tmp_path)


def test_case_resume_keeps_deadline_and_completed_worker_and_audits_new_fact(tmp_path, monkeypatch):
    import experiments.continuous_proof_network.evaluate as evaluation
    import research.continuous_research as core
    import research.run_invocations as runtime_module
    model = Direct()
    runtime = {"backend": "codex", "image": "deterministic", "timeout_seconds": 600}
    manifest = {"order": ["addition"], "runtime": runtime, "observation_seconds": 1200}
    monkeypatch.setattr(evaluation, "check", lambda root: manifest)
    monkeypatch.setattr(core, "real_runtime", lambda *args: runtime)
    monkeypatch.setattr(runtime_module, "real_runtime", lambda *args: runtime)
    monkeypatch.setattr(core, "SolInvoker", lambda **kwargs: model)

    class Audit:
        def invoke(self, **kwargs):
            return {"classification": "SUBSTANTIVE", "reasons": ["Addition."],
                    **{key: True for key in ("mathematically_correct", "predecessor_sufficient",
                                             "closed_book_clean", "no_target_circularity")}}

    monkeypatch.setattr(runtime_module, "SolInvoker", lambda **kwargs: Audit())
    evaluation.write_once(tmp_path / "inputs/addition/problem.json",
                          {"problem_id": "addition", "statement": "1 + 1 = 2", "context": ""})
    evaluation.run_case(tmp_path, "addition", "start")
    case = tmp_path / "cases/addition"
    before = (case / "observation.json").read_bytes()
    assert evaluation.read(case / "start.result.json")["status"]["pause_reason"] == "evaluation recovery checkpoint"
    evaluation.run_case(tmp_path, "addition", "resume")
    assert (case / "observation.json").read_bytes() == before
    assert model.calls == ["continuous_worker", "closed_book_verifier"]
    result = evaluation.read(case / "result.json")
    assert result["solved"] is True
    assert result["substantive_facts"] == 1
    assert result["recovery"]["confirmed_results_preserved"] is True
    evaluation.run_case(tmp_path, "addition", "resume")
    assert model.calls == ["continuous_worker", "closed_book_verifier"]


def test_host_retains_failed_sample_without_retry_or_extra_resume(tmp_path, monkeypatch):
    import subprocess
    import experiments.continuous_proof_network.evaluate as evaluation
    manifest = {"order": ["n3d-01"], "feature_sha": "test", "source_manifests": {}}
    evaluation.write_once(tmp_path / "manifest.json", manifest)
    monkeypatch.setattr(evaluation, "check", lambda root: manifest)
    launches = []

    def failed_process(argv, **kwargs):
        launches.append(argv[-1])
        return subprocess.CompletedProcess(argv, 1)

    monkeypatch.setattr(evaluation.subprocess, "run", failed_process)
    evaluation.run_all(tmp_path)
    first = (tmp_path / "cases/n3d-01/result.json").read_bytes()
    evaluation.run_all(tmp_path)
    assert launches == ["start"]
    assert (tmp_path / "cases/n3d-01/result.json").read_bytes() == first
    assert evaluation.collect(tmp_path)["groups"]["n3d"]["system_errors"] == 1


def test_real_fresh_python_process_resumes_the_confirmed_worker_result(tmp_path):
    """The subprocess boundary is real; only mathematical responses are deterministic."""
    import os
    from pathlib import Path
    import subprocess
    import sys
    import experiments.continuous_proof_network.evaluate as evaluation
    script = tmp_path / "child.py"
    script.write_text('''
import json, os, runpy, sys
from pathlib import Path
import experiments.continuous_proof_network.evaluate as evaluation
import research.continuous_research as core
import research.run_invocations as runtime_module
root, phase, tests = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
Direct = runpy.run_path(tests)["Direct"]
class Local(Direct):
    def invoke(self, **kwargs):
        with (root / "actual_calls.jsonl").open("a") as f:
            f.write(json.dumps({"pid": os.getpid(), "label": kwargs["label"]}) + "\\n")
        return super().invoke(**kwargs)
class Audit:
    def invoke(self, **kwargs):
        return {"classification": "SUBSTANTIVE", "reasons": ["Addition."],
                **{k: True for k in ("mathematically_correct", "predecessor_sufficient",
                                    "closed_book_clean", "no_target_circularity")}}
runtime = {"backend": "codex", "image": "deterministic", "timeout_seconds": 600}
evaluation.check = lambda root: {"order": ["addition"], "runtime": runtime, "observation_seconds": 1200}
core.real_runtime = runtime_module.real_runtime = lambda *args: runtime
core.SolInvoker = lambda **kwargs: Local()
runtime_module.SolInvoker = lambda **kwargs: Audit()
evaluation.run_case(root, "addition", phase)
''', encoding="utf-8")
    evaluation.write_once(tmp_path / "inputs/addition/problem.json",
                          {"problem_id": "addition", "statement": "1 + 1 = 2", "context": ""})
    env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(evaluation.CHECKOUT), str(evaluation.CHECKOUT / "src"))),
           "PYTHONUTF8": "1"}
    for phase in ("start", "resume"):
        subprocess.run([sys.executable, str(script), str(tmp_path), phase, str(Path(__file__).resolve())],
                       env=env, check=True, capture_output=True, text=True, timeout=30)
    case = tmp_path / "cases/addition"
    assert evaluation.read(case / "start.result.json")["pid"] != evaluation.read(case / "resume.result.json")["pid"]
    calls = [json.loads(line) for line in (tmp_path / "actual_calls.jsonl").read_text().splitlines()]
    assert [r["label"] for r in calls] == ["continuous_worker", "closed_book_verifier"]
    assert evaluation.read(case / "result.json")["solved"] is True
