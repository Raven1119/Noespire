# Eulerian circuit by trail splicing

## Reference proof

Start at any vertex incident to an edge and extend a trail without repeating edges until no extension is possible. Finiteness ensures that this process stops. Its endpoint must be its starting point: if it ended at a different vertex (w), the trail would have used an odd number of edges incident to (w), whereas the total degree of (w) is even. At least one unused incident edge would remain, contradicting maximality. Thus the trail is closed; call it (C).

If (C) contains every edge, the proof is complete. Otherwise some vertex of (C) is incident to an unused edge. To see this, use connectedness to take a path from an endpoint of an unused edge to (C), and consider the first edge of that path entering (C); unless an unused edge already has both endpoints on (C), this entering edge is unused and has an endpoint on (C).

Remove the edges of (C). At every vertex, (C) used an even number of incident edges, so all degrees in the remaining graph are still even. Starting at a vertex of (C) incident to a remaining edge, the same maximal-trail argument produces another closed trail (C') made entirely of unused edges.

Splice (C') into (C) at their common starting vertex. The result is a closed trail using exactly the union of their edge sets. If edges still remain, repeat the construction. Each repetition consumes at least one new edge, so finiteness makes the process terminate with a closed trail traversing every edge exactly once.
