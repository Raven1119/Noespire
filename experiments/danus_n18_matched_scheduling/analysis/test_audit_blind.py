from __future__ import annotations

import json
import hashlib
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

    def test_reference_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reference_dir = Path(directory)
            reference = reference_dir / "p-reference.md"
            reference.write_text("frozen reference\n", encoding="utf-8")
            manifest = {
                "problems": [
                    {
                        "reference_file": reference.name,
                        "reference_sha256": hashlib.sha256(b"different\n").hexdigest(),
                    }
                ]
            }

            with self.assertRaisesRegex(ValueError, "reference hash mismatch"):
                audit_blind.verify_reference_hashes(manifest, reference_dir)

    def test_failed_audit_gets_system_invalid_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            audit_blind.write_integrity_sidecar(
                run,
                {"run_id": "r1", "integrity": "BLIND_INTEGRITY_FAIL"},
            )

            sidecar = json.loads((run / "system_invalid.json").read_text(encoding="utf-8"))
            self.assertEqual(sidecar["classification"], "SYSTEM_INVALID_RUN")
            self.assertEqual(sidecar["error_type"], "BlindIntegrityFailure")
            self.assertFalse(sidecar["replacement_allowed"])
            self.assertEqual(
                sidecar["audit_evidence"],
                "experiments/danus_n18_matched_scheduling/analysis/blind_audit.json",
            )

            # A repeated deterministic audit must accept its own prior evidence.
            audit_blind.write_integrity_sidecar(
                run,
                {"run_id": "r1", "integrity": "BLIND_INTEGRITY_FAIL"},
            )


if __name__ == "__main__":
    unittest.main()
