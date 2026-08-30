---
fact_id: c16f4ee93ffaf9fb
problem_id: n18c_vieta_jumping_square_20260829t181235z
author: high
predecessors: []
glossary_introduces:
  a: a positive integer from the theorem statement
  b: a positive integer from the theorem statement
  c: the integer kb-a used for the Vieta descent
  d: the nonnegative integer a-kb used when testing whether c can be nonpositive
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
Let
\[
k=\frac{a^2+b^2}{ab+1}.
\]
The numerator and denominator are positive and the hypothesis says that the quotient is an integer, so k is a positive integer. Equivalently,
\[
a^2+b^2=k(ab+1). \tag{1}
\]

Assume for contradiction that the conclusion is false for at least one pair of positive integers. Among all pairs for which k is not a perfect square, choose one for which a+b is minimal. Since equation (1) is symmetric in a and b, interchange a and b if necessary so that a\ge b.

Because 1 is a perfect square, k is not equal to 1. We first exclude b=1. If b=1, then (1) gives
\[
a^2+1=k(a+1).
\]
Thus a+1 divides a^2+1. But
\[
a^2+1=(a+1)(a-1)+2,
\]
so a+1 divides 2. Since a is positive, a+1\ge2, hence a+1=2. This gives a=1 and then k=1, a contradiction. Therefore b\ge2.

Define the integer
\[
c=kb-a.
\]
We prove that c>0. Suppose instead that c\le0, and define the nonnegative integer d=a-kb=-c. Thus a=kb+d. Substituting this expression for a into (1) gives
\[
(kb+d)^2+b^2=k((kb+d)b+1).
\]
Expanding both sides and cancelling k^2b^2 yields
\[
kbd+d^2+b^2=k,
\]
or
\[
k(1-bd)=b^2+d^2. \tag{2}
\]
The right-hand side of (2) is positive, and k is positive, so 1-bd>0. Since b and d are nonnegative integers and b is positive, bd is a nonnegative integer less than 1. Hence bd=0, and therefore d=0. Equation (2) now gives k=b^2, contradicting the assumption that k is not a perfect square. This proves c>0.

Rearranging (1) gives
\[
a(kb-a)=b^2-k.
\]
Using the definition of c, this is
\[
ac=b^2-k. \tag{3}
\]
Since a>0 and c>0, equation (3) implies b^2-k>0. Consequently,
\[
0<c=\frac{b^2-k}{a}<\frac{b^2}{a}\le b,
\]
where the last inequality uses a\ge b>0. Thus c is a positive integer strictly smaller than b.

It remains to check that b and c give the same quotient k. Using c=kb-a and then (1), we obtain
\[
\begin{aligned}
b^2+c^2-k(bc+1)
&=b^2+(kb-a)^2-k\bigl(b(kb-a)+1\bigr)\\
&=a^2+b^2-kab-k\\
&=0.
\end{aligned}
\]
Therefore
\[
\frac{b^2+c^2}{bc+1}=k.
\]
The pair (b,c) consists of positive integers and has the same nonsquare integer quotient k. Moreover, c<b\le a implies c<a, so
\[
b+c<a+b.
\]
This contradicts the minimal choice of a+b. Hence no nonsquare integer quotient can occur, and the integer in the statement is a perfect square.

## intuition
Choose a hypothetical nonsquare solution of minimal size and replace the larger variable by the other root of its quadratic equation. The companion root is positive unless the quotient is already a square, and it is smaller than the smaller original variable, producing an impossible descent.
