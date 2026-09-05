"""Read-only N2Z evidence supplement; never feeds back into proving."""
import json
from pathlib import Path

from research.graph import FactGraph


def summarize_run(problem_dir, summary, *, initial_attempt_ids):
    root = Path(problem_dir)
    attempts = {"historical": [], "during_run": []}
    initial = set(initial_attempt_ids)
    for path in sorted((root / "attempts").glob("*.json")):
        group = "historical" if path.name in initial else "during_run"
        attempts[group].append((path.name, json.loads(path.read_text(encoding="utf-8"))))
    counts = {}
    for group, records in attempts.items():
        errors = [r for _, r in records if r.get("verdict") == "ERROR"]
        timeouts = sum("TimeoutExpired" in str(r.get("error")) or "timed out" in str(r.get("error")).lower() for r in errors)
        counts[group] = {"ids": [name for name, _ in records], "count": len(records),
                         "failures": sum(r.get("verdict") == "FAIL" for _, r in records),
                         "timeouts": timeouts, "other_errors": len(errors) - timeouts}
    facts = {f.fact_id: f for f in FactGraph(root).list_facts()}
    audits = {a["fact_id"]: a.get("classification") for a in summary.get("fact_audit", [])}

    def closure(fid, seen=None):
        seen = set() if seen is None else seen
        if fid in seen:
            return seen
        seen.add(fid)
        if fid in facts:
            for parent in facts[fid].predecessors:
                closure(parent, seen)
        return seen

    def outcome(fid):
        ids = closure(fid) if fid else set()
        incomplete = sorted(i for i in ids if i not in facts or audits.get(i) not in ("SUBSTANTIVE", "TRIVIAL"))
        return {"fact_id": fid, "resolved": bool(fid), "closure_ids": sorted(ids),
                "unaudited_or_invalid_ids": incomplete, "audited_success": bool(ids) and not incomplete}

    scaffold_path = root / "scaffold.json"
    scaffold = json.loads(scaffold_path.read_text(encoding="utf-8")) if scaffold_path.exists() else {}
    nodes = {n["node_id"]: n for n in scaffold.get("nodes", [])}
    target = nodes.get(scaffold.get("target_node_id"), {})
    refinements = []
    records = [(path, json.loads(path.read_text(encoding="utf-8")))
               for path in sorted((root / "local_refinements").glob("*.json"))]
    applied_by_id = {(r.get("proposal") or {}).get("proposal_id"): r for _, r in records
                     if r.get("applied") is True and r.get("outcome") == "APPLIED"}
    for path, record in records:
        proposal = record.get("proposal") or {}
        context = record.get("context") or {}
        boundary = {f["fact_id"] for f in context.get("verified_boundary", [])}
        children = proposal.get("children", [])
        cited = {fid for n in children for fid in n.get("premise_fact_ids", [])} & boundary
        applied = record.get("applied") is True and record.get("outcome") == "APPLIED"
        operation = context.get("allowed_operation")
        descendants = {n["node_id"] for n in children} if applied and operation == "INSERT_CUT_SET" else set()
        # Follow the actual final scaffold, including replacement children whose
        # dependencies preserve the original Cut's mathematical lineage.
        changed = True
        while changed:
            previous = len(descendants)
            for nid in tuple(descendants):
                node = nodes.get(nid, {})
                replacement = applied_by_id.get(node.get("superseded_by") or node.get("parked_by"))
                if replacement and replacement.get("blocked_node_id") == nid:
                    descendants.update(c["node_id"] for c in replacement["proposal"].get("children", []))
            descendants.update(nid for nid, n in nodes.items() if set(n.get("depends_on", [])) & descendants)
            changed = previous != len(descendants)
        candidates = []
        for nid in sorted(descendants):
            fid = nodes.get(nid, {}).get("resolved_by_fact_id")
            if fid and closure(fid) & cited:
                candidates.append({"node_id": nid, **outcome(fid)})
        blocked_id = record.get("blocked_node_id")
        blocked_goal = (context.get("blocked_node") or {}).get("goal")
        blocked_outcomes = [{"node_id": nid, **outcome(n.get("resolved_by_fact_id"))}
                            for nid, n in nodes.items() if nid == blocked_id or
                            (blocked_goal and n.get("goal") == blocked_goal)]
        refinements.append({"evidence": str(path.relative_to(root)), "operator": operation,
                            "proposal_id": proposal.get("proposal_id"), "blocked_node_id": blocked_id,
                            "applied": applied, "boundary_ids": sorted(boundary),
                            "proposed_boundary_ids": sorted(cited),
                            "cited_boundary_ids": sorted(cited) if applied else [],
                            "citing_child_ids": [n["node_id"] for n in children if set(n.get("premise_fact_ids", [])) & cited],
                            "descendants": candidates,
                            "audited_descendant_fact_ids": sorted({c["fact_id"] for c in candidates if c["audited_success"]}),
                            "blocked_goal_outcomes": blocked_outcomes})
    exposure = []
    for path in sorted((root / "two_stage").glob("episode-*.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        patch = episode.get("patch") or {}
        prompt = patch.get("builder_prompt") or ""
        exposed = "VERIFIED LOCAL BOUNDARY INPUTS" in prompt
        boundary = (episode.get("gate_packet") or {}).get("verified_boundary", [])
        exposure.append({"evidence": str(path.relative_to(root)), "episode": episode.get("episode"),
                         "blocked_node_id": episode.get("blocked_node_id"),
                         "operator": (episode.get("sketch") or {}).get("operator"),
                         "builder_completed": bool(patch), "disclosure_present": exposed if patch else None,
                         "boundary_ids": sorted(f["fact_id"] for f in boundary) if exposed else []})
    return {"attempts": counts, "exposure": exposure, "refinements": refinements,
            "target": outcome(target.get("resolved_by_fact_id")),
            "audit": {"missing_ids": sorted(set(facts) - set(audits)),
                      "error_ids": sorted(i for i, c in audits.items() if c == "AUDIT_ERROR"),
                      "invalid_ids": sorted(i for i, c in audits.items() if c == "INVALID")}}
