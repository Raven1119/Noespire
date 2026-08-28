---
fact_id: def86f00ef4b9faa
problem_id: n15_putnam_2024_a1
author: high3
predecessors: []
glossary_introduces:
  a: a positive integer variable in the original equation
  b: a positive integer variable in the original equation
  c: a positive integer variable in the original equation
  d: the greatest common divisor of a, b, and c
  n: the positive integer exponent in the equation
  x: the primitive positive integer a/d
  y: the primitive positive integer b/d
  z: the primitive positive integer c/d
external_refs: []
---

## statement
Determine all positive integers \(n\) for which there exist positive integers \(a\), \(b\), and \(c\) satisfying

\[
2a^n+3b^n=4c^n.
\]

## proof
We prove that the complete set of such positive integers is \(\{1\}\).

Existence for \(n=1\): choose \(a=1\), \(b=2\), and \(c=2\). Then
\[
2a^1+3b^1=2\cdot 1+3\cdot 2=8=4\cdot 2=4c^1.
\]

Nonexistence for every \(n\ge 2\): suppose, for contradiction, that \(n\ge 2\) and that positive integers \(a,b,c\) satisfy the displayed equation. Let
\[
d=\gcd(a,b,c),\qquad x=a/d,\qquad y=b/d,\qquad z=c/d.
\]
Then \(x,y,z\) are positive integers, \(\gcd(x,y,z)=1\), and division of the original equation by \(d^n\) gives
\[
2x^n+3y^n=4z^n. \tag{1}
\]

First suppose \(n\ge 3\). Reducing (1) modulo \(2\) gives \(y^n\equiv 0\pmod 2\), so \(y\) is even. Since \(n\ge 2\), the integer \(y^n\) is divisible by \(4\). From
\[
2x^n=4z^n-3y^n
\]
it follows that \(2x^n\) is divisible by \(4\), so \(x^n\) is even and therefore \(x\) is even. Since \(n\ge 3\) and both \(x\) and \(y\) are even, both \(x^n\) and \(y^n\) are divisible by \(8\). Equation (1) therefore implies that \(4z^n\) is divisible by \(8\). Hence \(z^n\) is even, so \(z\) is even. Thus \(2\) divides \(x,y,z\), contradicting \(\gcd(x,y,z)=1\). Consequently no \(n\ge 3\) works.

It remains to exclude \(n=2\). In this case (1), reduced modulo \(3\), gives
\[
2x^2\equiv z^2\pmod 3. \tag{2}
\]
Every integer square is congruent to either \(0\) or \(1\) modulo \(3\). If \(3\) did not divide \(x\), then \(x^2\equiv 1\pmod 3\), and (2) would give \(z^2\equiv 2\pmod 3\), which is impossible. Hence \(3\mid x\). Equation (2) then gives \(z^2\equiv 0\pmod 3\), hence \(3\mid z\). Thus \(9\) divides both \(2x^2\) and \(4z^2\). From
\[
3y^2=4z^2-2x^2
\]
we obtain \(9\mid 3y^2\), so \(3\mid y^2\), hence \(3\mid y\). Therefore \(3\) divides \(x,y,z\), again contradicting \(\gcd(x,y,z)=1\).

We have exhibited a solution for \(n=1\) and proved that no \(n\ge 2\) has a solution. Therefore the answer is exactly \(n=1\).

## intuition
After reducing any hypothetical solution to a primitive one, parity forces all three variables to be even for n at least 3, while square residues modulo 3 force all three variables to be divisible by 3 for n=2.
