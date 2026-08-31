// ---------------------------------------------------------------------------
// THROWAWAY PROTOTYPE — mock data only. No backend calls, no persistence.
// Question answered: how should the Problem Workspace layout divide
// Proof / Attempts content across its three states (SOLVED / OPEN / RUNNING)?
//
// The types below mirror the real backend schemas exactly:
//   ProblemSpec      src/research/problem.py  (problem_id, statement, premise_fact_ids)
//   ProofObligation  src/research/obligation.py
//   Fact             src/research/fact.py
//   attempt evidence src/research/problem.py:_start_attempt/_update_attempt
// Only WorkspaceModel (the ADR-0005 read-model aggregate) is UI-only.
//
// In-text Fact references use prototype markup [[fact:<fact_id>|<label>]] so
// proof text can carry clickable mathematical references ("by Lemma 1")
// without ever showing raw hex ids (CONTEXT.md: Proof Document).
// ---------------------------------------------------------------------------

export type ObligationStatus = 'OPEN' | 'RUNNING' | 'DISCHARGED' | 'REJECTED'

export interface ProblemSpec {
  problem_id: string
  statement: string
  premise_fact_ids: string[]
}

export interface ProofObligation {
  obligation_id: string
  premises: string[]
  goal: string
  route_id: string
  status: ObligationStatus
  resolved_by_fact_id: string | null
}

export interface Fact {
  fact_id: string
  problem_id: string
  author: string
  statement: string
  proof: string
  predecessors: string[]
}

export interface CandidateArtifact {
  statement: string
  proof: string
  predecessors: string[]
}

export interface VerifierArtifact {
  accepted: boolean
  reason: string
}

export type AttemptVerdict = 'RUNNING' | 'PASS' | 'FAIL' | 'ERROR'

export interface AttemptEvidence {
  attempt_id: string
  problem_id: string
  obligation_id: string
  candidate_artifact: CandidateArtifact | null
  verifier_artifact: VerifierArtifact | null
  verdict: AttemptVerdict
  error: string | null
  /**
   * PROTOTYPE-ONLY read-model field — NOT part of the backend attempt schema.
   * The persisted evidence cannot distinguish failure origin: the contract
   * guard's synthetic VerificationResult and a fresh verifier's rejection both
   * land as verifier_artifact.accepted=false
   * (src/research/obligation_execution.py:93-106, problem.py:134-141).
   */
  failureSource?: 'contract_guard' | 'fresh_verifier' | 'runtime'
}

/** UI-only aggregate — the ADR-0005 "workspace read model", not a backend object. */
export interface WorkspaceModel {
  spec: ProblemSpec
  obligation: ProofObligation
  /** Verified Facts belonging to this problem (empty while OPEN/RUNNING). */
  facts: Fact[]
  /** Topo-ordered supporting closure of the target Fact (empty unless SOLVED). */
  closure_fact_ids: string[]
  /** Oldest → newest, mirroring attempt-NNNNNN file numbering. */
  attempts: AttemptEvidence[]
  /** Lineage: the problem this one was revised & forked from (ADR-0001). */
  derived_from?: string
  /** UI-only display string; the backend records no timestamps. */
  last_activity: string
}

// ---------------------------------------------------------------------------
// Problem 1 — SOLVED. Sum of the first n odd numbers, 3-Fact closure chain:
// algebra (square differences) → lemma (k-th odd number) → target (induction).
// ---------------------------------------------------------------------------

const F_ALG = '3f9a1c7e52b84d06'
const F_LEMMA = '8c04d2af69e1b735'
const F_TARGET = 'd17b6e930a4f28c5'

const P1_STATEMENT =
  'For every positive integer $n$, the sum of the first $n$ odd numbers equals $n^2$.'

