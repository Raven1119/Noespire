# N1.6 New-Proof Problem Candidate Research

## Scope and source policy

This note proposes six **new** proof problems for the N1.6 freeze. It deliberately excludes the triangular-sum identity, the identity that the sum of the first odd numbers is a square, divisibility of \(n^3-n\) by \(6\), Putnam 2024 A1, Putnam 2024 A2, Putnam 2023 B1, and Putnam 2024 B2.

Every candidate below comes from the Mathematical Association of America's official [Putnam archive](https://maa.org/maa-putnam-archive/). Only the official MAA problem PDFs and official MAA solution PDFs were used; no secondary solution source was consulted. Selection was based on proof structure and the presence of a small, inspectable dependency graph, not on any prediction of DANUS behavior. No DANUS experiment was run.

The blockquoted statement under each candidate is the proposed **worker-facing statement**. The proof outline is evaluator-only and should not be included in a blind worker prompt.

## Recommended freeze order

1. **2019 A1** — strongest elementary algebra/number-theory DAG, with construction and obstruction branches.
2. **2022 A3** — clean recurrence lemma followed by orbit counting and a fixed-point residue analysis.
3. **2020 A2** — compact combinatorial double count with a genuine first-hit decomposition lemma.
4. **2019 B3** — a distinct linear-algebra proof organized around one reusable eigenvalue-parity lemma.

Use **2022 A2** as the first reserve if matrix spectral machinery makes 2019 B3 undesirable for this freeze. Use **2022 B3** as the second reserve; its reasoning graph is excellent, but its arbitrary coloring of \(\mathbb R_{>0}\) introduces a more set-theoretic statement boundary.

---

## Candidate 1 — 2019 Putnam A1: values of a symmetric cubic form

