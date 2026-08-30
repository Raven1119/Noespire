# Hall's marriage theorem

## Reference proof

If a matching saturates (X), then the distinct matched partners of the vertices of any (S\subseteq X) all lie in (N(S)). Hence (|N(S)|\ge|S|), proving necessity.

For sufficiency, assume Hall's inequalities and induct on (|X|). The cases (|X|=0) and (|X|=1) are immediate. Suppose (|X|>1).

First assume there is a nonempty proper subset (S\subset X) with (|N(S)|=|S|). The induced bipartite graph on (S\sqcup N(S)) satisfies Hall's condition, so induction gives a matching saturating (S). Consider the bipartite graph on

\[
(X\setminus S)\sqcup(Y\setminus N(S)).
\]

For (T\subseteq X\setminus S), Hall's condition applied to (S\cup T) gives

\[
|S|+|T|\le |N(S\cup T)|\le |N(S)|+|N(T)\setminus N(S)|.
\]

Since (|N(S)|=|S|), the neighbors of (T) remaining in (Y\setminus N(S)) number at least (|T|). Induction supplies a matching saturating (X\setminus S) there. The two matchings use disjoint vertex sets, so their union saturates (X).

It remains to consider the case in which every nonempty proper (S\subset X) satisfies the strict inequality (|N(S)|\ge|S|+1). Choose any (x\in X). Hall's condition gives a neighbor (y\in Y). Delete (x) and (y). For every nonempty (T\subseteq X\setminus\{x\}), the strict inequality in the original graph gives at least (|T|+1) neighbors, so deleting (y) leaves at least (|T|). The empty set is harmless. Thus the smaller graph satisfies Hall's condition and has, by induction, a matching saturating (X\setminus\{x\}). Adding the edge (xy) produces a matching saturating all of (X).