const p1: WorkspaceModel = {
  // premise_fact_ids / root premises must equal the target Fact's
  // predecessors: execute_obligation contract-fails any candidate whose
  // predecessor set differs from the obligation premises
  // (obligation_execution.py:60-63). F_LEMMA pre-exists as an accepted Fact
  // of this same problem, as the backend's same-problem premise rule requires.
  spec: { problem_id: 'sum-first-n-odd', statement: P1_STATEMENT, premise_fact_ids: [F_LEMMA] },
  obligation: {
    obligation_id: 'root:sum-first-n-odd',
    premises: [F_LEMMA],
    goal: P1_STATEMENT,
    route_id: 'root',
    status: 'DISCHARGED',
    resolved_by_fact_id: F_TARGET,
  },
  facts: [
    {
      fact_id: F_ALG,
      problem_id: 'sum-first-n-odd',
      author: 'noespire-worker',
      statement: 'For every integer $k \\geq 1$, $k^2 - (k-1)^2 = 2k - 1$.',
      proof:
        'Expand the square: $k^2 - (k-1)^2 = k^2 - (k^2 - 2k + 1) = 2k - 1$.',
      predecessors: [],
    },
    {
      fact_id: F_LEMMA,
      problem_id: 'sum-first-n-odd',
      author: 'noespire-worker',
      statement: 'For every integer $k \\geq 1$, the $k$-th odd number equals $2k - 1$.',
      proof:
        'The odd numbers in increasing order form the arithmetic progression $1, 3, 5, \\ldots$ with first term $1$ and common difference $2$, so the $k$-th term is $1 + 2(k-1) = 2k - 1$. Equivalently, by [[fact:' +
        F_ALG +
        '|the square-difference identity]], the gap between consecutive squares is $k^2 - (k-1)^2 = 2k - 1$, so the odd numbers are exactly the successive gaps of the squares.',
      predecessors: [F_ALG],
    },
    {
      fact_id: F_TARGET,
      problem_id: 'sum-first-n-odd',
      author: 'noespire-worker',
      statement: P1_STATEMENT,
      proof:
        'We induct on $n$.\n\nBase case. For $n = 1$ the sum is $1 = 1^2$.\n\nInductive step. Assume the claim for $n$: $\\sum_{k=1}^{n}(2k-1) = n^2$. The $(n+1)$-st odd number is $2(n+1) - 1 = 2n + 1$ by [[fact:' +
        F_LEMMA +
        '|Lemma 1]], so\n\n$$\\sum_{k=1}^{n+1}(2k-1) \\;=\\; \\sum_{k=1}^{n}(2k-1) + (2n+1) \\;=\\; n^2 + 2n + 1 \\;=\\; (n+1)^2,$$\n\nwhich completes the induction.',
      predecessors: [F_LEMMA],
    },
  ],
  closure_fact_ids: [F_ALG, F_LEMMA, F_TARGET],
  attempts: [
    {
      attempt_id: 'attempt-000012',
      problem_id: 'sum-first-n-odd',
      obligation_id: 'root:sum-first-n-odd',
      candidate_artifact: {
        statement: P1_STATEMENT,
        proof: 'Induct on $n$; base $1 = 1^2$; step uses that the $(n+1)$-st odd number is $2n+1$.',
        predecessors: [F_LEMMA],
      },
      verifier_artifact: {
        accepted: true,
        reason: 'The induction is complete and correctly justified; the base case and the use of the predecessor lemma check out.',
      },
      verdict: 'PASS',
      error: null,
    },
  ],
  last_activity: '3 days ago',
}

// ---------------------------------------------------------------------------
// Problem 2 — OPEN, latest attempt is a verification rejection.
// ---------------------------------------------------------------------------

const P2_STATEMENT = 'Every even perfect number is triangular.'

