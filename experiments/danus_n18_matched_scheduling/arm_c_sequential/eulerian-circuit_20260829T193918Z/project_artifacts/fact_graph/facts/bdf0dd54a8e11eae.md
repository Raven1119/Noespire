---
fact_id: bdf0dd54a8e11eae
problem_id: n18c_eulerian_circuit_20260829t193918z
author: high
predecessors: []
glossary_introduces:
  G: the finite connected undirected graph in the theorem
  H: a connected component containing an edge in the residual graph obtained by deleting the edges of T
  T: a closed trail in G with the largest possible number of edges
  U: a nonempty closed trail in H based at v
  s: the initial vertex of the first greedily constructed trail
  t: the terminal vertex of the first greedily constructed trail
  v: a vertex common to H and T
  x: a vertex of H incident with a residual edge
  y: the first vertex on a chosen path from x that lies on T
  z: the vertex immediately preceding y on that path
external_refs: []
---

## statement
Let (G) be a finite connected undirected graph with at least one edge. Suppose every vertex of (G) has even degree. Prove that (G) has a closed trail that traverses every edge exactly once.

## proof
A trail is represented by a sequence of vertices and pairwise distinct edges in which each edge joins the vertices immediately before and after it. When counting incidences at a vertex, a loop (if loops are allowed) is counted twice, as it is in the degree.

First we show that G contains at least one nonempty closed trail. Choose a vertex incident with an edge; such a vertex exists because G has at least one edge. Starting there, successively append an edge incident with the current terminal vertex that has not previously appeared in the trail, and stop when no such edge exists. The process stops because G has finitely many edges. Let the initial vertex be s and the terminal vertex be t. If t is different from s, then among the edges of the trail the number of incidences at t is odd: every departure from t is paired with an arrival at t, except for the final arrival, which is unpaired. The degree of t in G is even, so the number of incidences at t belonging to edges not in the trail is odd and hence positive. Consequently there is an unused edge incident with t, contradicting the stopping rule. Therefore t equals s, and the constructed nonempty trail is closed.

Among all closed trails in G, choose one T having the largest possible number of edges. Such a choice exists because at least one closed trail exists and every trail uses each of the finitely many edges at most once. Suppose, for a contradiction, that T does not use every edge. Form the residual graph by retaining all vertices of G and deleting exactly the edges used by T. At every vertex, T uses an even number of incidences: during a cyclic traversal of T, each arrival at that vertex is paired with a departure. Since every degree in G is even, every degree in the residual graph is therefore even.

Let H be a connected component of the residual graph that contains an edge. We claim that H contains a vertex of T. Choose a vertex x of H incident with a residual edge. Because G is connected, there is a path in G from x to a vertex of T. If x itself is a vertex of T, the claim holds. Otherwise, on such a path let y be the first vertex that lies on T, and let z be the vertex immediately preceding y. Then z does not lie on T. The edge joining z to y cannot be an edge used by T, because both endpoints of every edge used by T are vertices of T. Thus that edge remains in the residual graph. The same reasoning applies to every preceding edge of the chosen path before its first vertex on T, so the residual graph contains a path from x to y. Hence y belongs to H, proving the claim.

Choose a common vertex v of H and T. Since H contains an edge and is connected, v is incident with a residual edge: if H has more than one vertex this follows from connectedness, and if H consists of one vertex its edge is a loop incident with v. Within H, start at v, traverse an unused edge, and continue appending unused edges at the current terminal vertex until this is impossible. This terminates because H is finite. The same incidence-parity argument used earlier shows that the terminal vertex must be v; if it were another vertex, its even degree in H would leave an unused incident edge. We have therefore obtained a nonempty closed trail U in H based at v.

Traverse T from v back to v, but first traverse U from v back to v and then continue along T. The edges of U are residual edges and hence none is an edge of T. Both U and T are trails, so this spliced closed walk repeats no edge and is therefore a closed trail. It contains strictly more edges than T because U is nonempty. This contradicts the maximal choice of T. Thus T uses every edge of G. Since T is a trail, it traverses every edge exactly once, and since it is closed, it is the required closed trail.

## intuition
Build a closed trail greedily using parity, choose one of maximum length, and show any remaining edge lies in an even-degree residual component attached to the trail; a residual closed trail can then be spliced in, contradicting maximality.
