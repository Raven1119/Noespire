"""Frozen original-question evaluation through the formal CRPN facade."""
from collections import Counter
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Timer
import time

from research.continuous_research import pause_run

CHECKOUT = Path(__file__).resolve().parents[2]
SOURCES = {"n3d": (16, "4c44a03ccf23feaecf98aa303abb3223bfcd95ca9bf02a4ebff1c5ab6b8ff01a"),
           "n3e": (4, "89a3f8eabf269c42875438714b4fd4bd3f4a258dd8bc66922372fca94bc77454")}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(CHECKOUT), *args], text=True).strip()


def original_inputs(source_root):
    """Read only original input metadata; never open historical proofs or oracles."""
    inputs, sources = [], {}
    for group, (count, expected) in SOURCES.items():
        root = Path(source_root) / f"workspaces/{group}_eval/run_01"
        if digest(root / "manifest.json") != expected:
            raise ValueError("original source manifest changed: " + group)
        manifest = read(root / "manifest.json")
        if digest(root / "harness/candidates.json") != manifest["harness_hashes"]["candidates.json"]:
            raise ValueError("original candidate bytes changed")
        candidates = read(root / "harness/candidates.json")
        if [c["id"] for c in candidates] != [f"{group}-{i:02}" for i in range(1, count + 1)]:
            raise ValueError("original candidate order changed")
        hashes = manifest.get("input_hashes", manifest.get("inputs_hashes"))
        for candidate in candidates:
            path = root / "inputs" / candidate["id"] / "proof_graph.json"
            if digest(path) != hashes[candidate["id"] + "/proof_graph.json"]:
                raise ValueError("original graph bytes changed")
            graph = read(path)
            claim = graph["obligations"][graph["target_obligation_id"]]
            route = next(iter(graph["routes"].values()))
            if (len(graph["obligations"]) != 1 or len(graph["routes"]) != 1 or claim["truth_state"] != "OPEN"
                    or claim["goal"] != candidate["statement"] or route["kind"] != "DIRECT"
                    or route["support_fact_ids"] or route["prerequisite_obligation_ids"]):
                raise ValueError("unexpected initial mathematical information")
            inputs.append({"problem_id": candidate["id"], "statement": candidate["statement"], "context": claim["context"],
                           "group": group, "control": candidate.get("control", False), "original_graph_path": str(path)})
        sources[group] = {"manifest_sha256": expected, "candidate_sha256": digest(root / "harness/candidates.json"),
                          "baseline_sha": manifest["commits"]["A"], "runtime": manifest["runtime"],
                          "result_source": str(root / "aggregate.json"), "comparison": "HISTORICAL_ONLY"}
    return inputs, sources


def require_feature(feature_sha):
    if len(feature_sha) != 40 or git("rev-parse", "HEAD") != feature_sha:
        raise ValueError("feature SHA must equal the reviewed feature-complete HEAD")
    if git("status", "--porcelain", "--untracked-files=all", "--",
           "src", "experiments/continuous_proof_network", "tests/test_continuous_evaluation.py"):
        raise ValueError("feature source has uncommitted changes")


def freeze(source_root, destination, feature_sha):
    """Invoke only after implementation closure, deterministic tests and source review."""
    from research.run_invocations import real_runtime
    require_feature(feature_sha)
    destination = Path(destination).resolve()
    allowed = Path(source_root).resolve() / "workspaces/continuous_proof_network/evaluation"
    if destination.parent != allowed:
        raise ValueError("evaluation must use a fresh direct child of the local evaluation directory")
    if destination.exists():
        raise ValueError("evaluation destination already exists")
    inputs, sources = original_inputs(source_root)
    runtime = real_runtime()
    if (runtime["model"], runtime["effort"], runtime["timeout_seconds"]) != ("gpt-5.6-sol", "xhigh", 600):
        raise ValueError("required Sol/xhigh/600s runtime is unavailable")
    for item in inputs:
        problem = {k: item[k] for k in ("problem_id", "statement", "context")}
        write_once(destination / "inputs" / item["problem_id"] / "problem.json", problem)
        path = destination / "inputs" / item["problem_id"] / "original_graph.json"
        with path.open("xb") as handle:
            handle.write(Path(item["original_graph_path"]).read_bytes())
    files = {str(p.relative_to(destination)): digest(p) for p in sorted((destination / "inputs").rglob("*.json"))}
    write_once(destination / "manifest.json", {"feature_sha": feature_sha, "created_at": time.time(),
        "harness_sha256": digest(__file__), "source_root": str(Path(source_root).resolve()),
        "source_manifests": sources, "input_hashes": files, "runtime": runtime,
        "order": [i["problem_id"] for i in inputs], "repetitions": 1, "observation_seconds": 1200,
        "window_policy": "External pause; target stays OPEN. At most one 600s in-flight call tail; post-audit separate.",
        "recovery_policy": "Once after first durable complete Worker result, fresh process resumes same run; deadline unchanged.",
        "comparison": "Historical v3 controls; no matched superiority claim",
        "baseline_budgets": {"n3d": [3, 0, 0, 0], "n3e": [24, 6, 12, 12]},
        "controls": [i["problem_id"] for i in inputs if i["control"]]})


