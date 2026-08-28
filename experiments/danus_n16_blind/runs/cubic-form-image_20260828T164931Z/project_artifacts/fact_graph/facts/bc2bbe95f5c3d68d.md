---
fact_id: bc2bbe95f5c3d68d
problem_id: n16_cubic_form_image_20260828t164931z
author: xhigh
predecessors: []
glossary_introduces:
  N: A nonnegative integer whose representability is being characterized.
  Q: The quadratic factor a^2+b^2+c^2-ab-bc-ca.
  a: The first nonnegative integer coordinate in a representation of N.
  b: The second nonnegative integer coordinate in a representation of N.
  c: The third nonnegative integer coordinate in a representation of N.
  m: The nonnegative integer N/9 when 9 divides N.
  t: A nonnegative integer quotient used for values congruent to 1 or 2 modulo 3.
  u: An arbitrary integer used to prove the cubic congruence modulo 3.
  x: An integer variable in the two-equal-coordinate identity.
  y: An integer variable in the two-equal-coordinate identity.
external_refs: []
---

## statement
Characterize the nonnegative integers representable in the form
\[
a^3+b^3+c^3-3abc
\]
with \(a,b,c\) nonnegative integers. Prove that a nonnegative integer \(N\) has such a representation if and only if either \(3\nmid N\) or \(9\mid N\).

## proof
Let \(N\) be a nonnegative integer.

First suppose that \(N\) has a representation
\[
N=a^3+b^3+c^3-3abc
\]
with \(a,b,c\) nonnegative integers. For every integer \(u\), the product \(u(u-1)(u+1)\) of three consecutive integers is divisible by \(3\). Hence \(u^3\equiv u\pmod 3\), and therefore
\[
N\equiv a+b+c\pmod 3.
\]
If \(3\mid N\), it follows that \(3\mid a+b+c\). Direct expansion gives the factorization
\[
a^3+b^3+c^3-3abc=(a+b+c)Q,
\qquad
Q=a^2+b^2+c^2-ab-bc-ca.
\]
Moreover,
\[
Q=(a+b+c)^2-3(ab+bc+ca).
\]
Since \(3\mid a+b+c\), both terms on the right-hand side of the last equality are divisible by \(3\), so \(3\mid Q\). Thus both factors in
\[
N=(a+b+c)Q
\]
are divisible by \(3\), and consequently \(9\mid N\). We have proved that every represented \(N\) satisfies either \(3\nmid N\) or \(9\mid N\).

Conversely, suppose that either \(3\nmid N\) or \(9\mid N\). We use the identity
\[
x^3+2y^3-3xy^2=(x-y)^2(x+2y),
\]
which follows by expanding the right-hand side.

If \(N\equiv1\pmod3\), the division algorithm gives \(N=3t+1\) for a nonnegative integer \(t\). Take
\[
(a,b,c)=(t+1,t,t).
\]
All three coordinates are nonnegative, and the displayed identity gives
\[
a^3+b^3+c^3-3abc=((t+1)-t)^2((t+1)+2t)=3t+1=N.
\]

If \(N\equiv2\pmod3\), the division algorithm gives \(N=3t+2\) for a nonnegative integer \(t\). Take
\[
(a,b,c)=(t,t+1,t+1).
\]
Again all coordinates are nonnegative, and
\[
a^3+b^3+c^3-3abc=(t-(t+1))^2(t+2(t+1))=3t+2=N.
\]
These two cases represent every nonnegative \(N\) for which \(3\nmid N\).

It remains to treat \(9\mid N\). Write \(N=9m\) with \(m\) a nonnegative integer. If \(m=0\), then \(N=0\) is represented by \((a,b,c)=(0,0,0)\). If \(m\geq1\), take
\[
(a,b,c)=(m-1,m,m+1),
\]
whose coordinates are nonnegative. Here \(a+b+c=3m\), while
\[
\begin{aligned}
Q&=(m-1)^2+m^2+(m+1)^2\\
&\quad-\bigl((m-1)m+m(m+1)+(m+1)(m-1)\bigr)\\
&=(3m^2+2)-(3m^2-1)=3.
\end{aligned}
\]
Using the factorization already established,
\[
a^3+b^3+c^3-3abc=(a+b+c)Q=(3m)(3)=9m=N.
\]
Thus every nonnegative \(N\) satisfying \(3\nmid N\) or \(9\mid N\) has the required representation. Together with the necessary condition, this proves the stated equivalence.

## intuition
The cubic splits into a sum factor and a quadratic factor. Modulo 3, divisibility of the cubic forces the sum factor to be divisible by 3, and the relation between the factors forces the quadratic factor to be divisible by 3 as well. Explicit near-diagonal triples realize every remaining admissible integer.
