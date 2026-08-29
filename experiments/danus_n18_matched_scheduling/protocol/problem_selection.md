# N1.8 OOD Problem Selection

Status: selected before every N1.8 DANUS proof run.

The six problems were chosen only from their mathematical structure. No candidate was run, scored, replaced, or retained according to model behavior. Exact-title and exact-statement inspection found no occurrence in Baseline A, N1.5, N1.6, or N1.7.

| Problem | Proof structure | Meaningful steps | Why it is harder than the N1.6 direct set |
| --- | --- | ---: | --- |
| `vieta-jumping-square` | minimal counterexample, quadratic root swap, descent | 7 | requires a delicate positivity/bounds argument before descent |
| `hall-marriage` | necessity plus two-case induction and graph restriction | 8 | combines a global condition, a tight-set split, and a deletion case |
| `primitive-pythagorean-triples` | parity, coprime factorization, square factors, converse | 7 | requires both classification and primitiveness in both directions |
| `ceva-concurrency` | area ratios, cyclic cancellation, converse uniqueness | 6 | joins local area comparisons to a bidirectional incidence theorem |
| `monotone-subsequence` | extremal labels, two-dimensional pigeonhole, order split | 5 | requires inventing paired invariants rather than direct algebra |
| `eulerian-circuit` | maximal trail, parity closure, residual graph, splicing | 6 | combines an invariant, iterative construction, and termination |

Every target is closed, elementary or olympiad-style, naturally provable without CAS, Lean, numerical search, or external retrieval. Each plaintext reference is self-contained and was written before execution; its SHA-256 will be frozen before the references are moved outside the execution workspace.
