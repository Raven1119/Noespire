from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ANALYSIS_DIR = Path(__file__).parent
EXPERIMENT_DIR = ANALYSIS_DIR.parent
sys.path.insert(0, str(ANALYSIS_DIR))
sys.path.insert(0, str(EXPERIMENT_DIR))

import analyze_runs  # noqa: E402
import audit_leakage  # noqa: E402
import run_once  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


def rejected_run(tmp_path: Path) -> Path:
    run = tmp_path / "rejected_run"
    project = run / "project_artifacts"
    worker = project / "workers" / "high"
    (worker / "logs").mkdir(parents=True)
    (worker / "logs" / "round_1.log").write_text("tokens used\n123\n", encoding="utf-8")
    write_json(worker / ".status.json", {"round_started_at": 10, "last_round_at": 15})
    (project / "fact_graph" / "facts").mkdir(parents=True)
    write_jsonl(
        project / "global_memory" / "verification.jsonl",
        [{
            "id": "v1",
            "author": "high",
            "claim": "Target theorem.",
            "verdict": "incorrect",
            "fact_id": None,
            "links": {"source_id": "p1", "predecessors": []},
            "verification_report": {"summary": "A concrete gap remains."},
        }],
    )
    write_jsonl(
        project / "global_memory" / "proof_attempt.jsonl",
        [{"id": "p1", "author": "high", "claim": "Target theorem.", "evidence": "Attempt."}],
    )
    (run / "input.md").write_text("Target theorem.\n", encoding="utf-8")
    write_json(
        run / "result.json",
        {
            "run_id": "rejected_run",
            "problem_id": "rejected",
            "classification": "DANUS_FAILED_TO_SOLVE",
            "worker_attempts": 1,
            "worker_sessions": 1,
            "verifier_calls": 1,
            "verifier_accepts": 0,
            "verifier_rejects": 1,
            "accepted_fact_count": 0,
            "supporting_closure": [],
            "supporting_closure_size": 0,
            "facts_outside_closure": 0,
            "total_tokens": 123,
            "wall_clock_seconds": 5,
            "waste_ratio": None,
        },
    )
    return run


class AnalysisTests(unittest.TestCase):
    def test_analyzer_preserves_rejected_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metric, rows, _packet = analyze_runs.analyze_run(rejected_run(Path(directory)))

        self.assertEqual(metric["search_failed_attempts"], 1)
        self.assertEqual(metric["failed_proof_cost"], 1.0)
        self.assertEqual(rows[0]["verifier_result"], "FAIL")
        self.assertEqual(rows[0]["fact_id"], "")

    def test_analyzer_preserves_run_when_token_marker_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = rejected_run(Path(directory))
            worker_log = run / "project_artifacts/workers/high/logs/round_1.log"
            worker_log.write_text("partial trace without usage footer\n", encoding="utf-8")
            metric, rows, _packet = analyze_runs.analyze_run(run)

        self.assertEqual(metric["failed_proof_cost"], "unavailable")
        self.assertEqual(rows[0]["tokens"], "unavailable")
        self.assertEqual(analyze_runs.sum_observable([1, "unavailable"]), "unavailable")

    def test_leakage_audit_handles_zero_facts_and_records_blocked_search(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            run = rejected_run(tmp_path)
            (run / "blind_wrapper.log").write_text(
                "x\trole=worker\tpolicy=blind\nx\trole=verifier\tpolicy=blind\n",
                encoding="utf-8",
            )
            (run / "verifier_service.log").write_text(
                'INFO POST /verify HTTP/1.1" 200\n', encoding="utf-8"
            )
            event_path = run / "project_artifacts/workers/high/local_memory/events.jsonl"
            write_jsonl(
                event_path,
                [{
                    "event_type": "search_math_results_stalled",
                    "attempted_queries": ["exact target theorem lookup"],
                    "primary_tool": "search_arxiv_theorems",
                    "reason": "tool is not exposed",
                }],
            )
            reference_dir = tmp_path / "reference"
            reference_dir.mkdir()
            (reference_dir / "rejected-reference.md").write_text(
                "# Private\n\n## Reference proof\n\nA private proof.\n", encoding="utf-8"
            )

            audit = audit_leakage.audit_run(run, reference_dir, tmp_path, "PASS")

        self.assertEqual(audit["integrity"], "BLIND_INTEGRITY_PASS")
        self.assertIsNone(audit["reference_overlap"]["accepted_facts"]["strongest"])
        self.assertEqual(
            audit["blocked_theorem_search_intents"][0]["attempted_queries"],
            ["exact target theorem lookup"],
        )

    def test_failure_snapshot_excludes_caches_and_keeps_verifier_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            project = tmp_path / "project"
            (project / "facts").mkdir(parents=True)
            (project / "facts" / "keep.md").write_text("evidence", encoding="utf-8")
            for ignored in (".agents", ".git", ".lake", "__pycache__"):
                (project / ignored).mkdir()
                (project / ignored / "cache").write_text("ignore", encoding="utf-8")
            verify_runs = tmp_path / "verify-runs"
            (verify_runs / "old").mkdir(parents=True)
            (verify_runs / "new").mkdir()
            (verify_runs / "new" / "verification.json").write_text("{}", encoding="utf-8")
            run_dir = tmp_path / "run"
            run_dir.mkdir()

            run_ids = run_once.preserve_runtime_artifacts(project, run_dir, verify_runs, {"old"})

            self.assertEqual(run_ids, ["new"])
            self.assertTrue((run_dir / "project_artifacts/facts/keep.md").is_file())
            self.assertFalse(any(
                (run_dir / "project_artifacts" / ignored).exists()
                for ignored in (".agents", ".git", ".lake", "__pycache__")
            ))
            self.assertTrue(
                (run_dir / "verifier_outputs/new/verification.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
