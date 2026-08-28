---
fact_id: b2c94a8f7de3fb3d
problem_id: n16_weighted_binomial_paths_20260828t170915z
author: xhigh4
predecessors: []
glossary_introduces:
  H: the first letter of the two-letter alphabet used in the counting proof
  T: the second letter of the two-letter alphabet used in the counting proof
  \mathcal W: the set of length-(2k+1) words over {H,T} having strictly more H occurrences than T occurrences
external_refs: []
---

## statement
Prove that for every nonnegative integer \(k\),
\[
\sum_{j=0}^{k}2^{k-j}\binom{k+j}{j}=4^k.
\]

## proof
Fix a nonnegative integer \(k\). Consider all words of length \(2k+1\) over the two-letter alphabet \(\{H,T\}\), and let \(\mathcal W\) be the set of those words that contain strictly more occurrences of \(H\) than of \(T\).

Because \(2k+1\) is odd, every word has unequal numbers of \(H\)'s and \(T\)'s. Interchanging \(H\) and \(T\) in every position is a bijection from \(\mathcal W\) to the set of words having strictly more \(T\)'s than \(H\)'s. These two sets partition all \(2^{2k+1}\) words. Consequently
\[
|\mathcal W|=\frac{2^{2k+1}}{2}=2^{2k}=4^k.
\]

We count \(\mathcal W\) a second way. Every word in \(\mathcal W\) contains at least \(k+1\) occurrences of \(H\), since its length is \(2k+1\) and it contains more \(H\)'s than \(T\)'s. For such a word, let \(j\) be the number of occurrences of \(T\) before the \((k+1)\)-st occurrence of \(H\). The word has at most \(k\) occurrences of \(T\), so \(0\le j\le k\).

Fix an integer \(j\) with \(0\le j\le k\). Before the \((k+1)\)-st \(H\), there are exactly \(k\) occurrences of \(H\) and exactly \(j\) occurrences of \(T\). Thus the first \(k+j\) positions can be chosen in \(\binom{k+j}{j}\) ways, position \(k+j+1\) is forced to be \(H\), and the remaining
\[
(2k+1)-(k+j+1)=k-j
\]
positions may be filled arbitrarily, in \(2^{k-j}\) ways. Every word obtained in this way lies in \(\mathcal W\): it already contains \(k+1\) occurrences of \(H\), and hence among its \(2k+1\) positions it contains at most \(k\) occurrences of \(T\).

The value of \(j\) is uniquely determined by a word in \(\mathcal W\), so these classes are pairwise disjoint; and the definition of \(j\) shows that they exhaust \(\mathcal W\). Therefore
\[
|\mathcal W|=\sum_{j=0}^{k}2^{k-j}\binom{k+j}{j}.
\]
Comparing this count with \(|\mathcal W|=4^k\) proves the stated identity for the arbitrary nonnegative integer \(k\).

## intuition
The summand counts majority-H words according to where their (k+1)-st H occurs; letter complementation shows that exactly half of all odd-length binary words have an H majority.
