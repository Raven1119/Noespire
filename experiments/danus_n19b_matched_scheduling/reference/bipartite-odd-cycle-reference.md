# Bipartite graphs and odd cycles

## Private source

Pre-registered self-contained reconstruction using parity of paths and the minimal odd closed-walk lemma. It was selected for its proof structure, not from model performance.

## Reference proof

First note that every odd closed walk contains an odd cycle. Indeed, choose an odd closed walk of minimum positive length. If it repeats a vertex other than its initial/final repetition, splitting at that repeated vertex produces two shorter closed walks whose lengths sum to an odd number, so one is odd, contradicting minimality. Thus the minimal walk has no internal repeated vertex and is an odd cycle.

If \(G\) is bipartite, every walk alternates between the two vertex classes. A closed walk, and in particular every cycle, must therefore have even length. Hence a bipartite graph has no odd cycle.

Conversely, suppose \(G\) has no odd cycle. The lemma implies that it has no odd closed walk. Work in one connected component and choose a root \(r\). For each vertex \(v\), choose a path from \(r\) to \(v\) and color \(v\) according to the parity of that path's length. This parity is well-defined: if two paths from \(r\) to \(v\) had opposite parity, traversing one and then the reverse of the other would give an odd closed walk.

The endpoints of every edge receive opposite colors. Otherwise, paths from \(r\) to the two endpoints having the same parity, followed by the edge and the reverse of one path, would form an odd closed walk. Thus the two color classes give a bipartition of the component. Repeating independently for every component proves that \(G\) is bipartite.
