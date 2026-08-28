---
fact_id: e6de928dc0afc2d3
problem_id: n15_putnam_2024_b2
author: xhigh
predecessors: []
glossary_introduces:
  Q_n: the nth convex quadrilateral in the finite initial segment under consideration
  phi: the interior angle ABC
  psi: the interior angle CDA
  s: the reflection across the perpendicular bisector of AC
  theta: the sum of the interior angles at the second and fourth vertices in a representation
  u_1: the first cyclic side length in a representation of Q_n
  u_2: the second cyclic side length in a representation of Q_n
  u_3: the third cyclic side length in a representation of Q_n
  u_4: the fourth cyclic side length in a representation of Q_n
  w: the side length AB in a chosen representation
  x: the side length BC in a chosen representation
  y: the side length CD in a chosen representation
  z: the side length DA in a chosen representation
external_refs: []
---

## statement
Two convex quadrilaterals are called partners if they have three vertices in common and they can be labeled \(ABCD\) and \(ABCE\) so that \(E\) is the reflection of \(D\) across the perpendicular bisector of the diagonal \(AC\). Is there an infinite sequence of convex quadrilaterals such that each quadrilateral is a partner of its successor and no two elements of the sequence are congruent?

## proof
The answer is no. We prove the stronger assertion that among any twenty-five convex quadrilaterals in which each one is a partner of the next, two are congruent.

Throughout, the letters in the name of a convex quadrilateral are taken in cyclic order. Say that an ordered quintuple (w,x,y,z,theta) represents a convex quadrilateral ABCD when
AB=w, BC=x, CD=y, DA=z,
and theta is the sum of the interior angles at B and D.

First we prove an invariant of a partnership. Suppose convex quadrilaterals ABCD and ABCE are partners in the labeling from the statement. Let s be reflection across the perpendicular bisector of AC. This reflection interchanges A and C and sends D to E. Consequently it sends triangle ACD isometrically to triangle CAE. Therefore
CD=AE, DA=CE,
and the interior angle CDA at D equals the interior angle CEA at E. The sides AB and BC and the interior angle ABC at B are common to the two quadrilaterals. It follows that a partnership preserves the multiset of the four side lengths and preserves the sum of the interior angles at the opposite vertices B and D (with D replaced by E). The four interior angles of a convex quadrilateral sum to 2pi, so the sum at the other pair of opposite vertices is preserved as well. Thus every partnership preserves both opposite-angle sums.

We next prove a uniqueness lemma. Fix positive real numbers w,x,y,z and a real number theta. There is at most one congruence class of convex quadrilaterals represented by (w,x,y,z,theta). Indeed, suppose ABCD is represented by this quintuple. Let phi be the interior angle ABC and let psi be the interior angle CDA. Then psi=theta-phi. Since ABCD is convex, its four vertices are distinct, each side length is positive, and
0<phi<pi and 0<psi<pi.
Equivalently, phi lies in the open interval whose lower endpoint is the larger of 0 and theta-pi and whose upper endpoint is the smaller of pi and theta. The diagonal AC lies in the interior of the convex quadrilateral except for its endpoints, and it divides the quadrilateral into the nondegenerate triangles ABC and ADC. Applying the law of cosines in these triangles gives
w^2+x^2-2wx cos(phi)=AC^2=y^2+z^2-2yz cos(theta-phi).    (1)
On the admissible open interval for phi, the left-hand side of (1) is strictly increasing in phi: its derivative is 2wx sin(phi), which is positive because w,x>0 and 0<phi<pi. The right-hand side of (1) is strictly decreasing in phi: its derivative is -2yz sin(theta-phi)=-2yz sin(psi), which is negative because y,z>0 and 0<psi<pi. Hence equation (1) has at most one admissible value of phi.

For that unique possible value of phi, the side lengths w,x and their included angle phi determine the nondegenerate triangle ABC up to congruence. Likewise, y,z and their included angle psi determine the nondegenerate triangle ADC up to congruence. Equation (1) says that these triangles have the same required length for their common side AC. To form a convex quadrilateral in the cyclic order ABCD, B and D must lie in opposite open half-planes bounded by the line AC. After A and C and the side of AC containing B have been fixed, the prescribed nondegenerate triangle ADC has exactly one placement in the opposite half-plane. Thus the two triangles have a unique convex gluing up to a plane isometry. This proves the uniqueness lemma. The strict inequalities supplied by convexity also show explicitly that no collinear boundary case phi=0, phi=pi, psi=0, or psi=pi occurs; the proof remains valid when theta=pi or when some of w,x,y,z are equal.

Now let Q_0,Q_1,...,Q_24 be any twenty-five consecutive members of a sequence satisfying the partnership condition. Choose a cyclic labeling of Q_0 and let (w,x,y,z,theta) represent it. By repeated application of the invariant proved above, every Q_n for 0<=n<=24 has the same multiset of side lengths as Q_0 and has theta as one of its two opposite-angle sums. Choose a cyclic labeling of Q_n in which the second and fourth vertices are the opposite pair whose angle sum is theta. In that labeling Q_n is represented by
(u_1,u_2,u_3,u_4,theta),
where (u_1,u_2,u_3,u_4) is a permutation of (w,x,y,z). There are at most 4!=24 such ordered quadruples (and possibly fewer if some side lengths are equal). By the pigeonhole principle, two of Q_0,Q_1,...,Q_24 are represented by the same ordered quintuple. The uniqueness lemma makes those two quadrilaterals congruent.

Therefore every sequence of pairwise noncongruent convex quadrilaterals in which each quadrilateral is a partner of its successor has at most twenty-four members. In particular, no infinite sequence with the required properties exists.

## intuition
A partner move only permutes the four side lengths and preserves the two sums of opposite angles. Convexity makes a chosen cyclic side ordering and one opposite-angle sum rigid, by a strictly monotone law-of-cosines equation. Thus only finitely many congruence classes can occur.
