# N1.9b Fresh OOD Problem Selection

Status: selected before every N1.9b DANUS mathematical run.

The six targets were chosen only from mathematical structure. No candidate was piloted, scored, replaced, or retained according to DANUS behavior. Exact statements and subjects were checked against Baseline A and N1.5 through N1.8.

| Problem | Proof structure | Meaningful steps | Structural rationale |
| --- | --- | ---: | --- |
| `ramsey-r33` | degree pigeonhole, triangle dichotomy, complementary-cycle construction | 5 | requires both a universal upper bound and an explicit sharp lower construction |
| `chinese-remainder` | pairwise coprimality, Bezout coefficients, simultaneous construction, uniqueness | 6 | coordinates several local congruences and proves a global uniqueness modulus |
| `sperner-antichain` | maximal-chain encoding, double count, LYM bound, sharp middle layer | 6 | requires a non-obvious weighted invariant and an extremal equality construction |
| `vandermonde-determinant` | polynomial viewpoint, forced roots, leading coefficient, induction | 5 | changes representation from determinant expansion to polynomial factorization |
| `p-group-center` | conjugation action, orbit-stabilizer, class partition, modular count | 5 | combines group action structure with divisibility rather than direct manipulation |
| `bipartite-odd-cycle` | minimal odd-walk lemma, path parity, well-defined coloring, converse | 6 | requires resolving path-choice ambiguity before constructing the bipartition |

Every target is a closed theorem with a self-contained private reference, naturally checkable in prose, and needs no Lean, CAS, numerical search, or external retrieval. The set is heterogeneous and was frozen in full before the first proof run.

For every problem, `protocol/runtime_manifest.json` freezes the exact statement hash, reference-proof hash, and the corresponding source path under the root-only private reference store. Those sources are moved out of the worker-visible workspace only after this pre-registration is committed.