const p2: WorkspaceModel = {
  spec: { problem_id: 'even-perfect-triangular', statement: P2_STATEMENT, premise_fact_ids: [] },
  obligation: {
    obligation_id: 'root:even-perfect-triangular',
    premises: [],
    goal: P2_STATEMENT,
    route_id: 'root',
    status: 'OPEN',
    resolved_by_fact_id: null,
  },
  facts: [],
  closure_fact_ids: [],
  attempts: [
    {
      attempt_id: 'attempt-000038',
      problem_id: 'even-perfect-triangular',
      obligation_id: 'root:even-perfect-triangular',
      candidate_artifact: {
        statement: P2_STATEMENT,
        proof:
          'Let $n$ be an even perfect number and write $n = m(m+1)/2$ for a suitable $m$. Since $n$ is even, $m$ is even, say $m = 2t$. Then $n = t(2t+1)$, and because $\\sigma(n) = 2n$ the divisors of $n$ pair off evenly, forcing $2t+1$ prime and $n$ triangular.',
        predecessors: [],
      },
      verifier_artifact: {
        accepted: false,
        reason:
          'The parity argument conflates "$m(m+1)/2$ is even" with "$m$ is even": for $m \\equiv 3 \\pmod 4$ the product $m(m+1)/2$ is even while $m$ is odd, so the case split is wrong and the claimed divisor pairing does not follow.',
      },
      verdict: 'FAIL',
      error: null,
      failureSource: 'fresh_verifier',
    },
    {
      attempt_id: 'attempt-000041',
      problem_id: 'even-perfect-triangular',
      obligation_id: 'root:even-perfect-triangular',
      candidate_artifact: {
        statement: P2_STATEMENT,
        proof:
          'By the Euclid–Euler theorem, every even perfect number has the form $n = 2^{p-1}(2^p - 1)$ where $2^p - 1$ is a Mersenne prime. Setting $m = 2^p - 1$, the Euclid–Euler factor is triangular: $2^{p-1}(2^p - 1)$ is exactly $T_{2^p - 1}$, the $m$-th triangular number. Hence every even perfect number is triangular.',
        predecessors: [],
      },
      verifier_artifact: {
        accepted: false,
        reason:
          'Gap in the reduction: after writing $n = 2^{p-1}(2^p-1)$, the candidate asserts without proof that this factor satisfies the triangular equation $n = m(m+1)/2$ with $m = 2^p - 1$ — the line "is exactly $T_{2^p-1}$" is stated, never derived from $T_m = 1 + 2 + \\cdots + m$. The Euclid–Euler theorem itself is also invoked as "classical" without proof and is not available as a premise Fact.',
      },
      verdict: 'FAIL',
      error: null,
      failureSource: 'fresh_verifier',
    },
  ],
  last_activity: '5 hours ago',
}

// ---------------------------------------------------------------------------
// Problem 3 — OPEN, contract failure (strengthened statement), forked from P2.
// ---------------------------------------------------------------------------

const P3_STATEMENT =
  'Every even perfect number $n = 2^{p-1}(2^p - 1)$, with $2^p - 1$ prime, equals the triangular number $T_{2^p - 1}$.'

const p3: WorkspaceModel = {
  spec: {
    problem_id: 'even-perfect-triangular-mersenne',
    statement: P3_STATEMENT,
    premise_fact_ids: [],
  },
  obligation: {
    obligation_id: 'root:even-perfect-triangular-mersenne',
    premises: [],
    goal: P3_STATEMENT,
    route_id: 'root',
    status: 'OPEN',
    resolved_by_fact_id: null,
  },
  facts: [],
  closure_fact_ids: [],
  attempts: [
    {
      attempt_id: 'attempt-000045',
      problem_id: 'even-perfect-triangular-mersenne',
      obligation_id: 'root:even-perfect-triangular-mersenne',
      candidate_artifact: {
        // Strengthened claim — does NOT match the obligation goal, so the
        // submission-contract guard rejected it and no fresh verifier ran.
        // The guard's SYNTHETIC VerificationResult is still persisted as
        // verifier_artifact (obligation_execution.py:93-106), so on disk this
        // looks exactly like a verifier rejection; failureSource is the
        // prototype-only field that preserves the true origin.
        statement:
          'Every even perfect number $n = 2^{p-1}(2^p - 1)$, with $2^p - 1$ prime, equals the triangular number $T_{2^p - 1}$, and the exponent $p$ is itself prime.',
        proof:
          'Since $2^p - 1$ is prime, $p$ must be prime: if $p = ab$ with $a, b > 1$ then $2^a - 1$ divides $2^p - 1$. Moreover $2^{p-1}(2^p-1) = \\frac{(2^p-1)2^p}{2} = T_{2^p-1}$ by direct expansion.',
        predecessors: [],
      },
      verifier_artifact: {
        accepted: false,
        reason: 'candidate statement does not match obligation goal',
      },
      verdict: 'FAIL',
      error: null,
      failureSource: 'contract_guard',
    },
  ],
  derived_from: 'even-perfect-triangular',
  last_activity: '2 hours ago',
}

