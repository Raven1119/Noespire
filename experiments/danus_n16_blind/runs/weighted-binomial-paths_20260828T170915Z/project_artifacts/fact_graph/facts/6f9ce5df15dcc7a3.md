---
fact_id: 6f9ce5df15dcc7a3
problem_id: n16_weighted_binomial_paths_20260828t170915z
author: xhigh
predecessors: []
glossary_introduces:
  A_j: For fixed k and 0<=j<=k, the set of binary words of length 2k+1 whose (k+1)-st zero occurs at position k+j+1.
  O_k: The set of binary words of length 2k+1 containing at least k+1 ones.
  Z_k: The set of binary words of length 2k+1 containing at least k+1 zeros.
  binary word: A finite sequence all of whose entries are either 0 or 1.
external_refs: []
---

## statement
Prove that for every nonnegative integer \(k\),
\[
\sum_{j=0}^{k}2^{k-j}\binom{k+j}{j}=4^k.
\]

## proof
Fix an arbitrary nonnegative integer \(k\). A binary word of length \(2k+1\) is a sequence of \(2k+1\) entries, each equal to \(0\) or \(1\). For each integer \(j\) satisfying \(0\le j\le k\), let \(A_j\) be the set of binary words of length \(2k+1\) in which the \((k+1)\)-st occurrence of \(0\) is in position \(k+j+1\).

To construct a word in \(A_j\), its first \(k+j\) positions must contain exactly \(k\) zeros and \(j\) ones. The positions of the \(j\) ones among these \(k+j\) positions can be selected in \(\binom{k+j}{j}\) ways. Position \(k+j+1\) must then be \(0\). The number of positions remaining after that forced zero is
\[
(2k+1)-(k+j+1)=k-j,
\]
and each remaining position can independently be \(0\) or \(1\). Consequently,
\[
|A_j|=\binom{k+j}{j}2^{k-j}.
\]

The sets \(A_0,A_1,\ldots,A_k\) are pairwise disjoint because the position of the \((k+1)\)-st zero is unique. Their union is exactly the set \(Z_k\) of length-\((2k+1)\) binary words containing at least \(k+1\) zeros. Indeed, every word in any \(A_j\) contains at least \(k+1\) zeros. Conversely, let a word in \(Z_k\) have its \((k+1)\)-st zero in position \(m\). The first \(m-1\) positions then contain exactly \(k\) zeros. If \(j\) is the number of ones among these positions, then \(m-1=k+j\), so \(m=k+j+1\). We have \(j\ge0\), and the whole word has at most \(k\) ones because it has length \(2k+1\) and at least \(k+1\) zeros; hence \(j\le k\). Thus the word belongs to \(A_j\) for a unique \(j\in\{0,1,\ldots,k\}\). It follows that
\[
|Z_k|=\sum_{j=0}^{k}|A_j|=\sum_{j=0}^{k}2^{k-j}\binom{k+j}{j}.
\]

Let \(O_k\) be the set of length-\((2k+1)\) binary words containing at least \(k+1\) ones. Every length-\((2k+1)\) binary word belongs to exactly one of \(Z_k\) and \(O_k\): among \(2k+1\) entries, either zeros occur at least \(k+1\) times or ones occur at least \(k+1\) times, and both alternatives cannot occur simultaneously. Replacing every zero by one and every one by zero is a bijection from \(Z_k\) to \(O_k\). There are \(2^{2k+1}\) binary words of length \(2k+1\), so
\[
2|Z_k|=2^{2k+1},\qquad |Z_k|=2^{2k}=4^k.
\]
Combining the two displayed formulas for \(|Z_k|\) proves the claimed identity.

The boundary case \(k=0\) is included: the sum has the single term \(2^0\binom00=1\), while \(4^0=1\); in the counting argument, \(Z_0\) consists only of the one-letter word \(0\). Since \(k\) was arbitrary, the identity holds for every nonnegative integer \(k\).

## intuition
Count odd-length binary words having a strict zero majority by the position of their (k+1)-st zero. Complementation shows exactly half of all such words have a zero majority.
