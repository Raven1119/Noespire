# Evaluator Reference — Weighted Binomial Paths

- Private source identity: 2020 William Lowell Putnam Competition, A2.
- Official problem: https://maa.org/wp-content/uploads/2024/10/2020Putnam_final.pdf#page=1
- Official solution: https://maa.org/wp-content/uploads/2024/10/2020-Putnam-Solutions.pdf#page=2
- Worker-visible source/title metadata: none.

## Reference proof

Consider all paths of length \(2k+1\) whose steps are either one unit right or one unit up. Exactly one of the two step types occurs at least \(k+1\) times. Swapping right and up is a bijection between the two cases, so exactly half of the \(2^{2k+1}\) paths contain at least \(k+1\) right steps. Their number is \(2^{2k}=4^k\).

Count the same paths according to the first time they reach the vertical line \(x=k+1\). If this first crossing ends at \((k+1,j)\), then before the crossing step the path reaches \((k,j)\). Its prefix contains \(k\) right steps and \(j\) up steps, in

\[
\binom{k+j}{j}
\]

possible orders. The crossing step is forced to be right. There remain

\[
2k+1-(k+j+1)=k-j
\]

unrestricted steps, giving \(2^{k-j}\) suffixes. The first-crossing height ranges from \(j=0\) through \(j=k\). Hence the same set of paths has size

\[
\sum_{j=0}^{k}2^{k-j}\binom{k+j}{j}.
\]

Equating the two counts proves the identity.
