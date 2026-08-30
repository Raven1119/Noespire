---
fact_id: ccfb91a39c3bee00
problem_id: n18a_ceva_concurrency_20260829t190022z
author: high4
predecessors: []
glossary_introduces:
  A: first vertex of the nondegenerate triangle ABC
  ABC: the nondegenerate triangle with vertices A, B, and C
  AD: the line through A and D
  B: second vertex of the nondegenerate triangle ABC
  BE: the line through B and E
  C: third vertex of the nondegenerate triangle ABC
  CF: the line through C and F
  D: interior point of side BC
  E: interior point of side CA
  F: interior point of side AB
  N: the positive normalization constant ed+1+d
  P: the proposed or assumed common point of the three cevians
  X: an arbitrary point in the plane of triangle ABC
  d: the positive ratio BD/DC
  e: the positive ratio CE/EA
  f: the positive ratio AF/FB
  s: a real affine-line parameter
  x: first normalized affine barycentric coordinate relative to ABC
  y: second normalized affine barycentric coordinate relative to ABC
  z: third normalized affine barycentric coordinate relative to ABC
external_refs: []
---

## statement
Let (ABC) be a nondegenerate triangle, and let (D,E,F) lie in the interiors of (BC,CA,AB), respectively. Prove that the cevians (AD,BE,CF) are concurrent if and only if

\[
\frac{BD}{DC}\cdot\frac{CE}{EA}\cdot\frac{AF}{FB}=1.
\]

## proof
All segment lengths occurring below are ordinary positive Euclidean lengths. Since (D,E,F) are interior points of their respective sides, the six lengths (BD,DC,CE,EA,AF,FB) are positive.

We first define the coordinate system used in the proof. Because (ABC) is nondegenerate, the vectors (B-A) and (C-A) are linearly independent. Hence each point (X) in the plane has unique real numbers (y,z) such that
[
X=A+y(B-A)+z(C-A).
]
Writing (x=1-y-z), this is equivalently
[
X=xA+yB+zC,qquad x+y+z=1.
]
We call ((x,y,z)) the normalized affine barycentric coordinates of (X) relative to (ABC). In particular,
[
A=(1,0,0),qquad B=(0,1,0),qquad C=(0,0,1).
]

Since (D) lies between (B) and (C), (BC=BD+DC), and the section formula obtained by writing (D=B+(BD/BC)(C-B)) gives
[
D=left(0,rac{DC}{BD+DC},rac{BD}{BD+DC}ight).
]
A point of the line (AD) has the form (A+s(D-A)) for some real (s). Its coordinates therefore satisfy (DC,z=BD,y). Conversely, if normalized coordinates ((x,y,z)) satisfy (DC,z=BD,y), set
[
s=rac{BD+DC}{DC},y.
]
Then (y=sDC/(BD+DC)), the displayed equation gives (z=sBD/(BD+DC)), and (x=1-y-z=1-s); thus the point equals (A+s(D-A)). Therefore
[
Xin ADquadLongleftrightarrowquad DC,z=BD,y. 	ag{1}
]

Similarly, because (E) lies between (C) and (A),
[
E=left(rac{CE}{CE+EA},0,rac{EA}{CE+EA}ight).
]
For a point (X=B+s(E-B)), its coordinates satisfy (EA,x=CE,z). Conversely, if normalized coordinates satisfy (EA,x=CE,z), then with
[
s=rac{CE+EA}{CE},x
]
one has (x=sCE/(CE+EA)), (z=sEA/(CE+EA)), and (y=1-s), so (X=B+s(E-B)). Consequently
[
Xin BEquadLongleftrightarrowquad EA,x=CE,z. 	ag{2}
]

Because (F) lies between (A) and (B),
[
F=left(rac{FB}{AF+FB},rac{AF}{AF+FB},0ight).
]
For a point (X=C+s(F-C)), its coordinates satisfy (FB,y=AF,x). Conversely, if normalized coordinates satisfy (FB,y=AF,x), then with
[
s=rac{AF+FB}{FB},x
]
one has (x=sFB/(AF+FB)), (y=sAF/(AF+FB)), and (z=1-s), so (X=C+s(F-C)). Hence
[
Xin CFquadLongleftrightarrowquad FB,y=AF,x. 	ag{3}
]

Assume first that (AD,BE,CF) are concurrent at a point (P), and write the normalized coordinates of (P) as ((x,y,z)). By (1)--(3),
[
DC,z=BD,y,qquad EA,x=CE,z,qquad FB,y=AF,x. 	ag{4}
]
If (x=0), then the second equation in (4), together with (CE>0), gives (z=0), and the third equation, together with (FB>0), gives (y=0). This contradicts (x+y+z=1). Thus (x
e0). The second and third equations in (4), with all segment lengths positive, then imply (z
e0) and (y
e0). Division in (4) is therefore valid and yields
[
rac{z}{y}=rac{BD}{DC},qquad
rac{x}{z}=rac{CE}{EA},qquad
rac{y}{x}=rac{AF}{FB}.
]
Multiplying these three equalities, the left-hand side is ((z/y)(x/z)(y/x)=1), proving
[
rac{BD}{DC}rac{CE}{EA}rac{AF}{FB}=1.
]

Conversely, assume
[
rac{BD}{DC}rac{CE}{EA}rac{AF}{FB}=1.
]
Define the positive real numbers
[
d=rac{BD}{DC},qquad e=rac{CE}{EA},qquad f=rac{AF}{FB}.
]
Then (def=1). Let (N=ed+1+d>0), and let (P) be the unique point with normalized affine barycentric coordinates
[
(x,y,z)=left(rac{ed}{N},rac1N,rac dNight).
]
These three coordinates sum to (1), so the point exists by the coordinate construction above. They satisfy
[
z=dy,qquad x=ez,qquad y=fx,
]
where the last equality follows from (fed=1). Replacing (d,e,f) by their definitions shows
[
DC,z=BD,y,qquad EA,x=CE,z,qquad FB,y=AF,x.
]
By (1), (2), and (3), respectively, (Pin AD), (Pin BE), and (Pin CF). Thus the three cevians are concurrent at (P). This proves both implications.

## intuition
In affine barycentric coordinates, each cevian fixes one ratio of two coordinates. The three cyclic ratio equations are compatible exactly when their product is one.
