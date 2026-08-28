# Frozen N1.5 DANUS Diagnostic Problem Source Research

## Selection status and evidence boundary

This note fixes exactly four candidate problems **before any DANUS run**. Selection used only mathematical structure: an exact target, an authoritative first-party source with a published reference solution, at least two meaningful reasoning transitions in the normal solution, and diversity of proof shape. No known or inferred DANUS/Codex performance was used.

The source authority is the Mathematical Association of America's [William Lowell Putnam Competition Archive](https://maa.org/maa-putnam-archive/), which publishes the official problem sets and problem-and-solution documents. Sources were checked on 2026-08-28.

> **Reference-proof firewall:** Only the text under each **Target** heading is eligible for a future DANUS problem input. Every **Offline reference answer/outline** below is evaluator-only material and MUST NOT be placed in `PROBLEM.md`, prompts, tasks, memory, the Fact Graph, or any other DANUS-visible input.

## Problem 1 -- `putnam-2024-a1`

**Structure:** elementary number theory; primitive reduction, parity, and modular obstruction.

### Target

Determine all positive integers \(n\) for which there exist positive integers \(a\), \(b\), and \(c\) satisfying

\[
2a^n+3b^n=4c^n.
\]

### Primary sources

- Problem source: *The 85th William Lowell Putnam Mathematical Competition, 2024, Session A, Problem A1*, in the official MAA [2024 Problems PDF](https://maa.org/wp-content/uploads/2026/02/2024-Putnam-Problems.pdf), p. 1.
- Reference-proof source: Problem A1 in the official MAA [2024 Problems & Solutions PDF](https://maa.org/wp-content/uploads/2026/02/2024-Putnam-Solutions.pdf), p. 1.

### Structural rationale

The classification target is exact and self-contained. A normal proof must do more than spot a congruence: it first removes a common divisor, derives a parity pattern, separates \(n\ge 3\) from \(n=2\), and closes the exceptional exponent with a second modular argument. It requires no search oracle, CAS, numerical approximation, or external theorem database.

### Offline reference answer/outline -- MUST NOT be passed to DANUS

The answer is \(n=1\) only.

1. Exhibit \((a,b,c)=(1,2,2)\) for \(n=1\).
2. For \(n\ge2\), divide a hypothetical solution by \(\gcd(a,b,c)\), obtaining a primitive triple \((x,y,z)\). Parity forces \(y\) even, then \(x\) even, and hence \(z\) odd.
3. If \(n\ge3\), the left side is divisible by \(8\), whereas \(4z^n\equiv4\pmod 8\), a contradiction.
4. If \(n=2\), write \(2(x/2)^2+3(y/2)^2=z^2\). Here \(y/2\) and \(z\) are odd; reducing modulo \(8\) would require \(2(x/2)^2\equiv6\pmod8\), impossible.

## Problem 2 -- `putnam-2024-a2`

**Structure:** algebra; polynomial composition, divisibility, and degree comparison.

### Target

For which real polynomials \(p\) is there a real polynomial \(q\) such that

\[
p(p(x))-x=(p(x)-x)^2q(x)
\]

for all real \(x\)?

### Primary sources

- Problem source: *The 85th William Lowell Putnam Mathematical Competition, 2024, Session A, Problem A2*, in the official MAA [2024 Problems PDF](https://maa.org/wp-content/uploads/2026/02/2024-Putnam-Problems.pdf), p. 1.
- Reference-proof source: Problem A2, Solution 1, in the official MAA [2024 Problems & Solutions PDF](https://maa.org/wp-content/uploads/2026/02/2024-Putnam-Solutions.pdf), pp. 1-2.

### Structural rationale

The task has an exact classification and a clean internal proof boundary. It requires introducing the right auxiliary polynomial, translating a composition identity into divisibility, using a finite polynomial expansion, and resolving the resulting alternatives by degree before checking sufficiency. This is symbolic natural-language reasoning, not a request for computer algebra.

### Offline reference answer/outline -- MUST NOT be passed to DANUS

The polynomials are exactly \(p(x)=x+c\) and \(p(x)=-x+c\), for real constants \(c\).

1. Set \(f(x)=p(x)-x\). Then \(p(p(x))-x=f(x+f(x))+f(x)\).
2. The exact finite Taylor expansion of the polynomial \(f(x+f(x))\) shows that divisibility by \(f(x)^2\) is equivalent, apart from \(f\equiv0\), to \(f\mid(2+f')\).
3. If \(f\) is nonconstant, \(\deg(2+f')<\deg f\), so divisibility forces \(2+f'=0\), giving \(f=-2x+c\). If \(f\) is constant, \(f=c\). Translating back gives the two asserted families.
4. Substitute both families into the original identity to verify that a polynomial \(q\) exists (with \(q=0\) for \(p=-x+c\); for \(p=x+c\), choose a suitable constant \(q\), with the zero case immediate).

## Problem 3 -- `putnam-2023-b1`

**Structure:** enumerative combinatorics; invariant state representation, reversibility, and lattice-path counting.

### Target

Consider an \(m\)-by-\(n\) grid of unit squares, indexed by \((i,j)\) with \(1\le i\le m\) and \(1\le j\le n\). There are \((m-1)(n-1)\) coins, which are initially placed in the squares \((i,j)\) with \(1\le i\le m-1\) and \(1\le j\le n-1\). If a coin occupies the square \((i,j)\) with \(i\le m-1\) and \(j\le n-1\), and the squares \((i+1,j)\), \((i,j+1)\), and \((i+1,j+1)\) are unoccupied, then a legal move is to slide the coin from \((i,j)\) to \((i+1,j+1)\). How many distinct configurations of coins can be reached from the initial configuration by a possibly empty sequence of legal moves?

### Primary sources

- Problem source: *The 84th William Lowell Putnam Mathematical Competition, 2023, Session B, Problem B1*, in the official MAA [2023 Problems PDF](https://maa.org/wp-content/uploads/2025/02/2023-Putnam-Problems.pdf), p. 2.
- Reference-proof source: Problem B1, Solution 1, in the official MAA [2023 Problems & Solutions PDF](https://maa.org/wp-content/uploads/2025/02/2023-Putnam-Problems-and-Solutions.pdf), pp. 16-17.

### Structural rationale

This problem tests whether a proof search can discover a representation rather than merely manipulate the stated move. A complete proof must establish an invariant map from configurations to lattice paths, prove the converse reachability claim using reversed local moves, and only then count the paths. The variables remain symbolic; no enumeration or numerical search is needed.

### Offline reference answer/outline -- MUST NOT be passed to DANUS

The number of reachable configurations is

\[
\binom{m+n-2}{m-1}.
\]

1. Represent the unoccupied squares as a lattice path from \((1,n)\) to \((m,1)\) containing \(m-1\) east steps and \(n-1\) south steps.
2. A legal coin move changes one local `ES` portion of this empty-square path to `SE`, so the path description is invariant under all reachable moves.
3. Conversely, repeatedly reverse an `SE` to `ES`; this terminates at the initial path. Reversing those coin slides proves that every such lattice path corresponds to a reachable configuration.
4. Count the words with \(m-1\) copies of `E` and \(n-1\) copies of `S`.

## Problem 4 -- `putnam-2024-b2`

**Structure:** Euclidean geometry; reflection invariants, finite state reduction, and congruence uniqueness.

### Target

Two convex quadrilaterals are called partners if they have three vertices in common and they can be labeled \(ABCD\) and \(ABCE\) so that \(E\) is the reflection of \(D\) across the perpendicular bisector of the diagonal \(AC\). Is there an infinite sequence of convex quadrilaterals such that each quadrilateral is a partner of its successor and no two elements of the sequence are congruent?

### Primary sources

- Problem source: *The 85th William Lowell Putnam Mathematical Competition, 2024, Session B, Problem B2*, in the official MAA [2024 Problems PDF](https://maa.org/wp-content/uploads/2026/02/2024-Putnam-Problems.pdf), p. 2.
- Reference-proof source: Problem B2, especially Solution 2, in the official MAA [2024 Problems & Solutions PDF](https://maa.org/wp-content/uploads/2026/02/2024-Putnam-Solutions.pdf), pp. 15-17.

### Structural rationale

The target is an exact yes/no assertion with all geometric operations defined. The reference route requires extracting invariants preserved by the partnership, reducing an apparently infinite process to finitely many ordered data states, and proving that one such state determines a congruence class via the law of cosines and monotonicity. It is synthetic/algebraic geometry without coordinates supplied by a solver.

### Offline reference answer/outline -- MUST NOT be passed to DANUS

No such infinite sequence exists.

1. Represent \(ABCD\) by \((w,x,y,z,\theta)\), where \(w,x,y,z\) are its four side lengths in order and \(\theta=\angle B+\angle D\).
2. Passing to a partner preserves \(\theta\) and only permutes the four side lengths in an appropriate labeling. Hence every member of a partner sequence is represented by one of finitely many permutations of the first quintuple.
3. Prove uniqueness: if \(\phi=\angle B\), then both expressions
   \[
   w^2+x^2-2wx\cos\phi
   \quad\text{and}\quad
   y^2+z^2-2yz\cos(\theta-\phi)
   \]
   equal \(AC^2\). On the convexity interval, the first is strictly increasing in \(\phi\) and the second strictly decreasing, so the quintuple fixes \(\phi\), and then fixes the two triangles along \(AC\) up to congruence.
4. An infinite sequence repeats a representing quintuple by the pigeonhole principle; the corresponding quadrilaterals are congruent, contradicting the requirement.

## Freeze recommendation

Freeze the ordered IDs exactly as listed:

1. `putnam-2024-a1`
2. `putnam-2024-a2`
3. `putnam-2023-b1`
4. `putnam-2024-b2`

The four targets cover number-theoretic obstruction, algebraic classification, combinatorial bijection, and geometric invariant/finite-state reasoning. All have first-party published solutions and require multiple meaningful proof steps. None calls for Lean, a CAS, numerical search, or resolution of an open conjecture.
