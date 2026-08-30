---
fact_id: bd8b62c2e27ad3bc
problem_id: n18a_ceva_concurrency_20260829t190022z
author: high7
predecessors: []
glossary_introduces:
  A: first vertex of the nondegenerate triangle ABC
  ABC: the nondegenerate triangle with vertices A, B, and C
  AD: the line through A and D
  AF: Euclidean length of the segment from A to F
  B: second vertex of the nondegenerate triangle ABC
  BD: Euclidean length of the segment from B to D
  BE: the line through B and E
  C: third vertex of the nondegenerate triangle ABC
  CE: Euclidean length of the segment from C to E
  CF: the line through C and F
  D: interior point of the side BC
  DC: Euclidean length of the segment from D to C
  E: interior point of the side CA
  EA: Euclidean length of the segment from E to A
  F: interior point of the side AB
  FB: Euclidean length of the segment from F to B
  P: common point of the three cevian lines, or the explicitly constructed candidate common point
  S: the positive normalizing number rs+1+r
  X: an arbitrary point of the plane used to define barycentric coordinates
  d: the real affine parameter locating D on BC
  p_A: barycentric coordinate of P at A
  p_B: barycentric coordinate of P at B
  p_C: barycentric coordinate of P at C
  r: the positive real number BD/DC
  s: the positive real number CE/EA
  t: the positive real number AF/FB
  u: a real affine parameter locating P on AD
  v: a real affine parameter locating P on BE
  w: a real affine parameter locating P on CF
  x_A: barycentric coordinate of X at A
  x_B: barycentric coordinate of X at B
  x_C: barycentric coordinate of X at C
external_refs: []
---

## statement
Let (ABC) be a nondegenerate triangle, and let (D,E,F) lie in the interiors of (BC,CA,AB), respectively. Prove that the cevians (AD,BE,CF) are concurrent if and only if

\[
\frac{BD}{DC}\cdot\frac{CE}{EA}\cdot\frac{AF}{FB}=1.
\]

## proof
Regard the points of the plane as position vectors in an affine coordinate system. Because the triangle ABC is nondegenerate, the vectors B-A and C-A are linearly independent. Consequently every point X of the plane has unique barycentric coordinates x_A,x_B,x_C satisfying
X=x_A A+x_B B+x_C C and x_A+x_B+x_C=1:
indeed, uniquely write X-A=x_B(B-A)+x_C(C-A) and then set x_A=1-x_B-x_C.

Set
r=BD/DC, s=CE/EA, and t=AF/FB.
All three numbers are positive because D,E,F are interior points of the respective sides. We first record the affine formulas
D=(B+rC)/(1+r), E=(sA+C)/(1+s), and F=(A+tB)/(1+t).
For example, because D is interior to BC, there is a unique number d with 0<d<1 and D=(1-d)B+dC. The two displacement vectors D-B=d(C-B) and C-D=(1-d)(C-B) show that BD/DC=d/(1-d)=r. Hence d=r/(1+r), which gives D=(B+rC)/(1+r). The derivations for E and F are identical after replacing (B,D,C,r) respectively by (C,E,A,s) and (A,F,B,t).

Assume first that AD, BE, and CF are concurrent at a point P, and let p_A,p_B,p_C be the barycentric coordinates of P.

Since P lies on the line AD, there is u in R such that
P=(1-u)A+uD=(1-u)A+[u/(1+r)]B+[ur/(1+r)]C.
Uniqueness of barycentric coordinates therefore gives
p_C=r p_B.                                                     (1)

Since P lies on the line BE, there is v in R such that
P=(1-v)B+vE=[vs/(1+s)]A+(1-v)B+[v/(1+s)]C.
Thus
p_A=s p_C.                                                     (2)

Since P lies on the line CF, there is w in R such that
P=(1-w)C+wF=[w/(1+t)]A+[wt/(1+t)]B+(1-w)C.
Thus
p_B=t p_A.                                                     (3)

The three barycentric coordinates are nonzero. Indeed, if p_B=0, then (1) gives p_C=0 and (2) gives p_A=0, contradicting p_A+p_B+p_C=1. Equations (1) and (2) then also show directly that p_C and p_A are nonzero. We may therefore divide the three relations to obtain
r=p_C/p_B, s=p_A/p_C, and t=p_B/p_A.
Multiplication gives rst=1, which is precisely
(BD/DC)(CE/EA)(AF/FB)=1.

Conversely, assume rst=1. Define the positive number
S=rs+1+r
and define the point
P=(rs A+B+rC)/S.
Using the three affine formulas for D,E,F, we verify each incidence explicitly. First,
P=(rs/S)A+[(1+r)/S]D.
The two displayed coefficients sum to (rs+1+r)/S=1, so P lies on the line AD. Second,
P=(1/S)B+[r(1+s)/S]E.
Again the coefficients sum to (1+r+rs)/S=1, so P lies on the line BE. Finally,
P=(r/S)C+[rs(1+t)/S]F.
Here the coefficients sum to
[r+rs(1+t)]/S=(r+rs+rst)/S=(r+rs+1)/S=1,
where rst=1 was used. Hence P lies on the line CF. Thus the three cevians are concurrent at P.

Both implications have been proved.

## intuition
Barycentric coordinates turn membership in each cevian into one ratio between two coordinates. Around the three vertices these ratios telescope in the necessary direction; when their product is one, the same equations consistently define an explicit common point.
