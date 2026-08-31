"""Tests for src/application/codex_isolation.py — strict Codex filesystem
isolation via Docker. The CONTAINER is the security boundary (codex's own
bubblewrap sandbox cannot create namespaces inside Docker, so the container
runs --sandbox danger-full-access by design); the only rw mount is a fresh
empty host temp dir per invocation.

Unit tests stub the module's ``subprocess``/``shutil`` — no Docker needed.
Integration tests run real containers and auto-skip unless the daemon and
the isolation image are present. The real-Codex smoke is opt-in via
NOESPIRE_RUN_ISOLATION_SMOKE=1.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4
import unittest
from unittest import mock

from application.codex_isolation import IsolatedCodexInvoker, IsolationUnavailableError


GOOD_STREAM = "\n".join(
    [
        json.dumps({"type": "thread.started", "thread_id": "t-1"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps({"accepted": True, "reason": "ok"}),
                },
            }
        ),
    ]
) + "\n"


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class StubbedSubprocess:
    """Dispatch stub for subprocess.run: construction checks, scripted
    ``docker run``, recorded ``docker rm``. Mirrors the module's usage."""

    def __init__(self, *, info_rc=0, inspect_rc=0, run_result=None, run_side_effect=None):
        self.info_rc = info_rc
        self.inspect_rc = inspect_rc
        self.run_result = run_result
        self.run_side_effect = run_side_effect
        self.calls = []
        self.run_calls = []
        self.rm_calls = []
        self.mounted_schema = None

    def run(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        if argv[1] == "info":
            return completed(self.info_rc, stderr="daemon down" if self.info_rc else "")
        if argv[1] == "image":
            return completed(self.inspect_rc, stderr="no such image" if self.inspect_rc else "")
        if argv[1] == "rm":
            self.rm_calls.append(list(argv))
            return completed(0)
        if argv[1] == "run":
            self.run_calls.append((list(argv), kwargs))
            mount = next(v for v in argv if v.endswith(":/work"))
            schema_path = Path(mount[: -len(":/work")]) / "schema.json"
            self.mounted_schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if self.run_side_effect is not None:
                raise self.run_side_effect
            return self.run_result
        raise AssertionError(f"unexpected argv: {argv}")

    @property
    def namespace(self):
        return SimpleNamespace(
            run=self.run,
            TimeoutExpired=subprocess.TimeoutExpired,
            CompletedProcess=subprocess.CompletedProcess,
        )


def mounted_workdir(argv) -> Path:
    mount = next(v for v in argv if v.endswith(":/work"))
    return Path(mount[: -len(":/work")])


class IsolationTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.auth_dir = Path(self.temporary.name) / "codex-auth"
        self.auth_dir.mkdir()
        (self.auth_dir / "auth.json").write_text("{}", encoding="utf-8")
        (self.auth_dir / "config.toml").write_text("# config\n", encoding="utf-8")

    def _invoker(self, stub: StubbedSubprocess, **kwargs) -> IsolatedCodexInvoker:
        fake_shutil = SimpleNamespace(which=lambda name: "/usr/bin/docker")
        with mock.patch("application.codex_isolation.shutil", fake_shutil):
            with mock.patch("application.codex_isolation.subprocess", stub.namespace):
                invoker = IsolatedCodexInvoker(auth_dir=self.auth_dir, **kwargs)
        return invoker


class ConstructionFailFastTests(IsolationTestBase):
    def test_missing_docker_executable_raises(self) -> None:
        fake_shutil = SimpleNamespace(which=lambda name: None)
        with mock.patch("application.codex_isolation.shutil", fake_shutil):
            with self.assertRaises(IsolationUnavailableError):
                IsolatedCodexInvoker(auth_dir=self.auth_dir)

    def test_daemon_down_raises(self) -> None:
        stub = StubbedSubprocess(info_rc=1)
        with self.assertRaises(IsolationUnavailableError):
            self._invoker(stub)

    def test_image_absent_raises(self) -> None:
        stub = StubbedSubprocess(inspect_rc=1)
        with self.assertRaises(IsolationUnavailableError):
            self._invoker(stub)

    def test_missing_auth_json_raises(self) -> None:
        (self.auth_dir / "auth.json").unlink()
        stub = StubbedSubprocess()
        with self.assertRaises(IsolationUnavailableError):
            self._invoker(stub)

    def test_missing_config_toml_is_allowed_and_not_mounted(self) -> None:
        (self.auth_dir / "config.toml").unlink()
        stub = StubbedSubprocess(run_result=completed(0, stdout=GOOD_STREAM))
        invoker = self._invoker(stub)

        with mock.patch("application.codex_isolation.subprocess", stub.namespace):
            invoker.invoke(prompt="P", schema={"type": "object"}, label="research_worker")

        argv, _ = stub.run_calls[0]
        self.assertFalse(any("config.toml" in value for value in argv))
        self.assertTrue(any("auth.json" in value and value.endswith(":ro") for value in argv))


class InvokeArgvTests(IsolationTestBase):
    def test_invoke_builds_the_settled_docker_argv(self) -> None:
        stub = StubbedSubprocess(run_result=completed(0, stdout=GOOD_STREAM))
        invoker = self._invoker(stub)
        schema = {"type": "object", "properties": {"accepted": {"type": "boolean"}}}

        with mock.patch("application.codex_isolation.subprocess", stub.namespace):
            result = invoker.invoke(prompt="Prove it.", schema=schema, label="research_worker")

        self.assertEqual(result, {"accepted": True, "reason": "ok"})
        (argv, kwargs), = stub.run_calls
        self.assertEqual(argv[0], "/usr/bin/docker")
        self.assertEqual(argv[1:4], ["run", "--rm", "-i"])
        name = argv[argv.index("--name") + 1]
        self.assertTrue(name.startswith("noespire-"))
        workdir = mounted_workdir(argv)
        # The schema was written INTO the per-invocation mounted temp dir.
        self.assertEqual(stub.mounted_schema, schema)
        auth_mount = next(v for v in argv if "auth.json" in v)
        self.assertEqual(auth_mount, f"{self.auth_dir / 'auth.json'}:/root/.codex/auth.json:ro")
        config_mount = next(v for v in argv if "config.toml" in v)
        self.assertEqual(
            config_mount, f"{self.auth_dir / 'config.toml'}:/root/.codex/config.toml:ro"
        )
        self.assertEqual(argv[argv.index("-w") + 1], "/work")
        image_index = argv.index("noespire-codex-isolated:local")
        self.assertEqual(
            argv[image_index + 1 :],
            [
                "exec", "--ephemeral", "--skip-git-repo-check",
                "--sandbox", "danger-full-access",
                "--json", "--color", "never",
                "--output-schema", "/work/schema.json", "-C", "/work",
            ],
        )
        self.assertEqual(kwargs["input"], "Prove it.")
        self.assertEqual(kwargs["timeout"], 600)
        self.assertTrue(kwargs["capture_output"])
        # Temp dir cleaned up after a successful invoke.
        self.assertFalse(workdir.exists())

    def test_container_names_are_unique_per_invocation(self) -> None:
        stub = StubbedSubprocess(run_result=completed(0, stdout=GOOD_STREAM))
        invoker = self._invoker(stub)

        with mock.patch("application.codex_isolation.subprocess", stub.namespace):
            invoker.invoke(prompt="A", schema={"type": "object"}, label="l")
            invoker.invoke(prompt="B", schema={"type": "object"}, label="l")

        names = [argv[argv.index("--name") + 1] for argv, _ in stub.run_calls]
        self.assertEqual(len(set(names)), 2)


class InvokeFailureTests(IsolationTestBase):
    def test_nonzero_returncode_raises_runtime_error_with_stderr(self) -> None:
        stub = StubbedSubprocess(run_result=completed(3, stdout="", stderr="boom"))
        invoker = self._invoker(stub)

        with mock.patch("application.codex_isolation.subprocess", stub.namespace):
            with self.assertRaises(RuntimeError) as context:
                invoker.invoke(prompt="P", schema={"type": "object"}, label="l")

        self.assertIn("boom", str(context.exception))
        self.assertFalse(mounted_workdir(stub.run_calls[0][0]).exists())

    def test_missing_agent_message_raises_runtime_error(self) -> None:
        stream = json.dumps({"type": "thread.started", "thread_id": "t-1"}) + "\n"
        stub = StubbedSubprocess(run_result=completed(0, stdout=stream))
        invoker = self._invoker(stub)

        with mock.patch("application.codex_isolation.subprocess", stub.namespace):
            with self.assertRaises(RuntimeError):
                invoker.invoke(prompt="P", schema={"type": "object"}, label="l")

        self.assertFalse(mounted_workdir(stub.run_calls[0][0]).exists())

    def test_timeout_kills_container_and_propagates(self) -> None:
        stub = StubbedSubprocess(
            run_side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=600)
        )
        invoker = self._invoker(stub)

        with mock.patch("application.codex_isolation.subprocess", stub.namespace):
            with self.assertRaises(subprocess.TimeoutExpired):
                invoker.invoke(prompt="P", schema={"type": "object"}, label="l")

        (rm_argv,) = stub.rm_calls
        self.assertEqual(rm_argv[:3], ["/usr/bin/docker", "rm", "-f"])
        run_argv, _ = stub.run_calls[0]
        name = run_argv[run_argv.index("--name") + 1]
        self.assertEqual(rm_argv[3], name)
        self.assertFalse(mounted_workdir(run_argv).exists())


