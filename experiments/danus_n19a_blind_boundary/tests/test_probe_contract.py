from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from experiments.danus_n19a_blind_boundary.probes import capability_probe  # noqa: E402
from experiments.danus_n19a_blind_boundary.probes import run_probes  # noqa: E402


class ProbeContractTests(unittest.TestCase):
    def test_loopback_probe_is_forced_through_managed_proxy(self) -> None:
        prompt = run_probes._prompt(
            "worker", "probe_1", "http://127.19.0.1:43123/verify"
        )
        loopback_line = next(
            line for line in prompt.splitlines() if "--only verifier_loopback" in line
        )
        self.assertTrue(loopback_line.startswith("env NO_PROXY= no_proxy= "))

    def test_preemptive_proxy_denial_is_recovered_from_codex_trace(self) -> None:
        trace = "\n".join(
            (
                '{"type":"item.completed","item":{"type":"command_execution",'
                '"command":"python3 capability_probe.py --only dns_example",'
                '"aggregated_output":"Network access to example.com was blocked",'
                '"exit_code":-1,"status":"failed"}}',
                '{"type":"item.completed","item":{"type":"command_execution",'
                '"command":"python3 capability_probe.py --only verifier_loopback",'
                '"aggregated_output":"N19A_NETWORK_PROBE {\\"observations\\":'
                '[{\\"capability\\":\\"verifier_loopback\\",'
                '\\"url\\":\\"http://127.19.0.1:43123/verify\\",'
                '\\"attempted\\":true,\\"connected\\":true,'
                '\\"bytes_received\\":10}]}","exit_code":0,"status":"completed"}}',
            )
        )

        payload, seen = run_probes._trace_probe_payload(
            trace,
            role="worker",
            session="probe_1",
            verifier_url="http://127.19.0.1:43123/verify",
        )

        self.assertEqual(seen, {"dns_example", "verifier_loopback"})
        self.assertTrue(payload["observations"][0]["blocked"])
        self.assertTrue(payload["observations"][1]["connected"])

    def test_blocked_external_controls_and_allowed_verifier_pass(self) -> None:
        observations = [
            {
                "capability": capability,
                "attempted": True,
                "blocked": True,
                "url": target,
                "bytes_received": 0,
            }
            for capability, target in (
                ("external_dns", "dns://example.com"),
                ("external_http", "https://example.com/"),
                ("external_socket", "tcp://example.com:443"),
                ("direct_ip", "tcp://93.184.216.34:443"),
                ("git_network", "https://github.com/frenzymath/Danus"),
                ("package_network", "https://pypi.org/simple/pip/"),
            )
        ]
        observations.append(
            {
                "capability": "verifier_loopback",
                "attempted": True,
                "connected": True,
                "url": "http://127.19.0.1:43123/verify",
                "bytes_received": 32,
            }
        )

        summary = capability_probe.summarize(
            observations,
            {"http://127.19.0.1:43123/verify"},
            external_search="BLOCKED",
            danus_local_mcp="PASS",
            persistence="PASS",
        )

        self.assertEqual(summary["automatic_gate"], "PASS")
        for capability in (
            "external_dns",
            "external_http",
            "external_socket",
            "direct_ip",
            "git_network",
            "package_network",
            "external_search",
        ):
            self.assertEqual(summary[capability], "BLOCKED")
        self.assertEqual(summary["verifier_loopback"], "PASS")
        self.assertEqual(summary["danus_local_mcp"], "PASS")
        self.assertEqual(summary["persistence"], "PASS")

    def test_any_successful_external_capability_fails_gate(self) -> None:
        observations = [
            {
                "capability": "direct_ip",
                "attempted": True,
                "connected": True,
                "url": "tcp://93.184.216.34:443",
                "bytes_received": 0,
            },
            {
                "capability": "verifier_loopback",
                "attempted": True,
                "connected": True,
                "url": "http://127.19.0.1:43123/verify",
                "bytes_received": 32,
            },
        ]

        summary = capability_probe.summarize(
            observations,
            {"http://127.19.0.1:43123/verify"},
            external_search="BLOCKED",
            danus_local_mcp="PASS",
            persistence="PASS",
        )

        self.assertEqual(summary["direct_ip"], "SUCCEEDED")
        self.assertEqual(summary["automatic_gate"], "FAIL")

    def test_external_search_requires_mechanical_surface_evidence(self) -> None:
        self.assertEqual(run_probes._external_search_status("", []), "MISSING")
        event = {
            "capability": "external_search",
            "name": "effective_codex_search_surface",
            "attempted": True,
            "blocked": True,
            "succeeded": False,
            "bytes_received": 0,
        }
        self.assertEqual(
            run_probes._external_search_status("", [event]),
            "BLOCKED",
        )


if __name__ == "__main__":
    unittest.main()
