"""One-time import on an isolated copy; legacy source files are never mutated."""
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
import shutil
import json
from copy import deepcopy

from .proof_patch import KINDS, structural_schema

from .proof_graph import ProofGraph, ProofObligation, ProofRoute
from .run_storage import read_json, write_json


def _shape(nodes):
    return {key: {"goal": n["goal"], "depends_on": sorted(n["depends_on"]),
                  "premise_fact_ids": sorted(n["premise_fact_ids"]),
                  "parked_by": n.get("parked_by"), "superseded_by": n.get("superseded_by")}
            for key, n in nodes.items()}


def _reconstruct_history(source, final_nodes, problem_id):
    """Reverse exact recorded post-images, then replay mathematical routes forward.

    Facts may have been resolved since the patch; no structural change is guessed.
    A manual backtrack or unrecorded rename fails this comparison.
    """
    from .local_refinement import SplitChildSpec, _proposal_id
    records = []
    for path in (source / "local_refinements").glob("*.json"):
        record = read_json(path)
        if record.get("applied") is not True:
            continue
        operator = record["context"]["allowed_operation"]
        proposal = record["proposal"]
        prefix = {"SPLIT": "split-", "INSERT_CUT_SET": "cut-", "ADD_ALTERNATIVE_ROUTE": "alt-"}[operator]
        children = tuple(SplitChildSpec(**c) for c in proposal["children"])
        audit = json.loads(record["auditor_raw"])
        checks = structural_schema(operator)["properties"]["checks"]["required"]
        if (record["problem_id"] != problem_id or record["outcome"] != "APPLIED"
                or record.get("mechanical_errors") or record["auditor_verdict"] != "PASS"
                or audit.get("verdict") != "PASS" or any(audit.get("checks", {}).get(k) is not True for k in checks)
                or proposal["proposal_id"] != _proposal_id(children, prefix)):
            raise ValueError("legacy refinement lacks valid structural provenance")
        record["source_path"] = path.relative_to(source).as_posix()
        record["source_sha256"] = sha256(path.read_bytes()).hexdigest()
        records.append(record)
    working, history = deepcopy(final_nodes), []
    while records:
        matches = [r for r in records if _shape({n["node_id"]: n for n in r["post_patch_nodes"]}) == _shape(working)]
        if len(matches) != 1:
            raise ValueError("legacy post-images do not uniquely reconstruct the final graph")
        record = matches[0]
        records.remove(record)
        context, proposal = record["context"], record["proposal"]
        blocked = context["blocked_node"]
        if blocked["node_id"] != proposal["blocked_node_id"] or record["blocked_node_id"] != blocked["node_id"]:
            raise ValueError("legacy refinement target identity mismatch")
        child_ids = {c["node_id"] for c in proposal["children"]}
        before = {n["node_id"] for n in context["local_nodes"]} | {blocked["node_id"]}
        wrappers = [k for k, n in working.items() if k not in child_ids | before and n["goal"] == blocked["goal"]]
        if context["allowed_operation"] == "SPLIT":
            if wrappers:
                raise ValueError("unexpected duplicate target in a legacy SPLIT")
        elif len(wrappers) != 1:
            raise ValueError("legacy cut/alternative wrapper lacks unique evidence")
        record["wrapper"] = wrappers[0] if wrappers else None
        for key in child_ids | set(wrappers):
            working.pop(key)
        working[blocked["node_id"]] = blocked
        for node in context["local_nodes"]:
            working[node["node_id"]] = node
        _check_legacy_transition(source, record, working)
        history.append(record)
    if any(n.get("parked_by") or n.get("superseded_by") or "__" in k for k, n in working.items()):
        raise ValueError("legacy refinements require complete provenance evidence")
    return working, list(reversed(history))


