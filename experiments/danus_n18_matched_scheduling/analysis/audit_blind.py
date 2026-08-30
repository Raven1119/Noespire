"""Run the frozen N1.6 leakage audit over all valid N1.8 runs."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
NOESPIRE_ROOT = EXPERIMENT_ROOT.parents[1]
sys.path.insert(0, str(NOESPIRE_ROOT))

from experiments.danus_n16_blind.analysis import audit_leakage as n16_audit  # noqa: E402


ARM_DIRECTORIES = ("arm_a_parallel", "arm_b_single", "arm_c_sequential")
PROTECTED_RE = re.compile(
    r"danus_n18_matched_scheduling/(?:reference|problems/manifest\.json)"
    r"|noespire-n18-references|capability_canary",
    re.I,
)


def result_bearing_runs() -> list[Path]:
    return sorted(
        result.parent
        for directory in ARM_DIRECTORIES
        for result in (EXPERIMENT_ROOT / directory).glob("*/result.json")
    )


def audit_run(run: Path, reference_dir: Path, gate: str) -> dict[str, Any]:
    previous = n16_audit.PROTECTED_RE
    try:
        n16_audit.PROTECTED_RE = PROTECTED_RE
        return n16_audit.audit_run(run, reference_dir, NOESPIRE_ROOT, gate)
    finally:
        n16_audit.PROTECTED_RE = previous


def apply_integrity(result_path: Path, audit: dict[str, Any]) -> None:
    before = json.loads(result_path.read_text(encoding="utf-8"))
    if before["run_id"] != audit["run_id"]:
        raise ValueError(f"audit/result run mismatch: {audit['run_id']} != {before['run_id']}")
    integrity = audit["integrity"]
    if integrity not in {"BLIND_INTEGRITY_PASS", "BLIND_INTEGRITY_FAIL"}:
        raise ValueError(f"unexpected integrity value: {integrity}")
    if before["blind_integrity"] == integrity:
        return
    if before["blind_integrity"] != "PENDING_POST_RUN_AUDIT":
        raise ValueError(f"refusing to replace prior audit state in {before['run_id']}")
    text = result_path.read_text(encoding="utf-8")
    old = '"blind_integrity": "PENDING_POST_RUN_AUDIT"'
    new = f'"blind_integrity": "{integrity}"'
    if text.count(old) != 1:
        raise ValueError(f"expected one pending marker in {before['run_id']}")
    result_path.write_text(text.replace(old, new), encoding="utf-8")
    after = json.loads(result_path.read_text(encoding="utf-8"))
    before.pop("blind_integrity")
    after.pop("blind_integrity")
    if before != after:
        raise RuntimeError(f"audit mutated non-integrity evidence in {audit['run_id']}")


def verify_reference_hashes(manifest: dict[str, Any], reference_dir: Path) -> None:
    for item in manifest["problems"]:
        path = reference_dir / item["reference_file"]
        if not path.is_file():
            raise ValueError(f"restored reference missing: {item['reference_file']}")
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != item["reference_sha256"]:
            raise ValueError(f"reference hash mismatch: {item['reference_file']}")


def write_integrity_sidecar(run: Path, audit: dict[str, Any]) -> None:
    if audit["integrity"] != "BLIND_INTEGRITY_FAIL":
        return
    value = {
        "classification": "SYSTEM_INVALID_RUN",
        "error_type": "BlindIntegrityFailure",
        "run_id": audit["run_id"],
        "replacement_allowed": False,
        "mathematical_result_preserved": True,
        "audit_evidence": (
            "experiments/danus_n18_matched_scheduling/analysis/blind_audit.json"
        ),
    }
    path = run / "system_invalid.json"
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != value:
            raise ValueError(f"refusing to overwrite different invalid evidence: {run.name}")
        return
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    runs = result_bearing_runs()
    if len(runs) != 18:
        raise SystemExit(f"expected 18 result-bearing runs, found {len(runs)}")
    reference_dir = EXPERIMENT_ROOT / "reference"
    manifest = json.loads(
        (EXPERIMENT_ROOT / "protocol" / "runtime_manifest.json").read_text(encoding="utf-8")
    )
    verify_reference_hashes(manifest, reference_dir)
    isolation = json.loads(
        (EXPERIMENT_ROOT / "protocol" / "reference_isolation_probe.json").read_text(
            encoding="utf-8"
        )
    )
    gate = isolation.get("automatic_gate")
    audits = [audit_run(run, reference_dir, gate) for run in runs]
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": "all 18 result-bearing N1.8 formal math runs; execution-invalid attempts excluded",
        "capability_gate": gate,
        "runs": audits,
        "summary": {
            "pass": sum(run["integrity"] == "BLIND_INTEGRITY_PASS" for run in audits),
            "fail": sum(run["integrity"] == "BLIND_INTEGRITY_FAIL" for run in audits),
            "unexpected_url_occurrences": sum(
                len(run["unexpected_url_occurrences"]) for run in audits
            ),
            "blocked_theorem_search_intents": sum(
                len(run["blocked_theorem_search_intents"]) for run in audits
            ),
            "completed_theorem_search_events": sum(
                len(run["completed_theorem_search_events"]) for run in audits
            ),
            "suspicious_reference_overlaps": sum(
                run["reference_overlap"]["assessment"] == "SUSPICIOUS_TEXTUAL_OVERLAP"
                for run in audits
            ),
        },
    }
    output_path = EXPERIMENT_ROOT / "analysis" / "blind_audit.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    for run, audit in zip(runs, audits, strict=True):
        apply_integrity(run / "result.json", audit)
        write_integrity_sidecar(run, audit)
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
