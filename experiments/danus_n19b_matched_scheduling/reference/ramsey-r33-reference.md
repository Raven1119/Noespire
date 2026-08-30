# The Ramsey number R(3,3)

## Private source

Pre-registered self-contained reconstruction of the standard degree-pigeonhole upper bound and complementary five-cycle lower bound. It was selected for its proof structure, not from model performance.

## Reference proof

Consider any red-blue coloring of the edges of \(K_6\), and choose a vertex \(v\). Among the five edges incident with \(v\), at least three have the same color. Relabeling the colors if necessary, suppose \(va,vb,vc\) are red. If one of \(ab,bc,ca\) is red, that edge together with \(v\) gives a red triangle. If none is red, all three are blue, so \(abc\) is a blue triangle. Thus every coloring of \(K_6\) has a monochromatic triangle.

For the lower bound, label the vertices of \(K_5\) cyclically. Color the five edges of the cycle red and the remaining five edges blue. The red graph is a five-cycle and therefore has no triangle. The blue graph is the complement of that five-cycle, which is itself a five-cycle (its cyclic order may be taken by stepping two positions at a time), so it also has no triangle. Hence \(K_5\) admits a coloring with no monochromatic triangle. Combining the two bounds gives \(R(3,3)=6\).
