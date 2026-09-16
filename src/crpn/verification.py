"""Mathematical verifier seam; all execution is delegated to DANUS."""
class VerifierBackend:
    """Replaceable mathematical authority seam, below CRPN policy."""
    def __init__(self, runtime):
        self.runtime = runtime

    def verify(self, key, candidate, predecessors):
        from .contracts import VERIFIER, VERIFY_SCHEMA
        packet = {"candidate": {"statement": candidate["statement"], "proof": candidate["proof"]},
                  "accepted_predecessors": predecessors,
                  "verification_purpose": candidate.get("provenance", {}).get("purpose", "local proof")}
        result = self.runtime.call("verifier", "verifier", key, VERIFIER, packet, VERIFY_SCHEMA)
        if result["status"] != "COMPLETED":
            return {"verdict": result["status"].lower(), "evidence": result["evidence"]}
        output = result["output"]
        if output.get("verdict") not in ("correct", "wrong", "inconclusive"):
            return {"verdict": "inconclusive", "raw": output, "evidence": result["evidence"]}
        return {**output, "evidence": result["evidence"]}