def check(root):
    manifest = read(Path(root) / "manifest.json")
    require_feature(manifest["feature_sha"])
    if digest(__file__) != manifest["harness_sha256"]:
        raise ValueError("frozen harness changed")
    for name, expected in manifest["input_hashes"].items():
        if digest(Path(root) / name) != expected:
            raise ValueError("frozen evaluation input changed")
    return manifest


def invocation_metrics(directory):
    rows = []
    for path in sorted(Path(directory).glob("*.json")):
        record = read(path)
        turns = [e["usage"] for e in record.get("events", [])
                 if e.get("type") == "turn.completed" and isinstance(e.get("usage"), dict)]
        usage = {key: sum(t[key] for t in turns if isinstance(t.get(key), (int, float)))
                 for key in ("input_tokens", "output_tokens")
                 if turns and all(isinstance(t.get(key), (int, float)) for t in turns)}
        rows.append({"role": record.get("label"), "usage": usage,
                     "elapsed_seconds": record.get("elapsed_seconds"), "error": record.get("error"),
                     "network_attempts": record.get("network_attempts", [])})

    def total(items):
        known = [r["usage"] for r in items if len(r["usage"]) == 2]
        elapsed = [r["elapsed_seconds"] for r in items if isinstance(r["elapsed_seconds"], (int, float))]
        return {"actual_calls": len(items), "reported_input_output_tokens": sum(sum(u.values()) for u in known) if known else None,
                "unknown_usage_calls": len(items) - len(known), "token_totals_complete": len(known) == len(items),
                "elapsed_seconds": sum(elapsed) if elapsed else None,
                "unknown_duration_calls": len(items) - len(elapsed)}

    return {**total(rows), "by_role": {role: total([r for r in rows if r["role"] == role])
            for role in sorted({r["role"] for r in rows})}, "records": rows}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


