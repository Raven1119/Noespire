# Ceva concurrency criterion

## Reference proof

Assume first that (AD,BE,CF) meet at (P). Write ([UVW]) for the area of triangle (UVW), and set

\[
\alpha=[PBC],\qquad \beta=[PCA],\qquad \gamma=[PAB].
\]

The triangles (PBD) and (PCD) have the same altitude to (BC), so

\[
\frac{BD}{DC}=\frac{[PBD]}{[PCD]}.
\]

Because (A,P,D) are collinear, comparing the two pairs of triangles with bases on line (AP) gives

\[
\frac{[PBD]}{[PCD]}=\frac{[PAB]}{[PCA]}=\frac\gamma\beta.
\]

The same argument on the other two cevians yields

\[
\frac{CE}{EA}=\frac\alpha\gamma,
\qquad
\frac{AF}{FB}=\frac\beta\alpha.
\]

Their product is (1).

Conversely, assume the displayed product in the problem equals (1). The interior cevians (AD) and (BE) meet at a point (P) inside the triangle. Let the line (CP) meet (AB) at (F'). The already proved direction applied to (D,E,F') gives

\[
\frac{BD}{DC}\frac{CE}{EA}\frac{AF'}{F'B}=1.
\]

Comparison with the assumed equality shows (AF'/F'B=AF/FB). A point in the interior of segment (AB) is uniquely determined by this positive ratio, hence (F'=F). Therefore (CF) also passes through (P), proving concurrency.
