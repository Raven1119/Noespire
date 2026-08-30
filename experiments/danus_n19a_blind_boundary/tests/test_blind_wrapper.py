from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
WRAPPER = ROOT / "experiments/danus_n19a_blind_boundary/protocol/codex_blind_wrapper.sh"
FAKE_BACKEND = ROOT / "experiments/danus_n19a_blind_boundary/protocol/danus_fake_verifier_backend.sh"


class BlindWrapperTests(unittest.TestCase):
    def test_fake_verifier_launcher_avoids_crlf_shebang(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "verification.json"
            completed = subprocess.run(
                [
                    str(FAKE_BACKEND),
                    "exec",
                    f"Write the verification JSON to this exact path: {output}.",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.is_file())

    def run_wrapper(self, *args: str, verifier_url: str = "http://127.19.0.1:43123/verify"):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            capture = temp / "capture.sh"
            args_out = temp / "args.txt"
            env_out = temp / "env.txt"
            capture.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$@\" >\"$N19A_TEST_ARGS\"\n"
                "env | sort >\"$N19A_TEST_ENV\"\n",
                encoding="utf-8",
            )
            capture.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "N19A_REAL_CODEX_BIN": str(capture),
                    "N19A_TEST_ARGS": str(args_out),
                    "N19A_TEST_ENV": str(env_out),
                    "N19A_ALLOWED_LOOPBACK_PORT": "43123",
                    "N19A_CAPABILITY_PROBE": "1",
                    "DANUS_VERIFY_URL": verifier_url,
                    "HTTP_PROXY": "http://127.0.0.1:9999",
                    "HTTPS_PROXY": "http://127.0.0.1:9999",
                    "ALL_PROXY": "socks5://127.0.0.1:9998",
                }
            )
            completed = subprocess.run(
                [str(WRAPPER), "exec", *args],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            arguments = args_out.read_text(encoding="utf-8") if args_out.exists() else ""
            environment = env_out.read_text(encoding="utf-8") if env_out.exists() else ""
            return completed, arguments.splitlines(), environment

    def test_wrapper_enforces_os_network_profile_and_tool_denies(self) -> None:
        completed, arguments, environment = self.run_wrapper(
            "--dangerously-bypass-approvals-and-sandbox",
            "--sandbox",
            "danger-full-access",
            "--search",
            "--config",
            'permissions.n19a.network.domains={"*"="allow"}',
            "CAPABILITY_PROBE",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('approval_policy="never"', arguments)
        self.assertIn('default_permissions="n19a_blind"', arguments)
        self.assertIn("permissions.n19a_blind.network.enabled=true", arguments)
        self.assertIn("features.network_proxy=true", arguments)
        self.assertIn(
            'permissions.n19a_blind.network.domains={"127.19.0.1"="allow"}',
            arguments,
        )
        self.assertIn("permissions.n19a_blind.network.allow_local_binding=true", arguments)
        self.assertIn("permissions.n19a_blind.network.allow_upstream_proxy=false", arguments)
        self.assertIn("permissions.n19a_blind.network.enable_socks5=false", arguments)
        self.assertIn("tools.web_search=false", arguments)
        self.assertIn("--json", arguments)
        self.assertIn('mcp_servers.danus.disabled_tools=["search_arxiv_theorems"]', arguments)
        self.assertIn(
            "N19A_EXTERNAL_SEARCH_SURFACE=cli-disabled:web,arxiv,apps,plugins",
            environment,
        )
        self.assertIn('mcp_servers.danus.env.NO_PROXY=""', arguments)
        self.assertIn('mcp_servers.danus.env.no_proxy=""', arguments)
        self.assertIn(
            'mcp_servers.danus.env.DANUS_VERIFY_URL="http://127.19.0.1:43123/verify"',
            arguments,
        )
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", arguments)
        self.assertNotIn("danger-full-access", arguments)
        self.assertNotIn("--search", arguments)
        self.assertNotIn('permissions.n19a.network.domains={"*"="allow"}', arguments)
        self.assertNotIn("HTTP_PROXY=http://127.0.0.1:9999", environment)
        self.assertNotIn("HTTPS_PROXY=http://127.0.0.1:9999", environment)
        self.assertNotIn("ALL_PROXY=socks5://127.0.0.1:9998", environment)

    def test_wrapper_rejects_non_allowlisted_verifier_endpoint(self) -> None:
        completed, _, _ = self.run_wrapper(
            "CAPABILITY_PROBE", verifier_url="http://127.19.0.1:43124/verify"
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("DANUS_VERIFY_URL must equal", completed.stderr)


if __name__ == "__main__":
    unittest.main()
