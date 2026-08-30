# Vandermonde determinant

## Private source

Pre-registered self-contained reconstruction of the polynomial-root induction. It was selected for its proof structure, not from model performance.

## Reference proof

Let \(D_n(x_1,\ldots,x_n)\) denote the displayed determinant. We induct on \(n\). For \(n=1\), both sides equal \(1\).

Fix \(x_1,\ldots,x_{n-1}\) and regard \(D_n\) as a polynomial in \(x_n\). Its degree is at most \(n-1\). If \(x_n=x_i\) for some \(i<n\), rows \(i\) and \(n\) coincide, so the determinant vanishes. The factor theorem consequently gives
\[
D_n=c(x_1,\ldots,x_{n-1})\prod_{i=1}^{n-1}(x_n-x_i)
\]
for a coefficient \(c\) independent of \(x_n\); the identity remains valid when some of the \(x_i\) coincide because it is a polynomial identity.

The coefficient of \(x_n^{n-1}\) in \(D_n\) comes only from the last entry of the last row. Expanding that coefficient along the last row and last column shows that it is \(D_{n-1}(x_1,\ldots,x_{n-1})\). Hence \(c=D_{n-1}\). By the induction hypothesis,
\[
c=\prod_{1\le i<j\le n-1}(x_j-x_i).
\]
Multiplying this by the new factors \(\prod_{i=1}^{n-1}(x_n-x_i)\) gives exactly \(\prod_{1\le i<j\le n}(x_j-x_i)\), completing the induction.
