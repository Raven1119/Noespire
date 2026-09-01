import importlib.util
import json
from pathlib import Path

from research.agents import _blind_exec_options


REPOSITORY = Path(__file__).resolve().parents[1]
RUN_PATH = REPOSITORY / "experiments" / "n113_static_scaffold_architect" / "run.py"
SPEC = importlib.util.spec_from_file_location("n113_experiment_run", RUN_PATH)
assert SPEC and SPEC.loader
n113_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n113_run)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_blind_boundary_check_requires_exact_loopback_only_option_set(
    tmp_path: Path, monkeypatch
) -> None:
    case_id = "blind-case"
    case_dir = tmp_path / case_id
    protocol = {"model": "gpt-test", "reasoning_effort": "medium"}
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--model",
        "gpt-test",
        "--config",
        'model_reasoning_effort="medium"',
        *_blind_exec_options(),
    ]
    _write_json(
        case_dir / "blind_boundary_evidence.json",
        {
            "workspace_entries_before": [],
            "workspace_entries_after": [],
            "workspace_removed_after_case": True,
        },
    )
    audit_path = case_dir / "architect_audit.json"
    _write_json(
        audit_path,
        {
            "label": "scaffold_architect",
            "thread_id": "fresh-thread",
            "command": command,
        },
    )
    monkeypatch.setattr(n113_run, "RUNS", tmp_path)

    assert n113_run._architect_blind_boundary_pass(
        {"problem_id": case_id}, protocol
    )

    weakened = list(command)
    weakened.remove('permissions.n113_blind.network.domains={"127.19.0.1"="allow"}')
    _write_json(
        audit_path,
        {
            "label": "scaffold_architect",
            "thread_id": "fresh-thread",
            "command": weakened,
        },
    )
    assert not n113_run._architect_blind_boundary_pass(
        {"problem_id": case_id}, protocol
    )
