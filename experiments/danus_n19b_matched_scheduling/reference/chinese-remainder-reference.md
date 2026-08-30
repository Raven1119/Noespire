# Chinese remainder theorem

## Private source

Pre-registered self-contained reconstruction of the standard Bezout construction and product-divisibility uniqueness proof. It was selected for its proof structure, not from model performance.

## Reference proof

Put \(M=m_1\cdots m_k\) and \(M_i=M/m_i\). Pairwise coprimality implies \(\gcd(M_i,m_i)=1\), so Bezout's identity supplies integers \(s_i,t_i\) with
\[
s_iM_i+t_im_i=1.
\]
In particular, \(s_iM_i\equiv1\pmod{m_i}\). If \(j\ne i\), then \(m_i\mid M_j\), and hence \(s_jM_j\equiv0\pmod{m_i}\).

Define
\[
x=\sum_{j=1}^k a_js_jM_j.
\]
Reducing this sum modulo \(m_i\), every term except the \(i\)-th vanishes, while that term is congruent to \(a_i\). Thus \(x\) satisfies all the required congruences.

For uniqueness, suppose \(x\) and \(y\) are two solutions. Then every \(m_i\) divides \(x-y\). If coprime integers \(r,s\) both divide an integer \(d\), write \(d=rc\); since \(s\mid rc\) and \(\gcd(r,s)=1\), Euclid's lemma gives \(s\mid c\), so \(rs\mid d\). Applying this observation inductively to the pairwise coprime \(m_i\) shows that their product \(M\) divides \(x-y\). Therefore \(x\equiv y\pmod M\).
