# Evaluator Reference — Reflection Fixed Vector

- Private source identity: 2019 William Lowell Putnam Competition, B3.
- Official problem: https://maa.org/wp-content/uploads/2024/10/2019PutnamProblems.pdf#page=2
- Official solution: https://maa.org/wp-content/uploads/2025/02/2019-Putnam-Problem-Solutions.pdf#page=9
- Worker-visible source/title metadata: none.

## Reference proof

The matrix \(H=I-2uu^{\mathsf T}\) sends \(u\) to \(-u\) and fixes every vector perpendicular to \(u\). Thus \(H\) is orthogonal and \(\det H=-1\), so \(HQ\) is orthogonal and

\[
\det(HQ)=-\det Q.
\]

We use a parity lemma. If a real orthogonal \(n\times n\) matrix \(A\) has no eigenvalue \(1\), then \(\det A=(-1)^n\). Indeed, every nonreal eigenvalue has modulus one and occurs with its conjugate, so each nonreal pair contributes product \(1\) and two dimensions. The remaining real eigenvalues of an orthogonal matrix are \(\pm1\); under the hypothesis they are all \(-1\). The number of such real eigenvalues has the same parity as \(n\), which gives the determinant formula.

Apply the lemma to \(Q\). The hypothesis that \(Qv=v\) has no nonzero solution says that \(Q\) has no eigenvalue \(1\), hence \(\det Q=(-1)^n\). Consequently

\[
\det(HQ)=(-1)^{n+1}.
\]

If \(HQ\) had no eigenvalue \(1\), the lemma would instead force \(\det(HQ)=(-1)^n\), a contradiction. Therefore \(HQ\) has eigenvalue \(1\), and a corresponding nonzero eigenvector \(w\) satisfies \(HQw=w\).