def _check_legacy_transition(source, record, before):
    """Replay the original mechanical operator in scratch storage, never the source."""
    from tempfile import TemporaryDirectory
    from .scaffold import ProofScaffold
    from .local_refinement import (SplitChildSpec, SplitProposal, CutSetProposal, AlternativeRouteProposal,
                                   apply_split, apply_cut_set, apply_alternative_route)
    proposal_type, apply = {"SPLIT": (SplitProposal, apply_split),
        "INSERT_CUT_SET": (CutSetProposal, apply_cut_set),
        "ADD_ALTERNATIVE_ROUTE": (AlternativeRouteProposal, apply_alternative_route)}[record["context"]["allowed_operation"]]
    proposal = proposal_type(**{**record["proposal"],
        "children": tuple(SplitChildSpec(**c) for c in record["proposal"]["children"])})
    # TemporaryDirectory owns only its generated child of the isolated import.
    with TemporaryDirectory(dir=source.parent) as scratch:
        path = Path(scratch) / "scaffold.json"
        write_json(path, {**read_json(source / "scaffold.json"), "nodes": list(before.values())})
        apply(ProofScaffold(path), proposal)
        expected = {n["node_id"]: n for n in read_json(path)["nodes"]}
    if _shape(expected) != _shape({n["node_id"]: n for n in record["post_patch_nodes"]}):
        raise ValueError("legacy post-images do not match the recorded operator transition")