// ---------------------------------------------------------------------------
// Problem 4 — OPEN, latest attempt is a runtime error.
// ---------------------------------------------------------------------------

const P4_STATEMENT = 'There are infinitely many primes $p$ such that $p + 2$ is also prime.'

const p4: WorkspaceModel = {
  spec: { problem_id: 'twin-primes-infinite', statement: P4_STATEMENT, premise_fact_ids: [] },
  obligation: {
    obligation_id: 'root:twin-primes-infinite',
    premises: [],
    goal: P4_STATEMENT,
    route_id: 'root',
    status: 'OPEN',
    resolved_by_fact_id: null,
  },
  facts: [],
  closure_fact_ids: [],
  attempts: [
    {
      attempt_id: 'attempt-000049',
      problem_id: 'twin-primes-infinite',
      obligation_id: 'root:twin-primes-infinite',
      candidate_artifact: {
        statement: P4_STATEMENT,
        proof:
          'Let $\\pi_2(x)$ count twin primes up to $x$. A Brun sieve gives $\\pi_2(x) \\gg x / (\\log x)^2$, which tends to infinity, so there are infinitely many twin primes.',
        predecessors: [],
      },
      verifier_artifact: {
        accepted: false,
        reason:
          "Brun's sieve yields an upper bound $\\pi_2(x) \\ll x/(\\log x)^2$, not a lower bound; the claimed $\\gg$ estimate reverses the inequality without justification, so the argument does not establish infinitude.",
      },
      verdict: 'FAIL',
      error: null,
    },
    {
      attempt_id: 'attempt-000052',
      problem_id: 'twin-primes-infinite',
      obligation_id: 'root:twin-primes-infinite',
      candidate_artifact: null,
      verifier_artifact: null,
      verdict: 'ERROR',
      error: 'worker subprocess timed out after 600s (codex exec killed; no output written)',
    },
  ],
  last_activity: 'yesterday',
}

// ---------------------------------------------------------------------------
// Problem 5 — RUNNING, pre-candidate ("Generating candidate…").
// ---------------------------------------------------------------------------

const P5_STATEMENT = 'Every prime $p \\equiv 1 \\pmod{4}$ is a sum of two squares.'

const p5: WorkspaceModel = {
  spec: { problem_id: 'prime-1mod4-two-squares', statement: P5_STATEMENT, premise_fact_ids: [] },
  obligation: {
    obligation_id: 'root:prime-1mod4-two-squares',
    premises: [],
    goal: P5_STATEMENT,
    route_id: 'root',
    status: 'RUNNING',
    resolved_by_fact_id: null,
  },
  facts: [],
  closure_fact_ids: [],
  attempts: [
    {
      attempt_id: 'attempt-000058',
      problem_id: 'prime-1mod4-two-squares',
      obligation_id: 'root:prime-1mod4-two-squares',
      candidate_artifact: null,
      verifier_artifact: null,
      verdict: 'RUNNING',
      error: null,
    },
  ],
  last_activity: 'just now',
}

// ---------------------------------------------------------------------------
// Problem 6 — RUNNING, post-candidate ("Checking candidate…").
// ---------------------------------------------------------------------------

const P6_STATEMENT =
  'For every integer $n \\geq 2$, the harmonic number $H_n = 1 + \\tfrac{1}{2} + \\cdots + \\tfrac{1}{n}$ is not an integer.'