**Official problem source:** [2019 Putnam Problems, A1, PDF p. 1](https://maa.org/wp-content/uploads/2024/10/2019PutnamProblems.pdf#page=1)

**Official reference solution:** [2019 Putnam Problem Solutions, A1, PDF p. 1](https://maa.org/wp-content/uploads/2025/02/2019-Putnam-Problem-Solutions.pdf#page=1)

**Worker-facing statement**

> Characterize the nonnegative integers representable in the form
> \[
> a^3+b^3+c^3-3abc
> \]
> with \(a,b,c\) nonnegative integers. Prove that a nonnegative integer \(N\) has such a representation if and only if either \(3\nmid N\) or \(9\mid N\).

**Structural rationale:** The proof has two independently checkable halves—explicit representations and an arithmetic obstruction—and neither half merely repeats the final conclusion. A meaningful intermediate lemma is that divisibility of the cubic form by \(3\) automatically strengthens to divisibility by \(9\). A natural Research DAG has four facts: residue-class constructions, nonnegativity, the mod-3 reduction, and the mod-9 strengthening.

**Evaluator-only proof outline:**

1. Construct all allowed values: \(f(t,t,t)=0\), \(f(t,t,t+1)=3t+1\), \(f(t,t,t-1)=3t-1\) for \(t\ge 1\), and \(f(t,t+1,t-1)=9t\) for \(t\ge 1\).
2. Show \(f(a,b,c)\ge 0\), for example from AM-GM or from the standard factorization of \(a^3+b^3+c^3-3abc\).
3. Cubes are congruent to their bases modulo \(3\), so \(3\mid f(a,b,c)\) implies \(a+b+c\equiv0\pmod3\).
4. Write \(c=3k-a-b\) and expand; the result has an overall factor \(9\). Hence a represented multiple of \(3\) is a multiple of \(9\), completing the converse.

**Non-overlap with exclusions:** This is an image-classification theorem for a three-variable symmetric cubic form. It is not a finite-sum identity, not the one-variable theorem \(6\mid n^3-n\), and its official ID is 2019 A1 rather than any excluded 2023/2024 problem.

---

## Candidate 2 — 2022 Putnam A3: a period-five finite-field recurrence

**Official problem source:** [2022 Putnam Problems, A3, PDF p. 1](https://maa.org/wp-content/uploads/2024/10/2022_Putnam_Competitions.pdf#page=1)

**Official reference solution:** [2022 Putnam Solutions, A3, PDF pp. 3–4](https://maa.org/wp-content/uploads/2024/10/2022-Putnam-solutions.pdf#page=3)

**Worker-facing statement**

> Fix a prime \(p>5\). Let \(F(p)\) be the number of infinite sequences \((a_n)_{n\ge1}\) with every \(a_n\in\{1,2,\ldots,p-1\}\) and
> \[
> a_n a_{n+2}\equiv 1+a_{n+1}\pmod p
> \]
> for every \(n\ge1\). Prove that \(F(p)\equiv0\) or \(2\pmod5\).

**Structural rationale:** The central discovery is a recurrence invariant: every admissible sequence has period five. That lemma converts an infinite-sequence problem into a finite cyclic-action problem. The remaining nodes—classification of orbit sizes and counting constant sequences—depend cleanly on it, giving a compact but nontrivial three-layer proof graph.

**Evaluator-only proof outline:**

1. First note that no \(a_{n+1}\) is \(-1\) modulo \(p\). Starting from \(a_1,a_2\), successively simplify the recurrence to obtain
   \[
   a_3=\frac{1+a_2}{a_1},\quad
   a_4=\frac{1+a_1+a_2}{a_1a_2},\quad
   a_5=\frac{1+a_1}{a_2},\quad
   a_6=a_1,\quad a_7=a_2
   \]
   in \(\mathbb F_p\). Uniqueness of the next term then gives \(a_{n+5}=a_n\).
2. Cyclic shift acts on the admissible sequences. Every nonconstant sequence has an orbit of size \(5\), because \(5\) is prime; hence nonconstant sequences contribute a multiple of \(5\).
3. Constant sequences correspond exactly to \(c^2-c-1=0\) in \(\mathbb F_p\), equivalently \((2c-1)^2=5\). A nonzero field element has either zero or two square roots, and the resulting \(c\)'s are admissible. Thus the fixed-point contribution is \(0\) or \(2\) modulo \(5\).

**Non-overlap with exclusions:** The subject is a nonlinear recurrence over a finite field together with a cyclic group action. It is unrelated to the excluded elementary sums and cubic divisibility result, and 2022 A3 is not one of the excluded Putnam IDs.

---

## Candidate 3 — 2020 Putnam A2: a weighted binomial identity

**Official problem source:** [2020 Putnam Problems, A2, PDF p. 1](https://maa.org/wp-content/uploads/2024/10/2020Putnam_final.pdf#page=1)

**Official reference solution:** [2020 Putnam Solutions, A2, PDF pp. 2–3](https://maa.org/wp-content/uploads/2024/10/2020-Putnam-Solutions.pdf#page=2)

**Worker-facing statement**

> Prove that for every nonnegative integer \(k\),
> \[
> \sum_{j=0}^{k}2^{k-j}\binom{k+j}{j}=4^k.
> \]

**Structural rationale:** This is not a routine induction after the right proof object is chosen. The key intermediate lemma partitions a symmetric set of length-\(2k+1\) lattice paths by the height at which a path first crosses a vertical boundary. It yields a small Research DAG: global path count, symmetry halving, first-hit prefix/suffix count, and summation.

**Evaluator-only proof outline:**

1. Consider all \(2^{2k+1}\) paths of length \(2k+1\) using unit right and up steps. Since one of the two step types must occur at least \(k+1\) times, and swapping right/up has no fixed point in this odd-length setting, exactly half—\(2^{2k}=4^k\)—have at least \(k+1\) right steps.
2. Partition those paths by the first point where they reach \(x=k+1\). If this first point is \((k+1,j)\), the prefix before the crossing has \(k\) right steps and \(j\) up steps, hence \(\binom{k+j}{j}\) possibilities.
3. After the crossing, \(k-j\) unrestricted steps remain, giving \(2^{k-j}\) suffixes. Summing over \(0\le j\le k\) counts the same path set and proves the identity.

**Non-overlap with exclusions:** Although this is a sum identity, it is a weighted binomial identity proved by a lattice-path first-hit decomposition, not the triangular-sum or odd-sum identity. It does not involve \(n^3-n\), and 2020 A2 is distinct from all excluded Putnam IDs.

---

## Candidate 4 — 2019 Putnam B3: reflection forces a fixed vector

**Official problem source:** [2019 Putnam Problems, B3, PDF p. 2](https://maa.org/wp-content/uploads/2024/10/2019PutnamProblems.pdf#page=2)

**Official reference solution:** [2019 Putnam Problem Solutions, B3, PDF p. 9](https://maa.org/wp-content/uploads/2025/02/2019-Putnam-Problem-Solutions.pdf#page=9)

**Worker-facing statement**

> Let \(Q\) be a real \(n\times n\) orthogonal matrix, and let \(u\in\mathbb R^n\) satisfy \(u^{\mathsf T}u=1\). Define
> \[
> H=I-2uu^{\mathsf T}.
> \]
> Assume there is no nonzero vector \(v\) with \(Qv=v\). Prove that there is a nonzero vector \(w\) with \(HQw=w\).

**Structural rationale:** The theorem connects a concrete rank-one reflection calculation to a general spectral parity lemma. The intermediate lemma—an orthogonal matrix with the parity-opposed determinant sign must have eigenvalue \(1\)—is meaningful independently of the target. The proof has a clean separation between local matrix algebra and global eigenvalue bookkeeping.

**Evaluator-only proof outline:**

1. Show that \(H\) sends \(u\) to \(-u\), fixes \(u^\perp\), is orthogonal, and has determinant \(-1\).
2. Therefore \(Q\) and \(HQ\) are orthogonal matrices of the same dimension with opposite determinants.
3. Prove the lemma: if a real orthogonal \(n\times n\) matrix has determinant \(1\) with odd \(n\), or determinant \(-1\) with even \(n\), then it has eigenvalue \(1\). Indeed, nonreal eigenvalues have modulus one and occur in conjugate pairs whose products are one; parity and the total product of eigenvalues force a remaining \(+1\).
4. In the relevant parity, exactly one of \(Q\) and \(HQ\) has the determinant sign covered by the lemma. The hypothesis rules out \(Q\), so the lemma applies to \(HQ\).

**Non-overlap with exclusions:** This is a fixed-vector theorem for orthogonal matrices and a Householder reflection. It has no sum or integer-divisibility content, and its source is 2019 B3, not an excluded 2023/2024 problem.

---

## Candidate 5 — 2022 Putnam A2: negative coefficients in a polynomial square

**Official problem source:** [2022 Putnam Problems, A2, PDF p. 1](https://maa.org/wp-content/uploads/2024/10/2022_Putnam_Competitions.pdf#page=1)

**Official reference solution:** [2022 Putnam Solutions, A2, PDF p. 2](https://maa.org/wp-content/uploads/2024/10/2022-Putnam-solutions.pdf#page=2)

**Worker-facing statement**

> Let \(n\ge2\). As \(p(x)\) ranges over all real polynomials of degree exactly \(n\), determine the largest possible number of negative coefficients in \(p(x)^2\). Prove that the answer is \(2n-2\).

**Structural rationale:** Extremal existence and extremal impossibility are genuinely different branches. The upper-bound branch contains a useful sign lemma about convolution coefficients: if every non-end coefficient of a square were negative, a maximal positive input coefficient would force a positive output coefficient. This gives three to four substantial proof nodes without relying on enumeration.

**Evaluator-only proof outline:**

1. For large positive \(R\), take
   \[
   p(x)=Rx^n-x^{n-1}-\cdots-x+R.
   \]
   In \(p(x)^2\), the coefficients of degrees \(0,n,2n\) are positive for sufficiently large \(R\), while every other coefficient is \(-2R\) plus a constant independent of \(R\). Hence \(2n-2\) negative coefficients are attainable.
2. The constant and leading coefficients of any square are nonnegative. If \(2n-1\) coefficients were negative, every coefficient of degrees \(1,\ldots,2n-1\) would therefore be negative.
3. Write \(p(x)=\sum_{i=0}^n a_i x^i\) and assume \(a_n>0\). Negativity of the coefficient of \(x\) makes \(a_0,a_1\) nonzero with opposite signs, so some \(a_k>0\) occurs with \(k<n\). Choose the largest such \(k\).
4. The coefficient of \(x^{n+k}\) equals \(2a_ka_n\) plus products of pairs of coefficients whose indices are both larger than \(k\) and below \(n\). The first term is positive and all remaining products are nonnegative by maximality of \(k\), contradicting the assumed negativity.

**Non-overlap with exclusions:** This is an extremal theorem about coefficient convolution and signs. It is neither an integer-sum identity nor the divisibility of a cubic expression, and its 2022 A2 source ID is distinct from the excluded Putnam problems.

---

## Candidate 6 — 2022 Putnam B3: stabilization of a distance recoloring

**Official problem source:** [2022 Putnam Problems, B3, PDF p. 2](https://maa.org/wp-content/uploads/2024/10/2022_Putnam_Competitions.pdf#page=2)

**Official reference solution:** [2022 Putnam Solutions, B3, PDF p. 12](https://maa.org/wp-content/uploads/2024/10/2022-Putnam-solutions.pdf#page=12)

**Worker-facing statement**

> Begin with an arbitrary red-blue coloring of the positive real numbers. From any current coloring, define the next coloring as follows: a distance \(d>0\) is red exactly when there exist two positive reals of the same current color whose distance is \(d\); otherwise \(d\) is blue. Prove that after applying this recoloring rule twice, every positive real number is red.

**Structural rationale:** The target is global, but the proof is driven by a local scale lemma relating \(d\) and \(2d\). A second layer turns hypothetical blueness after two rounds into a forced alternating pattern, and a final midpoint argument contradicts it. This produces a particularly legible Research Fact DAG with one reusable lemma and two dependent contradiction facts.

**Evaluator-only proof outline:**

1. Lemma: after one recoloring, \(d\) and \(2d\) cannot both be blue. If \(d\) is blue, then in the preceding coloring the points \(x,x+d,x+2d,\ldots\) alternate colors, so points distance \(2d\) apart have the same color; hence \(2d\) is red.
2. Suppose \(d\) were blue after the second recoloring. In the once-recolored coloring, \(d,2d,3d,4d\) must alternate. The lemma forces \(2d,4d\) to be red and therefore \(d,3d\) to be blue.
3. Since \(d\) was blue after the first recoloring, the original colors at \(d,2d,3d,4d\) alternate. The point \(5d/2\) shares a color with one of \(2d,3d\) and with one of \(d,4d\); consequently both \(d/2\) and \(3d/2\) are red after the first recoloring.
4. Those two numbers are distance \(d\) apart, so \(d\) must be red after the second recoloring, a contradiction.

**Non-overlap with exclusions:** This is a Ramsey-style coloring process on positive real distances. It shares no mathematical object or proof mechanism with the excluded identities or cubic divisibility theorem, and 2022 B3 is not an excluded Putnam ID.

## Freeze recommendation in one line

Freeze **2019 A1, 2022 A3, 2020 A2, and 2019 B3** for the most structurally diverse four-problem set; retain **2022 A2** and **2022 B3** as ordered reserves.
