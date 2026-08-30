# Vieta-jumping square quotient

## Reference proof

Write

\[
k=\frac{a^2+b^2}{ab+1},
\]

so (a^2+b^2=k(ab+1)). Suppose for contradiction that some positive pair gives a nonsquare integer (k), and choose such a pair with (a+b) minimal. Interchange (a,b) if necessary so that (a\ge b).

If (a=b), then (k=2a^2/(a^2+1)=2-2/(a^2+1)). Integrality forces (a=1) and (k=1), a square. Thus (a>b). Also (k\ne1), since (a^2-ab+b^2=(a-b)^2+ab=1) has only the positive solution (a=b=1). Hence (k\ge2).

Regard

\[
f(t)=t^2-kbt+b^2-k
\]

as a monic quadratic having (a) as one root. First, (k<b^2). Indeed, if (k\ge b^2), the equation rearranges to

\[
a(a-kb)=k-b^2\ge0.
\]

Thus (a-kb\ge0). If it were at least (1), then the left side would be at least (a\ge kb\ge k), whereas the right side is strictly less than (k), a contradiction. Hence (a=kb) and (k=b^2), again a square.

The other root is therefore

\[
a'=kb-a=\frac{b^2-k}{a},
\]

which is a positive integer. Moreover

\[
f(b)=(2-k)b^2-k<0.
\]

Since (f) is positive outside its two positive roots and (a>b) is one root, the other root satisfies (0<a'<b). Vieta's relations give

\[
b^2+(a')^2=k(ba'+1).
\]

Thus the smaller positive pair ((b,a')) gives the same nonsquare integer (k), but (b+a'<a+b), contradicting minimality. Therefore every integral value of the quotient is a perfect square.