class LegacyScaffoldImporter:
    def __init__(self, source):
        self.source = Path(source).resolve()

    def import_to(self, destination):
        destination = Path(destination).resolve()
        if (destination == self.source or destination in self.source.parents or self.source in destination.parents
                or destination.exists()):
            raise ValueError("legacy import requires a fresh isolated destination")
        paths = list(self.source.rglob("*"))
        if any(p.is_symlink() or p.is_junction() for p in paths):
            raise ValueError("legacy source must not contain external filesystem links")
        fingerprints = {p.relative_to(self.source).as_posix(): sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
        source = destination / "legacy_source"
        shutil.copytree(self.source, source)
        copied = {p.relative_to(source).as_posix(): sha256(p.read_bytes()).hexdigest()
                  for p in source.rglob("*") if p.is_file()}
        if copied != fingerprints:
            raise ValueError("legacy copy differs from frozen source fingerprints")
        scaffold = read_json(source / "scaffold.json")
        problem_id = scaffold["problem_id"]
        nodes = {n["node_id"]: n for n in scaffold["nodes"]}
        if len(nodes) != len(scaffold["nodes"]):
            raise ValueError("duplicate legacy node IDs")
        initial_nodes, history = _reconstruct_history(source, nodes, problem_id)
        registry = read_json(source / "obligations.json").get("obligations", []) if (source / "obligations.json").exists() else []
        if any(o["status"] == "RUNNING" for o in registry):
            raise ValueError("legacy workspace has an unconfirmed RUNNING obligation")
        for name in ("facts", "_revoked"):
            if (source / name).exists():
                shutil.copytree(source / name, destination / name)
        if (source / "revocation_log.jsonl").exists():
            shutil.copy2(source / "revocation_log.jsonl", destination / "revocation_log.jsonl")
        obligations = {key: ProofObligation.create(problem_id, "", node["goal"]) for key, node in initial_nodes.items()}
        routes = {key: ProofRoute.create(obligations[key].obligation_id,
            [obligations[k].obligation_id for k in node["depends_on"]], node["premise_fact_ids"]) for key, node in initial_nodes.items()}
        closed, route_evidence = set(), {}
        for record in history:
            proposal = record["proposal"]
            blocked = proposal["blocked_node_id"]
            closed.add(routes[blocked].route_id)
            for child in proposal["children"]:
                obligations[child["node_id"]] = ProofObligation.create(problem_id, "", child["goal"])
            for child in proposal["children"]:
                routes[child["node_id"]] = ProofRoute.create(obligations[child["node_id"]].obligation_id,
                    [obligations[k].obligation_id for k in child["depends_on"]], child["premise_fact_ids"],
                    origin_patch_id="legacy:" + record["source_path"])
            route = ProofRoute.create(obligations[blocked].obligation_id,
                [obligations[c["node_id"]].obligation_id for c in proposal["children"]],
                record["context"]["blocked_node"]["premise_fact_ids"],
                kind=KINDS[record["context"]["allowed_operation"]], origin_patch_id="legacy:" + record["source_path"])
            route_key = record.get("wrapper") or "imported-route:" + proposal["proposal_id"]
            routes[route_key] = route
            route_evidence[route.route_id] = dict(path=record["source_path"], sha256=record["source_sha256"],
                                                target_obligation_id=obligations[blocked].obligation_id)
            if record.get("wrapper"):
                obligations[record["wrapper"]] = obligations[blocked]
        if set(nodes) - set(obligations):
            raise ValueError("legacy nodes have no proven import provenance")
        if any(obligations[k].goal != ProofObligation.create(problem_id, "", n["goal"]).goal for k, n in nodes.items()):
            raise ValueError("legacy final goal differs from refinement evidence")
        resolved = {}
        for key, node in nodes.items():
            if node["resolved_by_fact_id"]:
                # Only already-proved historical targets retain the exact old
                # direct lineage. New/open refinement routes still AND all claims.
                original_route = routes[key]
                historical_route = ProofRoute.create(obligations[key].obligation_id,
                    [obligations[k].obligation_id for k in node["depends_on"]], node["premise_fact_ids"],
                    kind=original_route.kind, origin_patch_id="legacy:scaffold.json")
                if historical_route.route_id != original_route.route_id:
                    routes["canonical:" + original_route.route_id] = original_route
                    routes[key] = historical_route
                item = replace(obligations[key], truth_state="DISCHARGED",
                    resolved_fact_id=node["resolved_by_fact_id"], resolved_route_id=routes[key].route_id)
                if item.obligation_id in resolved and resolved[item.obligation_id] != item:
                    raise ValueError("conflicting legacy resolutions of one mathematical obligation")
                resolved[item.obligation_id] = item
        obligations = {key: resolved.get(o.obligation_id, o) for key, o in obligations.items()}
        failed = {}
        for path in sorted((source / "attempts").glob("attempt-*.json")):
            attempt = read_json(path)
            key = attempt["attempt_id"]
            prefix = f"scaffold:{problem_id}:"
            if key != path.stem or not attempt["obligation_id"].startswith(prefix):
                raise ValueError("legacy attempt identity mismatch")
            alias = attempt["obligation_id"][len(prefix):]
            if alias not in obligations or alias not in routes:
                raise ValueError("legacy attempt references an unknown route")
            route = routes[alias]
            outcome = {"FAIL": "PROOF_REJECTED", "PASS": "FACT_ADMITTED", "ERROR": "ERROR"}.get(attempt["verdict"])
            if outcome is None:
                raise ValueError("unconfirmed legacy attempt outcome")
            typed = dict(attempt_id=key, obligation_id=obligations[alias].obligation_id, route_id=route.route_id,
                         outcome=outcome, candidate=attempt.get("candidate_artifact"),
                         verification=attempt.get("verifier_artifact"), legacy_path="legacy_source/attempts/" + path.name,
                         reason=(attempt.get("verifier_artifact") or {}).get("reason") or attempt.get("error") or outcome)
            if outcome == "FACT_ADMITTED":
                typed["fact_id"] = obligations[alias].resolved_fact_id
                if not typed["fact_id"] or attempt["verifier_artifact"].get("accepted") is not True:
                    raise ValueError("legacy PASS lacks verifier-admitted Fact resolution")
            if outcome == "PROOF_REJECTED":
                failed.setdefault(route.route_id, []).append(key)
            write_json(destination / "attempts" / path.name, typed)
        for key, route in tuple(routes.items()):
            evidence = failed.get(route.route_id, [])
            if route.route_id in closed or (len(evidence) >= 3 and obligations.get(key, None)
                                            and obligations[key].truth_state == "OPEN"):
                if not evidence:
                    raise ValueError("legacy parked/superseded route lacks recorded failure evidence")
                routes[key] = replace(route, lifecycle="EXHAUSTED", exhaustion_attempt_ids=tuple(evidence[-3:]),
                                      exhaustion_reason="Recorded legacy bounded failures; original evidence retained")
        data = dict(schema_version=3, problem_id=problem_id,
                    target_obligation_id=obligations[scaffold["target_node_id"]].obligation_id,
                    obligations={o.obligation_id: asdict(o) for o in obligations.values()},
                    routes={r.route_id: asdict(r) for r in routes.values()}, applied_patches={})
        ProofGraph._validate(data)
        ProofGraph._check_evidence(destination, data)
        manifest = dict(source=str(self.source), source_files=fingerprints,
                        obligation_ids={k: o.obligation_id for k, o in obligations.items()},
                        route_ids={k: r.route_id for k, r in routes.items()}, route_evidence=route_evidence)
        write_json(destination / "legacy_import.json", manifest)
        write_json(destination / "proof_graph.json", data)
        return manifest


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="fresh isolated workspace")
    args = parser.parse_args(argv)
    manifest = LegacyScaffoldImporter(args.source).import_to(args.destination)
    print(json.dumps(dict(workspace=str(args.destination.resolve()),
                          obligations=len(set(manifest["obligation_ids"].values())),
                          routes=len(set(manifest["route_ids"].values())))))


if __name__ == "__main__":
    main()