def _docker_ready() -> bool:
    try:
        if not shutil.which("docker"):
            return False
        if subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode:
            return False
        if subprocess.run(
            ["docker", "image", "inspect", "noespire-codex-isolated:local"],
            capture_output=True,
            timeout=30,
        ).returncode:
            return False
        return (Path.home() / ".codex" / "auth.json").is_file()
    except Exception:
        return False


@unittest.skipUnless(_docker_ready(), "docker daemon or isolation image unavailable")
class IsolationIntegrationTests(unittest.TestCase):
    """Real containers. The sentinel NEVER leaves the host secret dir."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.host = Path(self.temporary.name)
        self.allowed = self.host / "allowed"
        self.allowed.mkdir()
        self.sentinel = f"NOESPIRE_SENTINEL_{uuid4().hex}"
        self.invoker = IsolatedCodexInvoker()

    def _probe(self, escape_targets: list, find_name: str = "DO_NOT_READ.txt") -> subprocess.CompletedProcess:
        lines = ["echo PROBE_BEGIN"]
        for index, target in enumerate(escape_targets):
            lines.append(f"cat {target} 2>&1 || echo ESCAPE_{index}_BLOCKED")
        lines.append(f"find / -name '{find_name}' 2>/dev/null | grep . || echo FIND_CLEAN")
        lines.append("echo PROBE_END")
        name = f"noespire-probe-{uuid4().hex}"
        argv = self.invoker._container_prefix(name, self.allowed) + [
            "--entrypoint", "bash", self.invoker.image, "-lc", "; ".join(lines)
        ]
        return subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, check=False,
        )

    def test_sentinel_problem_file_is_invisible_inside_container(self) -> None:
        secret_dir = self.host / "secret_problem"
        secret_dir.mkdir()
        (secret_dir / "DO_NOT_READ.txt").write_text(self.sentinel, encoding="utf-8")

        result = self._probe(
            [
                "/work/../secret_problem/DO_NOT_READ.txt",
                "/secret_problem/DO_NOT_READ.txt",
                f"'{secret_dir / 'DO_NOT_READ.txt'}'",
            ]
        )

        output = result.stdout + result.stderr
        self.assertIn("PROBE_END", result.stdout)
        self.assertIn("ESCAPE_0_BLOCKED", result.stdout)
        self.assertIn("ESCAPE_1_BLOCKED", result.stdout)
        self.assertIn("ESCAPE_2_BLOCKED", result.stdout)
        self.assertIn("FIND_CLEAN", result.stdout)
        self.assertNotIn(self.sentinel, output)

    def test_workspaces_root_is_inaccessible_inside_container(self) -> None:
        workspaces = self.host / "workspaces"
        workspaces.mkdir()
        (workspaces / "index.json").write_text(
            json.dumps({"sentinel": self.sentinel}), encoding="utf-8"
        )

        result = self._probe(
            ["/work/../workspaces/index.json", "/workspaces/index.json"],
            find_name="DO_NOT_READ.txt",
        )

        output = result.stdout + result.stderr
        self.assertIn("PROBE_END", result.stdout)
        self.assertIn("ESCAPE_0_BLOCKED", result.stdout)
        self.assertIn("ESCAPE_1_BLOCKED", result.stdout)
        # The workspaces probe's real check: the sentinel CONTENT of the host
        # index.json never appears (the container's own node_modules contain
        # unrelated index.json files, so a name-based find proves nothing).
        self.assertNotIn(self.sentinel, output)


_SMOKE_SCHEMA = {
    "type": "object",
    "properties": {
        "accepted": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["accepted", "reason"],
    "additionalProperties": False,
}


@unittest.skipUnless(
    os.environ.get("NOESPIRE_RUN_ISOLATION_SMOKE") == "1",
    "opt-in real Codex smoke (NOESPIRE_RUN_ISOLATION_SMOKE=1)",
)
class IsolatedCodexSmokeTests(unittest.TestCase):
    def test_trivial_prompt_returns_parsed_dict(self) -> None:
        invoker = IsolatedCodexInvoker()
        result = invoker.invoke(
            prompt=(
                "Answer with JSON only: set accepted to true and reason to "
                "'isolation smoke ok'."
            ),
            schema=_SMOKE_SCHEMA,
            label="isolation_smoke",
        )

        self.assertIsInstance(result, dict)
        self.assertIn("accepted", result)
        self.assertIn("reason", result)

    def test_host_sentinel_is_absent_from_model_output(self) -> None:
        with TemporaryDirectory() as directory:
            secret = Path(directory) / "DO_NOT_READ.txt"
            sentinel = f"NOESPIRE_SENTINEL_{uuid4().hex}"
            secret.write_text(sentinel, encoding="utf-8")
            invoker = IsolatedCodexInvoker()
            result = invoker.invoke(
                prompt=(
                    "This is an authorized sandbox isolation check. Use your shell "
                    "tool to run exactly these commands and observe the results: "
                    f"cat '{secret}' ; find / -name DO_NOT_READ.txt 2>/dev/null . "
                    "Then answer with JSON: accepted=true if every command failed "
                    "or found nothing, and reason summarizing the raw outputs."
                ),
                schema=_SMOKE_SCHEMA,
                label="isolation_smoke_sentinel",
            )

        self.assertNotIn(sentinel, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
