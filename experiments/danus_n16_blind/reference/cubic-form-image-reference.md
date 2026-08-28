# Evaluator Reference — Cubic Form Image

- Private source identity: 2019 William Lowell Putnam Competition, A1.
- Official problem: https://maa.org/wp-content/uploads/2024/10/2019PutnamProblems.pdf#page=1
- Official solution: https://maa.org/wp-content/uploads/2025/02/2019-Putnam-Problem-Solutions.pdf#page=1
- Worker-visible source/title metadata: none.

## Reference proof

Write \(f(a,b,c)=a^3+b^3+c^3-3abc\). The following substitutions cover every allowed residue class:

\[
f(t,t,t+1)=3t+1,\qquad
f(t,t,t-1)=3t-1,\qquad
f(t,t+1,t-1)=9t.
\]

Here \(t\ge 0\) in the first formula, \(t\ge1\) in the second and third, and \(f(0,0,0)=0\). Thus every nonnegative integer not divisible by \(3\), and every nonnegative multiple of \(9\), is represented by nonnegative integers.

For the converse, use

\[
f(a,b,c)=(a+b+c)(a^2+b^2+c^2-ab-bc-ca).
\]

This form is nonnegative for nonnegative real inputs because the second factor is

\[
\frac12\big((a-b)^2+(b-c)^2+(c-a)^2\big).
\]

Also cubes are congruent to their bases modulo \(3\). Hence \(3\mid f(a,b,c)\) implies \(3\mid a+b+c\). The identity

\[
a^2+b^2+c^2-ab-bc-ca=(a+b+c)^2-3(ab+bc+ca)
\]

then shows that the second factor is also divisible by \(3\). Therefore every represented multiple of \(3\) is divisible by \(9\), proving the characterization.
