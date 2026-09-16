"""Recoverable verifier-gated submission seam (Noespire substrate patch).

The backend judges mathematics. This module alone writes accepted Facts.
Backend.verify(key, candidate, predecessors) must use the durable round service;
unconfirmed computation is INTERRUPTED, never repeated speculatively.
"""
from hashlib import sha256
import json
from pathlib import Path
from danus.core import FactGraph, GlobalMemory
from danus.core.schema import compute_fact_id
from danus.core.durable_io import immutable_json, read_json, locked


class SubmissionGate:
    def __init__(self, root, backend):
        self.root, self.backend = Path(root), backend
        self.graph, self.memory = FactGraph(root), GlobalMemory(root)

    def submit(self, key, *, problem_id, author, statement, proof,
               predecessors=(), glossary_introduces=None, provenance=None):
        identity = sha256(key.encode()).hexdigest()
        directory = self.root / "submissions" / identity
        with locked(directory / ".lock"):
            request = {"problem_id": problem_id, "author": author,
                       "statement": statement, "proof": proof,
                       "predecessors": sorted(set(predecessors)),
                       "glossary_introduces": glossary_introduces or {},
                       "provenance": provenance or {}}
            immutable_json(directory / "request.json", request)
            prior = []
            for fid in request["predecessors"]:
                closure = self.graph.supporting_closure(fid)
                if any(f.problem_id != problem_id for f in closure):
                    raise ValueError("cross_problem_predecessor")
                fact = self.graph.get(fid)
                prior.append({"fact_id": fid, "statement": fact.statement})
            receipt = directory / "result.json"
            if receipt.exists():
                result = read_json(receipt)
                verification = read_json(directory / "verification.json")
                expected = compute_fact_id(problem_id=problem_id, statement=statement,
                    proof=proof, predecessors=request["predecessors"],
                    glossary_introduces=request["glossary_introduces"])
                if (result.get("verification") != verification or
                    result.get("accepted") != (verification.get("verdict") == "correct") or
                    result.get("verdict") != verification.get("verdict") or
                    result.get("fact_id") != (expected if result["accepted"] else None)):
                    raise ValueError("submission receipt binding corruption")
                if result.get("fact_id"):
                    self.graph.supporting_closure(result["fact_id"])
                return result
            verdict_path = directory / "verification.json"
            if verdict_path.exists():
                verdict = read_json(verdict_path)
            else:
                verdict = self.backend.verify("submission-" + identity, request, prior)
                if not isinstance(verdict, dict) or verdict.get("verdict") not in (
                        "correct", "wrong", "inconclusive", "timeout", "interrupted", "error"):
                    verdict = {"verdict": "inconclusive", "raw": verdict}
                immutable_json(verdict_path, verdict)
            accepted = verdict["verdict"] == "correct"
            fid = None
            if accepted:
                fid = self.graph.add(problem_id=problem_id, author=author,
                                     statement=statement, proof=proof,
                                     predecessors=request["predecessors"],
                                     glossary_introduces=request["glossary_introduces"])
            result = {"accepted": accepted, "fact_id": fid,
                      "verdict": verdict["verdict"], "verification": verdict,
                      "evidence": str(directory)}
            # A receipt is authoritative; memory is only an append-only awareness trace.
            immutable_json(receipt, result)
            try:
                self.memory.append("verification", statement, json.dumps(verdict), author,
                                   verifiable=False, fact_id=fid, verdict=verdict["verdict"],
                                   links={"submission": identity, "predecessors": request["predecessors"]})
            except (ValueError, OSError):
                # Receipt remains the durable trace; awareness can be rebuilt from it.
                pass
            return result
