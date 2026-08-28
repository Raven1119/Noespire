# Fresh review packet: B2 high2 intermediate route

Review only the evidence in this packet. Do not inspect the repository or infer a desired experimental result.

## Original theorem

Two convex quadrilaterals are called partners if they have three vertices in common and they can be labeled \(ABCD\) and \(ABCE\) so that \(E\) is the reflection of \(D\) across the perpendicular bisector of the diagonal \(AC\). Is there an infinite sequence of convex quadrilaterals such that each quadrilateral is a partner of its successor and no two elements of the sequence are congruent?

## Local available premises

None at worker start.

## Attempted intermediate claim

Let \(a,b,c,d,K\) be positive real numbers. There are at most two congruence classes of convex quadrilaterals \(PQRS\) satisfying \(PQ=a\), \(QR=b\), \(RS=c\), \(SP=d\), and having area \(K\).

## Actual submitted worker attempt

The following is copied from accepted Fact `66e0f3ce87e4696d`:

> Let PQRS be such a convex quadrilateral. Put x=PR and t=x^2. The diagonal PR lies inside the convex quadrilateral and divides it into the nondegenerate triangles PQR and PRS. Let U and V denote their respective positive areas. Then K=U+V.
>
> Apply this identity to PQR and PRS, and define
> F(t)=4a^2b^2-(a^2+b^2-t)^2
> and
> G(t)=4c^2d^2-(c^2+d^2-t)^2.
> Then 16U^2=F(t) and 16V^2=G(t). Since U and V are positive,
> 4K=4U+4V=sqrt(F(t))+sqrt(G(t)).
> It follows that
> 8K sqrt(F(t))=16K^2+F(t)-G(t),
> and, after squaring,
> 64K^2F(t)=(16K^2+F(t)-G(t))^2.
>
> Thus F(t)-G(t) is a polynomial of degree at most one. Therefore equation (1) is a polynomial equation in t of degree at most two. More precisely, if A=2(a^2+b^2-c^2-d^2), then the coefficient of t^2 after bringing the two sides of (1) to one side is A^2+64K^2, which is strictly positive because K>0. Hence that polynomial is nonzero and has at most two real roots.
>
> For each fixed admissible length PR, the three side lengths PQ, QR, PR determine triangle PQR up to congruence, and the three side lengths SP, RS, PR determine triangle PRS up to congruence. Convexity requires Q and S to lie in opposite open half-planes bounded by the line PR. [...] Therefore each admissible diagonal length gives at most one congruence class, and the total number of congruence classes is at most two.

The following is copied from dependent accepted target Fact `9cf65343d0b09f0b`:

> The unordered multiset of the four boundary side lengths is the same for two partners. [...] The area is also the same for two partners. [...] It follows inductively that every member of any sequence of successive partners has the same positive area K and the same unordered multiset of four boundary side lengths as the first member.
>
> There are only finitely many ordered quadruples obtainable by arranging the fixed multiset of four side lengths around a cyclically labeled quadrilateral; in fact there are at most 4!=24 such ordered quadruples. For each of those ordered quadruples, fact 66e0f3ce87e4696d gives at most two congruence classes having area K. Therefore every sequence of successive partners is contained in a set of at most 48 congruence classes.
>
> An infinite sequence in which no two elements are congruent would contain infinitely many congruence classes, contradicting the preceding finite bound.

## Verifier result

- Intermediate claim: PASS, fact `66e0f3ce87e4696d`, no predecessors.
- Full target: PASS, fact `9cf65343d0b09f0b`, predecessor `66e0f3ce87e4696d`.
- Both submissions occurred in the same single worker round.
- Per-submission token attribution and duration are unavailable.
- The intermediate has one observed downstream use (the full target).
- A separate self-contained target proof was mechanically selected for the final closure, so these two accepted facts lie outside that selected closure.

## Necessary local trace

The worker reported that external search located the official answer and confirmed that it is negative. It also reported that its submitted Heron-diagonal proof was independently developed and used no external theorem. Whether that self-report establishes independence is not decidable from this packet.

## Required output

Return exactly this YAML shape:

```yaml
classification: DIRECTLY_SOLVABLE | SEARCH_FAILED | TOO_WIDE | MISSING_LEMMA | BAD_DEPENDENCY | COUNTEREXAMPLE | MALFORMED_CLAIM | STRATEGY_WASTE | UNKNOWN
confidence: LOW | MEDIUM | HIGH
evidence: >-
  ...
possible_intermediate_structure: >-
  ...
```