class Observation:
    """A cooperative external window, plus one durable process-restart checkpoint."""
    def __init__(self, case, deadline, restart_probe, clock=time.time):
        self.case, self.deadline, self.restart_probe, self.clock = Path(case), deadline, restart_probe, clock

    def __call__(self, event, details):
        self.case.mkdir(parents=True, exist_ok=True)
        with (self.case / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": self.clock(), "event": event, **details}) + "\n")
        if self.clock() >= self.deadline:
            self.expire()
        elif (self.restart_probe and event == "call_completed" and details.get("label") == "continuous_worker"
              and not (self.case / "recovery_checkpoint.json").exists()):
            directory = self.case / "workspace/continuous_run"
            requests = sorted((directory / "calls").glob("*/request.json"))
            result = next((p.parent / "result.json" for p in requests
                           if read(p).get("label") == "continuous_worker" and (p.parent / "result.json").exists()
                           and read(p.parent / "result.json").get("status") == "COMPLETED"), None)
            if result:
                write_once(self.case / "recovery_checkpoint.json", {"time": self.clock(), "event": event,
                           "visit": details.get("visit"), "result": str(result.relative_to(self.case)),
                           "confirmed_hashes": {str(p.relative_to(self.case)): digest(p)
                               for request in requests if (request.parent / "result.json").exists()
                               for p in (request, request.parent / "result.json")}})
                pause_run(self.case / "workspace", "evaluation recovery checkpoint")

    def expire(self):
        if (self.case / "workspace/continuous_run/state.json").exists():
            pause_run(self.case / "workspace", "evaluation observation window")


def audit_facts(case, problem, runtime):
    """Fresh independent post-audit, outside the search window; never alters truth."""
    from research.fact_audit import FactAuditor
    from research.graph import FactGraph
    from research.run_invocations import SolInvoker
    graph = FactGraph(case / "workspace")
    facts = graph.list_facts()
    if not facts:
        return
    backend = SolInvoker(image=runtime["image"], timeout_seconds=600, audit_dir=case / "post_audit/invocations")
    for fact in facts:
        directory = case / "post_audit" / fact.fact_id
        if (directory / "result.json").exists():
            continue
        if (directory / "started.json").exists():
            result = {"fact_id": fact.fact_id, "classification": "AUDIT_ERROR", "reason": "unconfirmed audit; not retried"}
        else:
            write_once(directory / "started.json", {"started_at": time.time(), "fact_id": fact.fact_id})
            try:
                result = FactAuditor(backend).audit(problem=problem["statement"], fact=fact,
                    predecessors=[graph.get_fact(k) for k in fact.predecessors], target_statement=problem["statement"])
            except Exception as error:
                result = {"fact_id": fact.fact_id, "classification": "AUDIT_ERROR", "reason": str(error)}
        write_once(directory / "result.json", result)


def collect_case(case):
    from research.continuous_research import read_status, export_proof
    from research.fact_audit import cascade_invalid
    from research.graph import FactGraph
    case = Path(case)
    workspace = case / "workspace"
    state = read_status(workspace)
    graph = FactGraph(workspace)
    facts = graph.list_facts()
    audits = cascade_invalid(facts, [read(p) for p in sorted((case / "post_audit").glob("*/result.json"))])
    clean = {a["fact_id"] for a in audits if a["classification"] in ("SUBSTANTIVE", "TRIVIAL")
             and all(a.get("checks", {}).get(k) is True for k in
                     ("mathematically_correct", "predecessor_sufficient", "closed_book_clean", "no_target_circularity"))}
    closure, errors = [], []
    if state["target_state"] == "DISCHARGED":
        try:
            closure = [f["fact_id"] for f in export_proof(workspace)["facts"]]
        except (KeyError, ValueError) as error:
            errors.append(str(error))
    directory = workspace / "continuous_run"
    requests = [read(p) for p in sorted((directory / "calls").glob("*/request.json"))]
    scope_counts = Counter(r["scope"] for r in requests)
    events = [json.loads(line) for line in (case / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    checkpoint = read(case / "recovery_checkpoint.json") if (case / "recovery_checkpoint.json").exists() else None
    resume = read(case / "resume.result.json") if (case / "resume.result.json").exists() else None
    recovery = {"checkpoint_created": checkpoint is not None,
        "resume_executed": bool(resume and not resume.get("resume_skipped_window_expired")),
        "confirmed_results_preserved": all((case / p).exists() and digest(case / p) == h
            for p, h in checkpoint["confirmed_hashes"].items()) if checkpoint else None,
        "duplicate_call_scopes": [scope for scope, n in scope_counts.items() if n > 1]}
    attention = [read(p) for p in directory.glob("visits/*/*-attention.json")]
    shared, used = {}, {}
    for p in directory.glob("visits/*/packet.json"):
        packet = read(p)
        for fact in packet.get("accepted_facts", []):
            shared.setdefault(fact["fact_id"], set()).add(packet["study"]["study_id"])
        admission = p.parent / "admission.json"
        if admission.exists() and read(admission).get("fact_id"):
            for key in graph.get_fact(read(admission)["fact_id"]).predecessors:
                used.setdefault(key, set()).add(packet["study"]["study_id"])
    return {"status": state["status"], "target_state": state["target_state"], "pause_reason": state.get("pause_reason"),
        "error": state.get("error"), "solved": bool(closure) and set(closure) <= clean and not errors,
        "closure": closure, "closure_errors": errors, "audit_results": audits,
        "substantive_facts": sum(a["classification"] == "SUBSTANTIVE" and a["fact_id"] in clean for a in audits),
        "invalid_facts": sum(a["classification"] == "INVALID" for a in audits),
        "fact_ids": [f.fact_id for f in facts], "refutation_ids": [p.stem for p in (workspace / "refutations").glob("*.json")],
        "search": invocation_metrics(directory / "invocations"), "post_audit": invocation_metrics(case / "post_audit/invocations"),
        "reservations": len(requests), "unconfirmed_reservations": state["unconfirmed_reservations"],
        "visits_completed": sum(e["event"] == "visit_completed" for e in events), "visit_cursor": state["step"],
        "served_channels": dict(Counter(e.get("channel") for e in events if e["event"] == "visit_completed")),
        "continuation_revisions": {s["study_id"]: s["revision"] for s in state["studies"]},
        "cross_study_fact_exposure": {k: sorted(v) for k, v in shared.items() if len(v) > 1},
        "cross_study_fact_used_lineage": {k: sorted(v) for k, v in used.items() if len(v) > 1},
        "known_true_target_refutation_conflict": state["target_state"] == "REFUTED",
        "recovery_blocker": bool(recovery["duplicate_call_scopes"]) or recovery["confirmed_results_preserved"] is False,
        "max_attention_estimated_tokens": max((m["estimated_tokens"] for m in attention), default=None),
        "attention_method": "ceil(UTF-8 bytes / 4), estimate not tokenizer measurement", "recovery": recovery}


def run_case(root, problem_id, phase):
    """Each invocation is one real OS process; only the planned checkpoint permits resume."""
    from research.continuous_research import start_run, resume_run, read_status, export_proof
    from research.run_invocations import real_runtime
    root = Path(root)
    manifest = check(root)
    if problem_id not in manifest["order"] or phase not in ("start", "resume"):
        raise ValueError("unregistered case or phase")
    case = root / "cases" / problem_id
    result_path = case / (phase + ".result.json")
    if result_path.exists() or (case / "result.json").exists():
        return
    if (case / (phase + ".started.json")).exists():
        raise ValueError("unconfirmed process stage; automatic retry is forbidden")
    if real_runtime() != manifest["runtime"]:
        raise ValueError("frozen runtime changed")
    if phase == "resume" and read(case / "start.result.json")["status"].get("pause_reason") != "evaluation recovery checkpoint":
        raise ValueError("only the planned recovery checkpoint may resume")
    if phase == "start":
        began = time.time()
        write_once(case / "observation.json", {"started_at": began, "deadline": began + manifest["observation_seconds"]})
    window = read(case / "observation.json")
    write_once(case / (phase + ".started.json"), {"time": time.time(), "pid": os.getpid(), "deadline": window["deadline"]})
    observer = Observation(case, window["deadline"], restart_probe=phase == "start")
    timer = Timer(max(0, window["deadline"] - time.time()), observer.expire)
    timer.daemon = True
    timer.start()
    problem = read(root / "inputs" / problem_id / "problem.json")
    expired_before_resume = phase == "resume" and time.time() >= window["deadline"]
    try:
        if expired_before_resume:
            observer.expire()
            status = read_status(case / "workspace")
        else:
            status = (start_run(case / "workspace", **problem, on_event=observer) if phase == "start"
                      else resume_run(case / "workspace", on_event=observer))
    finally:
        timer.cancel()
    write_once(result_path, {"finished_at": time.time(), "pid": os.getpid(), "status": status,
                            "resume_skipped_window_expired": expired_before_resume})
    if phase == "start" and status.get("pause_reason") == "evaluation recovery checkpoint":
        return
    audit_started = time.time()
    audit_facts(case, problem, manifest["runtime"])
    result = collect_case(case)
    result.update(problem_id=problem_id, group=problem_id.split("-")[0], observation=window,
                  search_wall_seconds=audit_started - window["started_at"],
                  post_audit_wall_seconds=time.time() - audit_started,
                  resume_skipped_window_expired=expired_before_resume)
    if result["closure"]:
        write_once(case / "proof.json", export_proof(case / "workspace"))
    write_once(case / "result.json", result)


def run_all(root):
    """Serial stable host. Completed samples and failed processes are never rerun."""
    from research.run_storage import run_lock
    root = Path(root).resolve()
    manifest = check(root)
    env = {**os.environ, "PYTHONPATH": str(CHECKOUT / "src"), "PYTHONUTF8": "1"}
    with run_lock(root / "host_lock"):
        for problem_id in manifest["order"]:
            case = root / "cases" / problem_id
            if (case / "result.json").exists():
                continue
            case.mkdir(parents=True, exist_ok=True)
            for phase in ("start", "resume"):
                if phase == "resume":
                    first = read(case / "start.result.json")["status"]
                    if first.get("pause_reason") != "evaluation recovery checkpoint":
                        break
                if not (case / (phase + ".result.json")).exists():
                    if (case / (phase + ".started.json")).exists():
                        write_once(case / "result.json", {"problem_id": problem_id, "solved": False,
                            "system_error": "host found an unconfirmed process; no automatic retry", "phase": phase})
                        break
                    argv = [sys.executable, "-X", "utf8", "-m", "experiments.continuous_proof_network.evaluate",
                            "run-case", str(root), problem_id, phase]
                    with (case / (phase + ".stdout.log")).open("x", encoding="utf-8") as stdout, \
                            (case / (phase + ".stderr.log")).open("x", encoding="utf-8") as stderr:
                        completed = subprocess.run(argv, cwd=CHECKOUT, env=env, stdout=stdout, stderr=stderr)
                    write_once(case / (phase + ".process.json"), {"argv": argv, "returncode": completed.returncode})
                    if completed.returncode:
                        write_once(case / "result.json", {"problem_id": problem_id, "solved": False,
                            "system_error": "evaluation process failed; evidence retained, not retried", "phase": phase,
                            "returncode": completed.returncode})
                        break
                if (case / "result.json").exists():
                    break
            if not (case / "result.json").exists():
                write_once(case / "result.json", {"problem_id": problem_id, "solved": False,
                    "system_error": "process ended without complete post-audit/result; retained without retry"})
            print(json.dumps({"problem_id": problem_id, "result_exists": (case / "result.json").exists()}), flush=True)
        if not (root / "aggregate.json").exists():
            write_once(root / "aggregate.json", collect(root))


def collect(root):
    root = Path(root)
    manifest = read(root / "manifest.json")
    rows = []
    for problem_id in manifest["order"]:
        case = root / "cases" / problem_id
        row = read(case / "result.json") if (case / "result.json").exists() else {"problem_id": problem_id, "incomplete": True}
        # Failed hosts still expose any real invocation cost; unknown is never zero.
        if "search" not in row:
            row["search"] = invocation_metrics(case / "workspace/continuous_run/invocations")
            row["post_audit"] = invocation_metrics(case / "post_audit/invocations")
        rows.append(row)
    groups = {}
    for group in SOURCES:
        selected = [r for r in rows if r["problem_id"].startswith(group + "-")]
        groups[group] = {"problems": len(selected), "clean_targets": sum(r.get("solved") is True for r in selected),
                         "system_errors": sum("system_error" in r for r in selected),
                         "incomplete": sum(r.get("incomplete", False) for r in selected)}
    controls = [r for r in rows if r["problem_id"] in manifest.get("controls", [])]
    groups["n3d_controls"] = {"problems": len(controls), "clean_targets": sum(r.get("solved") is True for r in controls)}
    structural = [r for r in rows if r["problem_id"].startswith("n3d-") and r not in controls]
    groups["n3d_structural_candidates"] = {"problems": len(structural), "clean_targets": sum(r.get("solved") is True for r in structural)}
    return {"feature_sha": manifest["feature_sha"], "comparison": "HISTORICAL_ONLY", "groups": groups, "runs": rows,
            "historical_sources": manifest["source_manifests"], "no_matched_superiority_claim": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    frozen = sub.add_parser("freeze", help="Only after implementation closure, tests and source review")
    frozen.add_argument("destination", type=Path)
    frozen.add_argument("--source-root", required=True, type=Path)
    frozen.add_argument("--feature-sha", required=True)
    for name in ("run-all", "collect"):
        p = sub.add_parser(name)
        p.add_argument("root", type=Path)
    case = sub.add_parser("run-case")
    case.add_argument("root", type=Path)
    case.add_argument("problem_id")
    case.add_argument("phase", choices=("start", "resume"))
    args = parser.parse_args(argv)
    if args.command == "freeze":
        freeze(args.source_root, args.destination, args.feature_sha)
    elif args.command == "run-all":
        run_all(args.root)
    elif args.command == "run-case":
        run_case(args.root, args.problem_id, args.phase)
    else:
        print(json.dumps(collect(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
