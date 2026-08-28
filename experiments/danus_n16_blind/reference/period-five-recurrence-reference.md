# Evaluator Reference — Period-Five Recurrence

- Private source identity: 2022 William Lowell Putnam Competition, A3.
- Official problem: https://maa.org/wp-content/uploads/2024/10/2022_Putnam_Competitions.pdf#page=1
- Official solution: https://maa.org/wp-content/uploads/2024/10/2022-Putnam-solutions.pdf#page=3
- Worker-visible source/title metadata: none.

## Reference proof

Work in \(\mathbb F_p\). Every sequence term is nonzero. No term can equal \(-1\): if \(a_{n+1}=-1\), the recurrence would give the impossible equality \(a_na_{n+2}=0\).

Starting with \(a_1,a_2\), repeated use of the recurrence gives

\[
a_3=\frac{1+a_2}{a_1},\qquad
a_4=\frac{1+a_1+a_2}{a_1a_2},\qquad
a_5=\frac{1+a_1}{a_2}.
\]

The next two applications simplify to \(a_6=a_1\) and \(a_7=a_2\). Since any two consecutive nonzero terms uniquely determine the next term, every admissible sequence satisfies \(a_{n+5}=a_n\).

Cyclic shift by one place therefore acts on the finite set of admissible sequences. Because \(5\) is prime, every orbit has size \(1\) or \(5\). The size-one orbits are precisely the constant sequences. Thus, modulo \(5\), \(F(p)\) equals the number of constants \(c\in\mathbb F_p^*\) satisfying

\[
c^2=1+c.
\]

Equivalently, \((2c-1)^2=5\). Since \(p>5\), the element \(5\) is nonzero and has either zero or two square roots in \(\mathbb F_p\). Each resulting \(c\) is nonzero and not \(-1\), so it defines an admissible constant sequence. The fixed-point count is therefore \(0\) or \(2\), and so is \(F(p)\) modulo \(5\).
