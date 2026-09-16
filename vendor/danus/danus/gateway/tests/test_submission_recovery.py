"""Independent admission/recovery tests for the substrate write gate."""
import json
from pathlib import Path

import pytest

from danus.core import FactGraph, GlobalMemory
from danus.gateway import submission


class Backend:
    def __init__(self, verdict="correct"):
        self.calls = []
        self.verdict = verdict

    def verify(self, key, candidate, predecessors):
        self.calls.append((key, candidate, predecessors))
        return {"verdict": self.verdict, "reason": "offline deterministic response"}


def submit(gate, key="one", predecessors=()):
    return gate.submit(key, problem_id="P", author="worker", statement="A local claim.",
                       proof="The complete test proof.", predecessors=predecessors)


def test_confirmed_submit_is_idempotent_and_source_is_danus(tmp_path):
    backend = Backend()
    gate = submission.SubmissionGate(tmp_path, backend)
    result = submit(gate)
    before = gate.graph.get_raw(result["fact_id"])
    assert submit(gate) == result
    assert len(backend.calls) == 1
    assert len(gate.graph.list()) == 1
    assert gate.graph.get_raw(result["fact_id"]) == before
    assert len(GlobalMemory(tmp_path).read("verification")) == 1


@pytest.mark.parametrize("kind", ["missing", "revoked", "cross_problem"])
def test_illegal_predecessor_rejected_before_backend(tmp_path, kind):
    backend = Backend()
    gate = submission.SubmissionGate(tmp_path, backend)
    if kind == "missing":
        fid = "a" * 16
    else:
        fid = gate.graph.add(problem_id="OTHER" if kind == "cross_problem" else "P",
                             author="w", statement="Prior.", proof="Proof.")
        if kind == "revoked":
            gate.graph.revoke(fid, "invalid")
    with pytest.raises(ValueError):
        submit(gate, predecessors=[fid])
    assert backend.calls == []


def test_verifier_confirmation_survives_crash_before_admission(tmp_path, monkeypatch):
    backend = Backend()
    gate = submission.SubmissionGate(tmp_path, backend)
    original = gate.graph.add
    def crash(**kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(gate.graph, "add", crash)
    with pytest.raises(KeyboardInterrupt):
        submit(gate)
    assert len(backend.calls) == 1 and gate.graph.list() == []
    monkeypatch.setattr(gate.graph, "add", original)
    result = submit(gate)
    assert result["accepted"] and len(backend.calls) == 1


def test_fact_admission_survives_crash_before_receipt(tmp_path, monkeypatch):
    backend = Backend()
    gate = submission.SubmissionGate(tmp_path, backend)
    original = submission.immutable_json
    def crash(path, value):
        if Path(path).name == "result.json":
            raise KeyboardInterrupt()
        return original(path, value)
    monkeypatch.setattr(submission, "immutable_json", crash)
    with pytest.raises(KeyboardInterrupt):
        submit(gate)
    assert len(gate.graph.list()) == 1
    before = gate.graph.get_raw(gate.graph.list()[0])
    monkeypatch.setattr(submission, "immutable_json", original)
    result = submit(gate)
    assert result["accepted"] and len(backend.calls) == 1
    assert len(gate.graph.list()) == 1 and gate.graph.get_raw(result["fact_id"]) == before


@pytest.mark.parametrize("verdict", ["wrong", "inconclusive", "timeout", "interrupted", "error"])
def test_nonaccepting_verdict_never_writes_fact_or_repeats_backend(tmp_path, verdict):
    backend = Backend(verdict)
    gate = submission.SubmissionGate(tmp_path, backend)
    result = submit(gate)
    assert not result["accepted"] and result["fact_id"] is None
    assert gate.graph.list() == []
    assert submit(gate) == result and len(backend.calls) == 1


def test_revoked_result_fails_closed_on_recovery(tmp_path):
    gate = submission.SubmissionGate(tmp_path, Backend())
    result = submit(gate)
    gate.graph.revoke(result["fact_id"], "invalid result")
    with pytest.raises(ValueError):
        submit(gate)


def test_gate_receipt_cannot_bind_unrelated_valid_fact(tmp_path):
    gate = submission.SubmissionGate(tmp_path, Backend())
    result = submit(gate)
    other = gate.graph.add(problem_id="P", author="w", statement="Different.", proof="Other proof.")
    receipt = Path(result["evidence"]) / "result.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["fact_id"] = other
    receipt.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        submit(gate)


def test_revoke_cascade_and_reinsertion_fail_closed(tmp_path):
    graph = FactGraph(tmp_path)
    source = graph.add(problem_id="P", author="w", statement="A", proof="proof A")
    child = graph.add(problem_id="P", author="w", statement="B", proof="proof B", predecessors=[source])
    graph.revoke(source, "false")
    assert graph.list() == []
    assert not graph.exists(source) and not graph.exists(child)
    with pytest.raises(ValueError):
        graph.supporting_closure(child)
    with pytest.raises(ValueError):
        graph.add(problem_id="P", author="w", statement="A", proof="proof A")
    assert (graph.revoked_dir / (source + ".md")).exists()
    assert (graph.revoked_dir / (child + ".md")).exists()
