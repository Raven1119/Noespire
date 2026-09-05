"""One fresh #67 live run with N2Y boundary disclosure. Never overwrites a run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for rel in ("src", "experiments/n2l_closed_book_long_horizon",
            "experiments/n2m_horizon_handoff", "experiments/n2p_mathematical_strategist",
            "experiments/n2q_auditor_guided_revision", "experiments/n2r_strategist_stability",
            "experiments/n2s_strategy_patch_separation", "experiments/n2t_strategy_patch_compilation",
            "experiments/n2u_live_two_stage", "experiments/n2v_two_stage_replication",
            "experiments/n2y_local_verified_boundary"):
    sys.path.insert(0, str(ROOT / rel))

import run_n2u
import run_experiment as n2l
from boundary_builder import BoundaryAwarePatchBuilder
from manifest import build_manifest, manifest_digest
from n2z_results import summarize_run
from sampler import tree_hash
from application.codex_isolation import DEFAULT_IMAGE


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _command(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return result.stdout.strip() if result.returncode == 0 else f"unknown: exit {result.returncode}"
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"unknown: {type(error).__name__}"


def _inputs():
    manifest = build_manifest(ROOT)
    for rel in ("experiments/n2v_two_stage_replication/manifest.py",
                "experiments/n2r_strategist_stability/sampler.py",
                "experiments/n2y_local_verified_boundary/boundary_builder.py",
                "experiments/n2z_live_boundary/run_n2z.py",
                "experiments/n2z_live_boundary/n2z_results.py",
                "docs/n2z_live_boundary_protocol.md"):
        manifest["file_hashes"][rel] = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    manifest["git_head"] = _command(["git", "rev-parse", "HEAD"])
    manifest["builder"] = "BoundaryAwarePatchBuilder"
    return manifest


def _environment():
    declared = {}
    try:
        import tomllib
        config = tomllib.loads((Path.home() / ".codex" / "config.toml").read_text(encoding="utf-8"))
        declared = {key: config.get(key, "unknown: unspecified") for key in
                    ("model", "model_reasoning_effort", "service_tier")}
    except (ImportError, OSError, ValueError) as error:
        declared = {"unknown_reason": type(error).__name__}
    return {"declared_config": declared, "effective_model": "unknown: not confirmed by invocation events",
            "python": sys.version.split()[0], "image": DEFAULT_IMAGE,
            "image_id": _command(["docker", "image", "inspect", "--format", "{{.Id}}", DEFAULT_IMAGE]),
            # docker/codex-isolated/Dockerfile already sets ENTRYPOINT ["codex"].
            "codex_cli": _command(["docker", "run", "--rm", "--pull", "never", "--network", "none", DEFAULT_IMAGE, "--version"])}


def run_live(case_root: Path) -> dict:
    """Create one new run, freeze inputs, delegate proving, supplement evidence."""
    case_root = Path(case_root)
    case_root.mkdir(parents=True, exist_ok=False)
    manifest = _inputs()
    initial = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted((n2l.ERDOS67_BASELINE / "attempts").glob("*.json"))}
    manifest["initial_attempt_hashes"] = initial
    manifest["environment"] = _environment()
    manifest["manifest_sha256"] = manifest_digest(manifest)
    _write(case_root / "manifest.json", manifest)
    try:
        # prepare_erdos67 inside run_live compares every copied file bytewise.
        # Its baseline contains 2 FAIL and 1 timeout ERROR; no later trajectory.
        summary = run_n2u.run_live(case_root, builder_factory=BoundaryAwarePatchBuilder)
        problem_dir = case_root / "workspace" / n2l.ERDOS67_PROBLEM_ID
        summary["n2z"] = summarize_run(problem_dir, summary, initial_attempt_ids=initial)
        copied = {name: hashlib.sha256((problem_dir / "attempts" / name).read_bytes()).hexdigest() for name in initial}
        summary["n2z"]["historical_attempts_unchanged"] = copied == initial
        summary["manifest_sha256"] = manifest["manifest_sha256"]
        _write(case_root / "evidence" / "manifest.json", manifest)
        _write(case_root / "evidence" / "summary.json", summary)
        return summary
    except Exception as error:
        _write(case_root / "run_error.json", {"error": f"{type(error).__name__}: {error}"})
        raise
    finally:
        after = _inputs()
        _write(case_root / "input_check_after.json", {
            "file_hashes": after["file_hashes"], "git_head": after["git_head"],
            "source_unchanged": after["file_hashes"] == manifest["file_hashes"],
            "baseline_unchanged": tree_hash(n2l.ERDOS67_BASELINE) == manifest["baseline_tree_sha256"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="run_01")
    args = parser.parse_args()
    if not args.run_id or not all(c.isalnum() or c in "_-" for c in args.run_id):
        parser.error("run-id must contain only letters, digits, _ or -")
    result = run_live(HERE / "runs" / args.run_id)
    print(json.dumps({"stop_reason": result["stop_reason"], "n2z": result["n2z"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
