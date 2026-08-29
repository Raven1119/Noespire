---
fact_id: cf1aab0a3dd0ee13
problem_id: n17b_reflection_fixed_vector_20260829t155918z
author: high
predecessors: []
glossary_introduces:
  A: the inverse matrix (I-Q)^{-1}
  H: the matrix I-2uu^{\mathsf T}
  I: the n by n identity matrix
  Q: the given real n by n orthogonal matrix
  \mathsf T: matrix or vector transpose
  n: the positive integer dimension of the real vector space
  u: the given unit vector in real n-dimensional space
  v: a vector used in the fixed-vector hypothesis
  w: the constructed nonzero fixed vector of HQ
external_refs: []
---

## statement
Let \(Q\) be a real \(n\times n\) orthogonal matrix, and let \(u\in\mathbb R^n\) satisfy \(u^{\mathsf T}u=1\). Define
\[
H=I-2uu^{\mathsf T}.
\]
Assume there is no nonzero vector \(v\) with \(Qv=v\). Prove that there is a nonzero vector \(w\) with \(HQw=w\).

## proof
Because there is no nonzero vector \(v\) satisfying \(Qv=v\), the nullspace of \(I-Q\) is \(\{0\}\). Since \(I-Q\) is an \(n\times n\) real matrix, it is therefore invertible. Define
\[
A=(I-Q)^{-1}.
\]
Orthogonality of \(Q\) gives \(Q^{\mathsf T}Q=I\), so \(Q^{\mathsf T}=Q^{-1}\). We compute
\[
I-Q^{\mathsf T}=-Q^{\mathsf T}(I-Q).
\]
Taking inverses of both sides yields
\[
A^{\mathsf T}
 =\bigl((I-Q)^{-1}\bigr)^{\mathsf T}
 =(I-Q^{\mathsf T})^{-1}
 =-\,(I-Q)^{-1}(Q^{\mathsf T})^{-1}
 =-AQ.
\]
On the other hand, \(A(I-Q)=I\), and hence \(A-AQ=I\). Therefore
\[
A^{\mathsf T}=-AQ=I-A,
\qquad\text{so}\qquad
A+A^{\mathsf T}=I.
\]
The scalar \(u^{\mathsf T}Au\) equals its transpose \(u^{\mathsf T}A^{\mathsf T}u\). Consequently,
\[
2u^{\mathsf T}Au
 =u^{\mathsf T}(A+A^{\mathsf T})u
 =u^{\mathsf T}u
 =1,
\]
and thus \(u^{\mathsf T}Au=\frac12\).

Now set \(w=Au\). Since \(u^{\mathsf T}u=1\), the vector \(u\) is nonzero; since \(A\) is invertible, \(w\) is nonzero. The identity \((I-Q)w=u\) gives
\[
Qw=w-u.
\]
It follows that
\[
u^{\mathsf T}Qw=u^{\mathsf T}w-u^{\mathsf T}u
=u^{\mathsf T}Au-1
=-\frac12.
\]
Using \(H=I-2uu^{\mathsf T}\), we finally obtain
\[
HQw=(I-2uu^{\mathsf T})Qw
=Qw-2u(u^{\mathsf T}Qw)
=Qw+u
=w.
\]
Thus the nonzero vector \(w=Au\) satisfies \(HQw=w\), as required.

## intuition
The inverse resolvent A=(I-Q)^{-1} has symmetric part I/2 for an orthogonal Q without fixed vectors. Thus w=Au has exactly the inner product needed for the reflection H to restore the displacement Qw-w=-u.
