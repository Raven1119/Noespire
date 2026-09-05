"""N2L closed-book verifier packet suite (§10) — frozen before any real run.

CB-N1..CB-N4 MUST be rejected; CB-A1..CB-A3 MUST be accepted. CB-X1 is a
borderline diagnostic (recorded, not asserted). Packet texts for N1/N2/A1/A2
are loaded verbatim from existing experiment evidence; N3/N4/A3 are
hand-written here. No packet is tuned against the live verifier.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

ERDOS67_PROBLEM = (
    "Let f : N -> {-1, +1}. Prove that for every real number C > 0, there exist "
    "positive integers d and m such that |sum_{k=1}^m f(kd)| > C."
)
CONTROL_A_PROBLEM = (
    "There exist irrational numbers a and b such that a^b is rational."
)
ODD_SUM_PROBLEM = (
    "For every positive integer n, the sum of the first n odd positive integers equals n^2."
)


def load_fact_md(path: Path) -> Tuple[str, str]:
    """Parse a FactGraph markdown artifact into (statement, proof)."""
    text = path.read_text(encoding="utf-8")
    statement = text.split("# Statement", 1)[1].split("# Proof", 1)[0].strip()
    proof = text.split("# Proof", 1)[1].strip()
    return statement, proof


def _attempt_candidate(path: Path) -> Tuple[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate = payload["candidate_artifact"]
    return candidate["statement"], candidate["proof"]


def build_packets() -> List[dict]:
    n1_statement, n1_proof = load_fact_md(
        REPO_ROOT
        / "experiments"
        / "n2c_alternative_route"
        / "runs"
        / "erdos67"
        / "evidence"
        / "facts"
        / "85aca512e39e0cb1.md"
    )
    n2_statement, n2_proof = _attempt_candidate(
        REPO_ROOT
        / "workspaces"
        / "let-f-n-1-1-prove-that-for-every-real-nu-ba4576"
        / "attempts"
        / "attempt-000001.json"
    )
    a1_statement, a1_proof = load_fact_md(
        REPO_ROOT
        / "experiments"
        / "danus_proposition_core_validation"
        / "runs"
        / "case_b_odd_sum"
        / "evidence_run1"
        / "facts"
        / "88212a9a3d199823.md"
    )
    a2_statement, a2_proof = load_fact_md(
        REPO_ROOT
        / "experiments"
        / "n2c_alternative_route"
        / "runs"
        / "control_a"
        / "evidence"
        / "facts"
        / "26cdfd4deb5ec32e.md"
    )
    x1_statement, x1_proof = load_fact_md(
        REPO_ROOT
        / "experiments"
        / "n2c_alternative_route"
        / "runs"
        / "control_a"
        / "evidence"
        / "facts"
        / "d4ca549ca758d3d1.md"
    )

    predecessor_statement = "For every positive integer n, the sum 1 + 2 + ... + n equals n(n+1)/2."
    predecessor_proof = (
        "By induction on n. Base n = 1: 1 = 1*2/2. Step: assume the claim for n; "
        "then 1 + ... + n + (n+1) = n(n+1)/2 + (n+1) = (n+1)(n+2)/2."
    )

    return [
        {
            "packet_id": "CB-N1",
            "expect": "REJECT",
            "assert": True,
            "problem": ERDOS67_PROBLEM,
            "statement": n1_statement,
            "proof": n1_proof,
            "predecessors": [],
            "note": "N2C false-PASS: cites Tao Thm 1.1 (vector-valued EDP) with arXiv URL.",
        },
        {
            "packet_id": "CB-N2",
            "expect": "REJECT",
            "assert": True,
            "problem": ERDOS67_PROBLEM,
            "statement": n2_statement,
            "proof": n2_proof,
            "predecessors": [],
            "note": "Frozen baseline round 1: final step invokes the EDP itself.",
        },
        {
            "packet_id": "CB-N3",
            "expect": "REJECT",
            "assert": True,
            "problem": ERDOS67_PROBLEM,
            "statement": (
                "For every positive integer K there exists a positive integer M such that "
                "for every function h : {1, ..., M} -> {-1, +1} there exist positive integers "
                "d and m with md <= M and |h(d) + h(2d) + ... + h(md)| > K."
            ),
            "proof": (
                "This is the finite compactness counterpart of the classical chromatic drift "
                "principle for the positive integers: every two-colouring of N admits a "
                "homogeneous arithmetic progression of arbitrarily large signed drift. Applying "
                "that principle with threshold K and extracting a uniform finite witness M via "
                "the standard tree/compactness argument yields the claim."
            ),
            "predecessors": [],
            "note": "Renamed target-equivalent; no 'EDP'/'discrepancy' string; key step rests "
            "only on an unprovided target-equivalent principle.",
        },
        {
            "packet_id": "CB-N4",
            "expect": "REJECT",
            "assert": True,
            "problem": "Boundedness of a standard sequence.",
            "statement": "The sequence a_n = (1 + 1/n)^n is bounded above by 3.",
            "proof": (
                "By the monotone convergence theorem, the increasing sequence (1 + 1/n)^n "
                "converges, and every convergent real sequence is bounded; the known limit "
                "e < 3 gives the bound."
            ),
            "predecessors": [],
            "note": "Ordinary named-theorem citation (MCT), not among predecessors, not proved inline.",
        },
        {
            "packet_id": "CB-A1",
            "expect": "ACCEPT",
            "assert": True,
            "problem": ODD_SUM_PROBLEM,
            "statement": a1_statement,
            "proof": a1_proof,
            "predecessors": [],
            "note": "Self-contained induction step (frozen validation evidence).",
        },
        {
            "packet_id": "CB-A2",
            "expect": "ACCEPT",
            "assert": True,
            "problem": CONTROL_A_PROBLEM,
            "statement": a2_statement,
            "proof": a2_proof,
            "predecessors": [],
            "note": "Self-contained excluded-middle case split (N2C control A evidence).",
        },
        {
            "packet_id": "CB-A3",
            "expect": "ACCEPT",
            "assert": True,
            "problem": ODD_SUM_PROBLEM,
            "statement": "For every positive integer n, 1 + 2 + ... + n <= n^2.",
            "proof": (
                "By the accepted predecessor fact, the sum equals n(n+1)/2. For n >= 1 we have "
                "n+1 <= 2n, hence n(n+1)/2 <= n(2n)/2 = n^2."
            ),
            "predecessors": [
                {"statement": predecessor_statement, "proof": predecessor_proof}
            ],
            "note": "Predecessor-grounded: the one external step is a supplied accepted Fact.",
        },
        {
            "packet_id": "CB-X1",
            "expect": None,
            "assert": False,
            "problem": CONTROL_A_PROBLEM,
            "statement": x1_statement,
            "proof": x1_proof,
            "predecessors": [],
            "note": "Borderline diagnostic: applies the real-exponent law (x^r)^s = x^(rs) "
            "naming it but not proving it. Recorded, not asserted.",
        },
    ]
