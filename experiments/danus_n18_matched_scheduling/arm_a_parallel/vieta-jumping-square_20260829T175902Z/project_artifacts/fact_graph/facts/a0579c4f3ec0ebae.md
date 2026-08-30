---
fact_id: a0579c4f3ec0ebae
problem_id: n18a_vieta_jumping_square_20260829t175902z
author: high2
predecessors: []
glossary_introduces:
  a: a positive integer from the theorem statement; in the minimal-counterexample argument, the larger of the two entries after a possible swap
  b: a positive integer from the theorem statement; in the minimal-counterexample argument, the smaller of the two entries after a possible swap
  c: the Vieta conjugate integer kb-a
  k: the positive integer (a^2+b^2)/(ab+1)
external_refs: []
---

## statement
Let (a) and (b) be positive integers. Suppose that

\[
\frac{a^2+b^2}{ab+1}
\]

is an integer. Prove that this integer is a perfect square.

## proof
Let k=(a^2+b^2)/(ab+1). Since a and b are positive integers, both a^2+b^2 and ab+1 are positive. Thus the assumed integer k is a positive integer. Equivalently,

(1)  a^2+b^2=k(ab+1).

Suppose, for contradiction, that the assertion is false. Then there exists at least one ordered pair of positive integers (a,b) satisfying (1) for which k is not a perfect square. Among all such pairs, choose one for which a+b is minimal. Equation (1) is symmetric in a and b, so after interchanging a and b if necessary, assume a>=b.

Define the integer c=kb-a. From (1),

(2)  ac=akb-a^2=b^2-k.

We first prove b^2>=k. If b^2<k, then (1) also gives

a(a-kb)=k-b^2>0.

The integer a-kb is therefore positive, hence a-kb>=1. Consequently

(3)  k-b^2=a(a-kb)>=a.

Moreover a-kb>0 implies a>kb. Since b>=1 and k>0, kb>=k, so a>k. But b^2>0 gives k-b^2<k. These two inequalities contradict (3), because (3) says k-b^2>=a>k. Therefore b^2>=k.

If b^2=k, then k=b^2 is a perfect square, contrary to the choice of the pair as one for which k is not a perfect square. Hence

(4)  b^2>k.

By (2), c=(b^2-k)/a, so (4) and a>0 imply c>0. Also, because k>0,

c=(b^2-k)/a < b^2/a.

Since a>=b>0, b^2/a<=b. Thus

(5)  0<c<b.

It remains to check that (c,b) is another solution with the same integer k. Using c=kb-a and (1), direct algebra gives

c^2+b^2-k(cb+1)
=(kb-a)^2+b^2-k((kb-a)b+1)
=a^2+b^2-kab-k
=a^2+b^2-k(ab+1)
=0.

Therefore c^2+b^2=k(cb+1). In particular, (c^2+b^2)/(cb+1)=k, because cb+1>0. By (5), c and b are positive integers, and this new pair has c+b<b+b<=a+b. It is therefore a counterexample with strictly smaller sum than the chosen pair, contradicting the minimality of a+b.

The assumption that k is not a perfect square is impossible. Hence the integer (a^2+b^2)/(ab+1) is a perfect square.

## intuition
Treat the equation as a quadratic in its larger entry. The other integral root is smaller and positive unless the quotient already equals b^2, so any nonsquare quotient would generate an infinite descent.
