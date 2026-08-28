# Fresh review packet: B1 high-cost direct attempts

Review only the evidence in this packet. Do not inspect the repository or infer a desired experimental result.

## Original theorem

Consider an \(m\)-by-\(n\) grid of unit squares. There are \((m-1)(n-1)\) coins, initially in the squares \((i,j)\) with \(1\le i\le m-1\) and \(1\le j\le n-1\). A coin at \((i,j)\) may slide to \((i+1,j+1)\) when the other three squares in that \(2\)-by-\(2\) block are unoccupied. How many distinct configurations are reachable?

## Local available premises

None declared by any submitted target fact.

## Worker attempts and verifier results

Seven workers independently submitted the full target with no predecessors. All seven submissions passed verification. Their reliable total token usages and durations were:

| Worker | Tokens | Seconds | Result |
| --- | ---: | ---: | --- |
| high | 88,944 | 530.432 | PASS |
| high2 | 83,439 | 415.442 | PASS |
| high3 | 84,201 | 475.525 | PASS |
| xhigh | 100,198 | 527.865 | PASS |
| xhigh2 | 193,422 | 577.702 | PASS |
| xhigh3 | 145,830 | 743.085 | PASS |
| xhigh4 | 135,253 | 467.712 | PASS |

The seven statements are exact repeats. The mechanically selected supporting closure contains one of the seven accepted target facts and no intermediate facts. No verifier rejection occurred.

## Actual high-cost worker attempt

The following excerpts are copied from `xhigh2`'s accepted no-predecessor Fact `e4b6fc8fdb25987f` (193,422 tokens):

> The answer is binom(m+n-2,m-1). Define a D-step to be the change (r,c) to (r+1,c), and define an L-step to be the change (r,c) to (r,c-1). A monotone path from (1,n) to (m,1) made from these steps has exactly m-1 D-steps and n-1 L-steps.
>
> We prove by induction on the number of moves that in every reachable configuration the unoccupied squares are the vertex set of a monotone D,L-path from (1,n) to (m,1). [...] The move makes (i+1,j+1) occupied and (i,j) unoccupied. Hence it replaces the consecutive path segment whose word is DL by one whose word is LD, and leaves every other path vertex unchanged.
>
> Conversely, suppose that the unoccupied squares are the vertices of a monotone path and that its word has an adjacent DL. [...] The other three squares in the two-by-two block are unoccupied, so sliding this coin to (i+1,j+1) is legal. It changes the path word by the adjacent replacement DL to LD.
>
> We next prove that every word consisting of m-1 copies of D and n-1 copies of L can be obtained from D^(m-1)L^(n-1) by replacements DL to LD. [...] Each path word has m+n-2 letters, and choosing the m-1 positions occupied by D uniquely determines the word.

The verifier accepted this Fact. Its `predecessors` field is empty and its `external_refs` field is empty.

## Necessary local trace

At least two workers explicitly reported finding or consulting the official solution. One described a lattice-path representation of the empty squares and local swaps; another said an official solution confirmed its mechanism. Thus the trace cannot establish that all successful routes were independently discovered.

Token count alone is not evidence of a wide proof gap.

## Required output

Return exactly this YAML shape:

```yaml
classification: DIRECTLY_SOLVABLE | SEARCH_FAILED | TOO_WIDE | MISSING_LEMMA | BAD_DEPENDENCY | COUNTEREXAMPLE | MALFORMED_CLAIM | STRATEGY_WASTE | UNKNOWN
confidence: LOW | MEDIUM | HIGH
evidence: >-
  ...
possible_intermediate_structure: >-
  ...
```
