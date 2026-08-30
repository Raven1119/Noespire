---
fact_id: f6bdc8c9ef1a7c62
problem_id: n18a_eulerian_circuit_20260830t022143z
author: high3
predecessors: []
glossary_introduces:
  G: the finite connected undirected graph in the theorem statement
  T: a nonempty trail in G with the maximum possible number of edges
  V(T): the set of vertices that occur in T
  e_i: the edge in position i of T, where i is an integer with 1 at most i at most k
  f: an edge of G assumed, for contradiction, not to occur in T
  g: an edge of G not in T and incident with a vertex of T
  k: the positive integer equal to the number of edges of T
  v_i: the vertex in position i of T, where i is an integer with 0 at most i at most k
  w: a vertex of T incident with g
  x: an endpoint of f
external_refs: []
---

## statement
Let (G) be a finite connected undirected graph with at least one edge. Suppose every vertex of (G) has even degree. Prove that (G) has a closed trail that traverses every edge exactly once.

## proof
Because G is finite, every trail has at most as many edges as G has, and there are only finitely many trails. Since G has an edge, choose a nonempty trail T having the maximum possible number of edges. Write
T=(v_0,e_1,v_1,e_2,\ldots,e_k,v_k),
where k\ge 1, every e_i has endpoints v_{i-1} and v_i, and the edges e_1,\ldots,e_k are pairwise distinct.

First T is closed. If an edge incident with v_k were absent from T, it could be appended at the end of T, yielding a trail with k+1 edges. Therefore every edge incident with v_k occurs in T. Suppose v_k\ne v_0. Orient each traversal of T from v_{i-1} to v_i solely for counting. The number of arrivals at v_k minus the number of departures from v_k is 1: every occurrence before the end pairs an arrival with a later departure, the trail does not start at v_k, and its final step arrives at v_k. Hence the total number of incidences at v_k among the edges of T is twice the number of departures plus 1, and is odd. A loop at v_k contributes one arrival and one departure, hence two incidences. Since every edge incident with v_k lies in T, this total is the degree of v_k in G, contradicting that this degree is even. Thus v_k=v_0.

It remains to show that T contains every edge of G. Assume some edge f is absent from T, and choose an endpoint x of f. If x is a vertex of T, then f itself is an edge absent from T incident with a vertex of T. If x is not a vertex of T, connectedness gives a path from x to v_0. Along this path, take the first edge whose later endpoint belongs to the vertex set V(T) of T. Its earlier endpoint does not belong to V(T), so that edge cannot occur in T; hence again there is an edge g absent from T and incident with a vertex w of T.

Because T is closed, choose an occurrence of w in T and cyclically rotate its displayed vertex-edge sequence so that it starts and ends at w. The rotated sequence is still a trail and uses exactly e_1,\ldots,e_k, because the same adjacencies are retained and these edges are pairwise distinct. Appending g produces a trail with k+1 pairwise distinct edges, contradicting the maximal choice of T. Therefore no edge is absent from T. The trail T is closed, contains every edge, and, being a trail, traverses no edge more than once; consequently it traverses every edge exactly once.

## intuition
A longest trail cannot stop at a different vertex from where it began, because parity would leave an unused exit. Once it is closed, connectedness lets any omitted edge be reached from the trail, and rotating the closed trail to that attachment point would extend it.
