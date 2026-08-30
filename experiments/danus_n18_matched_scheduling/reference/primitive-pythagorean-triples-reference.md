# Primitive Pythagorean triples

## Reference proof

Let (x^2+y^2=z^2) and (gcd(x,y,z)=1). The integers (x,y) cannot both be even, and they cannot both be odd because then (x^2+y^2\equiv2\pmod4), whereas a square is (0) or (1pmod4). Thus exactly one of (x,y) is even. Interchange them so that (y) is even; then (x,z) are odd.

Set

\[
r=\frac{z+x}{2},\qquad s=\frac{z-x}{2}.
\]

These are positive integers and

\[
rs=\frac{z^2-x^2}{4}=\left(\frac y2\right)^2.
\]

They are coprime. Indeed, a common divisor divides (r+s=z) and (r-s=x); but (gcd(x,z)=1), since a prime dividing both would, from (y^2=z^2-x^2), also divide (y), contrary to primitiveness.

A product of coprime positive integers is a square only when each factor is a square. Hence (r=m^2) and (s=n^2) for coprime positive integers (m>n). Adding and subtracting give

\[
z=m^2+n^2,\qquad x=m^2-n^2,
\]

and (y^2=4m^2n^2) gives (y=2mn). The coprime integers (m,n) cannot both be odd, since then (x) and (z) would be even, so they have opposite parity.

Conversely, for coprime (m>n) of opposite parity, direct expansion gives

\[
(m^2-n^2)^2+(2mn)^2=(m^2+n^2)^2.
\]

The first and third entries are odd. No odd prime can divide all three entries: if it divides (2mn), it divides (m) or (n), and then divisibility of (m^2-n^2) would force it to divide the other, contradicting (gcd(m,n)=1). The prime (2) does not divide the odd entries. Thus the resulting triple is primitive.
