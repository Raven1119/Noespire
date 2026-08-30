"""Apply N1.9a live semantics to each N1.9b result immediately after it finishes."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from experiments.danus_n16_blind.analysis import audit_leakage as live_audit
from experiments.danus_n18_matched_scheduling.analysis.audit_blind import apply_integrity


ROOT = Path(__file__).resolve().parents[1]
NOESPIRE_ROOT = ROOT.parents[1]
ARM_DIRECTORIES = ("arm_a_parallel", "arm_b_single", "arm_c_sequential")
PROTECTED_RE = re.compile(
    r"danus_n19b_matched_scheduling/(?:reference|problems/manifest\.json)"
    r"|noespire-n19b-references|private source",
    re.I,
)


def _manifest() -> dict[str, Any]:
    return json.loads((ROOT / "protocol/runtime_manifest.json").read_text(encoding="utf-8"))


def _reference_dir(manifest: dict[str, Any]) -> Path:
    private = Path(manifest["private_reference_store"])
    return private if private.is_dir() else ROOT / "reference"


def verify_reference_hashes(manifest: dict[str, Any], reference_dir: Path) -> None:
    for item in manifest["problems"]:
        path = reference_dir / item["reference_file"]
        if not path.is_file():
            raise ValueError(f"private reference missing: {item['reference_file']}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["reference_sha256"]:
            raise ValueError(f"private reference hash mismatch: {item['reference_file']}")


def _gate(manifest: dict[str, Any]) -> str:
    capability = json.loads(
        (NOESPIRE_ROOT / manifest["blind_policy"]["capability_evidence"]).read_text(
            encoding="utf-8"
        )
    )
    isolation = json.loads(
        (ROOT / "protocol/reference_isolation_probe.json").read_text(encoding="utf-8")
    )
    return (
        "PASS"
        if capability.get("automatic_gate") == "PASS"
        and isolation.get("automatic_gate") == "PASS"
        else "FAIL"
    )


def audit_run(run: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    reference_dir = _reference_dir(manifest)
    verify_reference_hashes(manifest, reference_dir)
    previous = live_audit.PROTECTED_RE
    try:
        live_audit.PROTECTED_RE = PROTECTED_RE
        return live_audit.audit_run(run, reference_dir, NOESPIRE_ROOT, _gate(manifest))
    finally:
        live_audit.PROTECTED_RE = previous


def _result_runs() -> list[Path]:
    return sorted(
        result.parent
        for directory in ARM_DIRECTORIES
        for result in (ROOT / directory).glob("*/result.json")
    )


def audit_pending_run() -> dict[str, Any]:
    pending = [
        run
        for run in _result_runs()
        if json.loads((run / "result.json").read_text(encoding="utf-8"))["blind_integrity"]
        == "PENDING_POST_RUN_AUDIT"
    ]
    if len(pending) != 1:
        raise RuntimeError(f"expected exactly one pending result, found {len(pending)}")
    manifest = _manifest()
    audit = audit_run(pending[0], manifest)
    (pending[0] / "blind_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    apply_integrity(pending[0] / "result.json", audit)
    if audit["integrity"] != "BLIND_INTEGRITY_PASS":
        raise RuntimeError(f"blind boundary failed for {pending[0].name}")
    return audit


def main() -> None:
    manifest = _manifest()
    runs = _result_runs()
    if len(runs) != manifest["analysis"]["valid_run_target"]:
        raise SystemExit(f"expected 18 valid runs, found {len(runs)}")
    audits = [audit_run(run, manifest) for run in runs]
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": "all 18 N1.9b result-bearing mathematical runs",
        "runs": audits,
        "summary": {
            "pass": sum(item["integrity"] == "BLIND_INTEGRITY_PASS" for item in audits),
            "fail": sum(item["integrity"] == "BLIND_INTEGRITY_FAIL" for item in audits),
            "external_access_succeeded": sum(
                "EXTERNAL_ACCESS_SUCCEEDED" in item["boundary_classifications"]
                for item in audits
            ),
        },
    }
    (ROOT / "analysis/blind_audit.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    if output["summary"]["fail"]:
        raise SystemExit(1)
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
