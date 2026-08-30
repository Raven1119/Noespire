# Sperner's theorem

## Private source

Pre-registered self-contained reconstruction of the maximal-chain double count. It was selected for its proof structure, not from model performance.

## Reference proof

A maximal chain in the Boolean lattice has the form
\[
\varnothing\subset\{\pi_1\}\subset\{\pi_1,\pi_2\}\subset\cdots\subset[n]
\]
for a permutation \(\pi\) of \([n]\). Hence there are \(n!\) maximal chains.

If \(A\subseteq[n]\) has size \(k\), then exactly \(k!(n-k)!\) maximal chains contain \(A\): the elements of \(A\) may appear in the first \(k\) positions in any order, and the remaining elements may appear afterward in any order.

Because \(\mathcal A\) is an antichain, a maximal chain contains at most one member of \(\mathcal A\). Double-counting pairs \((A,C)\) with \(A\in\mathcal A\) and maximal chain \(C\) containing \(A\) therefore gives
\[
\sum_{A\in\mathcal A}|A|!(n-|A|)!\le n!.
\]
After division by \(n!\),
\[
\sum_{A\in\mathcal A}\frac1{\binom n{|A|}}\le1.
\]

The binomial coefficients are largest in the middle: the ratio \(\binom n{k+1}/\binom nk=(n-k)/(k+1)\) is at least one up to the middle and at most one afterward. Thus every denominator in the last sum is at most \(\binom n{\lfloor n/2\rfloor}\), so
\[
\frac{|\mathcal A|}{\binom n{\lfloor n/2\rfloor}}\le1.
\]
Finally, all subsets of size \(\lfloor n/2\rfloor\) form an antichain of exactly that cardinality, proving sharpness.
