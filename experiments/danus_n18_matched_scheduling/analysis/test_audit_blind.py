from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ANALYSIS_DIR = Path(__file__).parent
sys.path.insert(0, str(ANALYSIS_DIR))

import audit_blind  # noqa: E402


class BlindAuditTests(unittest.TestCase):
    def test_n18_private_reference_marker_is_protected(self) -> None:
        self.assertIsNotNone(
            audit_blind.PROTECTED_RE.search(
                "experiments/danus_n18_matched_scheduling/reference/hall-reference.md"
            )
        )

    def test_apply_changes_only_blind_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            original = {
                "run_id": "r1",
                "problem_id": "p1",
                "blind_integrity": "PENDING_POST_RUN_AUDIT",
                "solved": True,
                "total_tokens": 123,
            }
            result_path.write_text(json.dumps(original) + "\n", encoding="utf-8")

            audit_blind.apply_integrity(
                result_path, {"run_id": "r1", "integrity": "BLIND_INTEGRITY_PASS"}
            )

            updated = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["blind_integrity"], "BLIND_INTEGRITY_PASS")
            self.assertEqual(
                {key: value for key, value in updated.items() if key != "blind_integrity"},
                {key: value for key, value in original.items() if key != "blind_integrity"},
            )


if __name__ == "__main__":
    unittest.main()
