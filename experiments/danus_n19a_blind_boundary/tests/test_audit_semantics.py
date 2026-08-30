from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from experiments.danus_n16_blind.analysis import audit_leakage  # noqa: E402


ALLOWLIST = {"http://127.19.0.1:43123/verify"}


class BoundaryAuditTests(unittest.TestCase):
    def test_search_intent_without_external_event_does_not_fail(self) -> None:
        event = {"intent": True, "attempted": False}
        self.assertEqual(
            audit_leakage.classify_boundary_event(event, ALLOWLIST),
            "SEARCH_INTENT_BLOCKED",
        )
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "PASS")

    def test_blocked_outbound_attempt_is_not_leakage(self) -> None:
        event = {
            "attempted": True,
            "blocked": True,
            "url": "https://example.com/",
            "bytes_received": 0,
        }
        self.assertEqual(
            audit_leakage.classify_boundary_event(event, ALLOWLIST),
            "OUTBOUND_ATTEMPT_BLOCKED",
        )
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "PASS")

    def test_successful_external_connection_fails_integrity(self) -> None:
        event = {
            "attempted": True,
            "connected": True,
            "url": "https://example.com/",
            "bytes_received": 0,
        }
        self.assertEqual(
            audit_leakage.classify_boundary_event(event, ALLOWLIST),
            "EXTERNAL_ACCESS_SUCCEEDED",
        )
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "FAIL")

    def test_external_response_bytes_fail_integrity(self) -> None:
        event = {
            "attempted": True,
            "blocked": True,
            "url": "https://example.com/",
            "bytes_received": 1,
        }
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "FAIL")

    def test_expected_loopback_verifier_traffic_is_allowed(self) -> None:
        event = {
            "attempted": True,
            "connected": True,
            "url": "http://127.19.0.1:43123/verify",
            "bytes_received": 12,
        }
        self.assertEqual(
            audit_leakage.classify_boundary_event(event, ALLOWLIST),
            "LOOPBACK_ALLOWED",
        )
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "PASS")

    def test_unexpected_non_loopback_url_fails_integrity(self) -> None:
        event = {"url": "https://unexpected.example/source"}
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "FAIL")

    def test_same_loopback_endpoint_with_wrong_path_fails_integrity(self) -> None:
        event = {
            "attempted": True,
            "connected": True,
            "url": "http://127.19.0.1:43123/unexpected",
            "bytes_received": 1,
        }
        self.assertEqual(audit_leakage.boundary_integrity([event], ALLOWLIST), "FAIL")


if __name__ == "__main__":
    unittest.main()
