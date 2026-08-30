# Monotone subsequence theorem

## Reference proof

Let the distinct real numbers be (a_1,\ldots,a_{n^2+1}). For each index (i), let (I_i) be the maximum length of a strictly increasing subsequence ending at (a_i), and let (D_i) be the maximum length of a strictly decreasing subsequence ending at (a_i).

Suppose there is neither an increasing nor a decreasing subsequence of length (n+1). Then every ordered pair ((I_i,D_i)) lies in

\[
\{1,\ldots,n\}\times\{1,\ldots,n\},
\]

which contains only (n^2) pairs. By the pigeonhole principle, two indices (i<j) have ((I_i,D_i)=(I_j,D_j)).

Because the sequence entries are distinct, either (a_i<a_j) or (a_i>a_j). In the first case, appending (a_j) to a longest increasing subsequence ending at (a_i) gives (I_j\ge I_i+1), a contradiction. In the second case, the analogous decreasing extension gives (D_j\ge D_i+1), also a contradiction. Thus at least one required subsequence exists.
