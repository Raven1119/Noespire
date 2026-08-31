"""Tests for the dev launcher (src/application/dev.py).

The subprocess seam is faked — the ordinary test suite never starts Vite
or Uvicorn. Real startup is covered by the manual smoke (docs/dev.md).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from application import dev


class FakeProcess:
    """Minimal Popen double: scripted poll() results, None once exhausted."""

    def __init__(self, poll_results) -> None:
        self._poll_results = list(poll_results)
        self.pid = 4321
        self.terminated = False
        self.killed = False

    def poll(self):
        if not self._poll_results:
            return None
        result = self._poll_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None) -> int:
        return 0


class FakePopen:
    """Records spawned commands; hands out scripted FakeProcesses."""

    def __init__(self, *processes: FakeProcess) -> None:
        self.processes = list(processes)
        self.calls = []

    def __call__(self, command, **kwargs) -> FakeProcess:
        self.calls.append({"command": command, **kwargs})
        return self.processes.pop(0)


class RepoRootTests(unittest.TestCase):
    def test_repo_root_contains_frontend_and_pyproject(self) -> None:
        root = dev.repo_root()
        self.assertTrue((root / "pyproject.toml").is_file())
        self.assertTrue((root / "frontend").is_dir())


class CommandConstructionTests(unittest.TestCase):
    def test_backend_command_is_uvicorn_factory_on_the_frozen_port(self) -> None:
        command = dev.backend_command()
        self.assertEqual(command[0], dev.sys.executable)
        self.assertIn("uvicorn", command)
        self.assertIn("--factory", command)
        self.assertIn("127.0.0.1", command)
        self.assertIn("8173", command)

    def test_frontend_command_runs_the_package_script(self) -> None:
        with mock.patch.object(dev.shutil, "which", return_value="/usr/bin/npm"):
            command = dev.frontend_command()
        self.assertEqual(command[-2:], ["run", "dev"])
        self.assertNotIn("vite", command)  # the package script, not npx vite


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_frontend_dir_is_a_clear_error(self) -> None:
        problems = dev.preflight(self.root)
        self.assertTrue(any("frontend" in problem for problem in problems))

    def test_missing_node_modules_tells_the_user_to_npm_install(self) -> None:
        (self.root / "frontend").mkdir()
        problems = dev.preflight(self.root)
        self.assertTrue(any("npm install" in problem for problem in problems))

    def test_missing_npm_is_a_clear_error(self) -> None:
        (self.root / "frontend" / "node_modules").mkdir(parents=True)
        with mock.patch.object(dev.shutil, "which", return_value=None):
            problems = dev.preflight(self.root)
        self.assertTrue(any("npm" in problem for problem in problems))

    def test_complete_checkout_passes(self) -> None:
        (self.root / "frontend" / "node_modules").mkdir(parents=True)
        with mock.patch.object(dev.shutil, "which", return_value="/usr/bin/npm"):
            problems = dev.preflight(self.root)
        self.assertEqual(problems, [])


class LifecycleTests(unittest.TestCase):
    """A dying child kills its sibling and the launcher exits non-zero;
    Ctrl+C stops both and exits zero. ``_terminate_tree`` is mocked — its
    own behavior is covered by TerminateTreeTests."""

    def serve(self, *processes: FakeProcess):
        popen = FakePopen(*processes)
        with mock.patch.object(dev, "_terminate_tree") as terminate:
            code = dev.serve(popen=popen, sleep=lambda _: None, stream=lambda _: None)
        return code, terminate, popen

    def test_frontend_crash_stops_backend_and_propagates_nonzero(self) -> None:
        backend, frontend = FakeProcess([None, None]), FakeProcess([None, 1])
        code, terminate, _ = self.serve(backend, frontend)
        self.assertNotEqual(code, 0)
        terminate.assert_any_call(backend)

    def test_backend_crash_stops_frontend_and_propagates_nonzero(self) -> None:
        backend, frontend = FakeProcess([None, 1]), FakeProcess([None, None])
        code, terminate, _ = self.serve(backend, frontend)
        self.assertNotEqual(code, 0)
        terminate.assert_any_call(frontend)

    def test_ctrl_c_stops_both_and_exits_zero(self) -> None:
        backend = FakeProcess([None])
        frontend = FakeProcess([None, KeyboardInterrupt()])
        code, terminate, _ = self.serve(backend, frontend)
        self.assertEqual(code, 0)
        terminate.assert_any_call(backend)
        terminate.assert_any_call(frontend)

    def test_children_are_spawned_with_expected_cwds(self) -> None:
        popen = FakePopen(FakeProcess([KeyboardInterrupt()]), FakeProcess([None]))
        with mock.patch.object(dev, "_terminate_tree"):
            dev.serve(popen=popen, sleep=lambda _: None, stream=lambda _: None)
        self.assertEqual(popen.calls[0]["cwd"], dev.repo_root())
        self.assertEqual(popen.calls[1]["cwd"], dev.repo_root() / "frontend")


class TerminateTreeTests(unittest.TestCase):
    def test_already_exited_process_is_left_alone(self) -> None:
        process = FakeProcess([0])
        with mock.patch.object(dev.subprocess, "run") as run:
            dev._terminate_tree(process)
        run.assert_not_called()
        self.assertFalse(process.terminated)

    def test_posix_uses_terminate(self) -> None:
        if dev.os.name == "nt":
            self.skipTest("posix path only")
        process = FakeProcess([None])
        dev._terminate_tree(process)
        self.assertTrue(process.terminated)

    def test_windows_kills_the_process_tree(self) -> None:
        if dev.os.name != "nt":
            self.skipTest("windows path only")
        process = FakeProcess([None])
        with mock.patch.object(dev.subprocess, "run") as run:
            dev._terminate_tree(process)
        command = run.call_args[0][0]
        self.assertEqual(command[0], "taskkill")
        self.assertIn("/T", command)  # whole tree — npm.cmd must not orphan node
        self.assertIn("/F", command)


class MainTests(unittest.TestCase):
    def test_preflight_failure_exits_nonzero_without_spawning(self) -> None:
        popen = FakePopen()
        with mock.patch.object(dev, "repo_root", return_value=Path("/nonexistent-root")):
            code = dev.main(popen=popen, sleep=lambda _: None)
        self.assertNotEqual(code, 0)
        self.assertEqual(popen.calls, [])

    def test_main_installs_keyboard_interrupt_handlers(self) -> None:
        """SIGINT (Ctrl+C) and, on Windows, SIGBREAK (Ctrl+Break) both raise
        KeyboardInterrupt so the supervise loop always cleans up children."""
        with mock.patch.object(dev.signal, "signal") as sig, mock.patch.object(
            dev, "serve", return_value=0
        ), mock.patch.object(dev, "preflight", return_value=[]), mock.patch.object(
            dev.Path, "mkdir", lambda self, **kw: None
        ):
            dev.main(popen=FakePopen(), sleep=lambda _: None)
        registered = {call.args[0] for call in sig.call_args_list}
        self.assertIn(dev.signal.SIGINT, registered)
        if hasattr(dev.signal, "SIGBREAK"):
            self.assertIn(dev.signal.SIGBREAK, registered)


if __name__ == "__main__":
    unittest.main()
