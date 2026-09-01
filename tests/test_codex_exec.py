import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from research.agents import CodexExec


def test_blind_codex_exec_pins_model_effort_and_disables_retrieval() -> None:
    stream = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "fresh-thread"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": '{"ok": true}'},
                }
            ),
        ]
    )
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=stream + "\n", stderr=""
    )

    with TemporaryDirectory() as directory:
        root = Path(directory)
        audit_dir = root / "audits"
        invoker = CodexExec(
            workdir=root,
            audit_dir=audit_dir,
            executable="codex-test",
            model="gpt-test",
            reasoning_effort="medium",
            blind=True,
        )
        with mock.patch("research.agents.subprocess.run", return_value=completed) as run:
            result = invoker.invoke(
                prompt="decompose only",
                schema={"type": "object"},
                label="scaffold_architect",
            )

        command = run.call_args.args[0]
        assert result == {"ok": True}
        assert command[command.index("--model") + 1] == "gpt-test"
        assert 'model_reasoning_effort="medium"' in command
        assert "--skip-git-repo-check" in command
        assert "--ignore-user-config" in command
        assert "--ignore-rules" in command
        for feature in (
            "standalone_web_search",
            "search_tool",
            "browser_use",
            "apps",
            "plugins",
            "multi_agent",
        ):
            assert command[command.index("--disable", command.index(feature) - 1) + 1] == feature

        audit = json.loads(next(audit_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert audit["thread_id"] == "fresh-thread"
        assert audit["command"] == command


def test_codex_exec_records_timeout_as_invocation_evidence() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        audit_dir = root / "audits"
        invoker = CodexExec(
            workdir=root,
            audit_dir=audit_dir,
            executable="codex-test",
            timeout_seconds=7,
        )
        timeout = subprocess.TimeoutExpired(cmd="codex-test", timeout=7)

        with mock.patch("research.agents.subprocess.run", side_effect=timeout):
            with pytest.raises(subprocess.TimeoutExpired):
                invoker.invoke(
                    prompt="decompose only",
                    schema={"type": "object"},
                    label="scaffold_architect",
                )

        audit = json.loads(next(audit_dir.glob("*.json")).read_text(encoding="utf-8"))
        assert audit["returncode"] is None
        assert audit["thread_id"] is None
        assert "TimeoutExpired" in audit["error"]