const p6: WorkspaceModel = {
  spec: { problem_id: 'harmonic-noninteger', statement: P6_STATEMENT, premise_fact_ids: [] },
  obligation: {
    obligation_id: 'root:harmonic-noninteger',
    premises: [],
    goal: P6_STATEMENT,
    route_id: 'root',
    status: 'RUNNING',
    resolved_by_fact_id: null,
  },
  facts: [],
  closure_fact_ids: [],
  attempts: [
    {
      attempt_id: 'attempt-000061',
      problem_id: 'harmonic-noninteger',
      obligation_id: 'root:harmonic-noninteger',
      candidate_artifact: {
        statement: P6_STATEMENT,
        proof:
          'Let $2^r$ be the largest power of two not exceeding $n$, so $2^r \\leq n < 2^{r+1}$. Among $1, \\ldots, n$ exactly one integer — $2^r$ itself — is divisible by $2^r$. Bring $H_n$ to the common denominator $D = \\mathrm{lcm}(1, \\ldots, n)$, which has $2$-adic valuation $r$. Every term $D/k$ is even except $D/2^r$, which is odd; hence the numerator is odd while $D$ is even, so $H_n$ cannot be an integer.',
        predecessors: [],
      },
      verifier_artifact: null,
      verdict: 'RUNNING',
      error: null,
    },
  ],
  last_activity: 'just now',
}

/** Display order on Home. p3 is nested under p2 as a collapsed fork. */
export const WORKSPACES: WorkspaceModel[] = [p1, p2, p3, p4, p5, p6]

export function getWorkspace(problemId: string): WorkspaceModel | undefined {
  return WORKSPACES.find((w) => w.spec.problem_id === problemId)
}

// ---------------------------------------------------------------------------
// Derivations (mirror what the ADR-0005 read model would compute).
// ---------------------------------------------------------------------------

export type DisplayStatus = 'SOLVED' | 'OPEN' | 'RUNNING' | 'ERROR'

export function latestAttempt(m: WorkspaceModel): AttemptEvidence | undefined {
  return m.attempts[m.attempts.length - 1]
}

export function displayStatus(m: WorkspaceModel): DisplayStatus {
  if (m.obligation.status === 'DISCHARGED') return 'SOLVED'
  if (m.obligation.status === 'RUNNING') return 'RUNNING'
  if (latestAttempt(m)?.verdict === 'ERROR') return 'ERROR'
  return 'OPEN'
}

export type RunningPhase = 'generating' | 'checking'

/** ADR-0003: the phase is INFERRED from artifact presence, not a backend event. */
export function runningPhase(a: AttemptEvidence): RunningPhase {
  return a.candidate_artifact ? 'checking' : 'generating'
}

export type FailureClass = 'contract' | 'rejection' | 'runtime'

/**
 * ERROR is reliably derivable from the verdict. FAIL is NOT: the contract
 * guard and the fresh verifier both persist verifier_artifact.accepted=false
 * (the guard's reason is a synthetic VerificationResult), so the persisted
 * schema alone cannot tell them apart. Classification therefore reads the
 * prototype-only failureSource field; a FAIL without it is conservatively
 * shown as a verification rejection.
 */
export function failureClass(a: AttemptEvidence): FailureClass | null {
  if (a.verdict === 'ERROR') return 'runtime'
  if (a.verdict === 'FAIL') return a.failureSource === 'contract_guard' ? 'contract' : 'rejection'
  return null
}

/** Human labels for closure display; raw fact ids never appear in body text. */
export function factLabel(m: WorkspaceModel, factId: string): string {
  const idx = m.closure_fact_ids.indexOf(factId)
  const isTarget = m.obligation.resolved_by_fact_id === factId
  if (isTarget) return 'Main theorem'
  if (idx === -1) return 'Fact'
  return `Lemma ${idx}`
}

export function getFact(m: WorkspaceModel, factId: string): Fact | undefined {
  return m.facts.find((f) => f.fact_id === factId)
}
