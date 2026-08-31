---
fact_id: 25ce3bdb78bf40cf
problem_id: n19bc_p_group_center_20260831t051212z
author: high
predecessors: []
glossary_introduces:
  C_G(x): the centralizer of an element x in G
  C_G(x_i): the centralizer of a chosen noncentral conjugacy-class representative x_i
  G: the finite group in the theorem
  Z(G): the center of G
  [G:C_G(x)]: the number of left cosets of C_G(x) in G
  [G:C_G(x_i)]: the number of left cosets of C_G(x_i) in G
  a,b,c,g,h,x: elements of G used in the proof
  gC_G(x): the left coset of C_G(x) represented by g
  hC_G(x): the left coset of C_G(x) represented by h
  i: an index ranging over the non-singleton conjugacy classes
  m: the integer satisfying |C_G(x)|=p^m
  n: the integer with n>=1 and |G|=p^n
  p: the prime in the theorem
  x_i: a representative of a non-singleton conjugacy class
external_refs: []
---

## statement
Let \(p\) be a prime and let \(G\) be a finite group of order \(p^n\) for some integer \(n\ge 1\). Prove that the order of the center \(Z(G)\) is divisible by \(p\), and hence that \(Z(G)\) contains a nonidentity element.

## proof
Let G act on its underlying set by conjugation: for elements g and x of G, define the action of g on x to be gxg^{-1}. Its orbits are exactly the conjugacy classes. The orbit of x has one element if and only if gxg^{-1}=x for every g in G, and this is equivalent to x belonging to Z(G).

For an element x of G, define C_G(x) to be the set of all g in G such that gx=xg. The identity belongs to C_G(x). If a and b belong to C_G(x), then
(ab^{-1})x = a(b^{-1}x) = a(xb^{-1}) = (ax)b^{-1} = (xa)b^{-1} = x(ab^{-1}).
Therefore ab^{-1} belongs to C_G(x), so C_G(x) is a subgroup of G.

Consider the map from the set of left cosets of C_G(x) in G to the conjugacy class of x that sends the coset gC_G(x) to gxg^{-1}. To check that it is well-defined, suppose gC_G(x)=hC_G(x). Then g=hc for some c in C_G(x), and gxg^{-1}=h(cxc^{-1})h^{-1}=hxh^{-1}. The map is surjective by the definition of the conjugacy class. It is injective because, if gxg^{-1}=hxh^{-1}, then h^{-1}g commutes with x; hence h^{-1}g belongs to C_G(x), and therefore gC_G(x)=hC_G(x). Thus the conjugacy class of x has cardinality [G:C_G(x)].

The left cosets of C_G(x) partition G, and multiplication by a fixed coset representative is a bijection from C_G(x) to that coset. Hence
|G| = [G:C_G(x)] |C_G(x)|.
It follows that |C_G(x)| divides |G|=p^n. Every positive divisor of p^n is p^m for an integer m with 0<=m<=n, so |C_G(x)|=p^m for such an m. If x does not belong to Z(G), then some element of G fails to commute with x, so C_G(x) is a proper subgroup of G. Therefore |C_G(x)|<|G| and m<n. In that case the conjugacy class of x has cardinality
[G:C_G(x)] = p^n/p^m = p^(n-m).
Since n-m>=1, this cardinality is divisible by p.

Choose one representative x_i from each non-singleton conjugacy class; the finite list of representatives is allowed to be empty. The conjugacy classes partition G. The singleton conjugacy classes are precisely those whose elements lie in Z(G), and each such class contributes exactly one element. Therefore the sum of the cardinalities of the singleton classes is |Z(G)|, while every remaining class has cardinality [G:C_G(x_i)]. Consequently,
|G| = |Z(G)| + sum_i [G:C_G(x_i)],
where i ranges over the non-singleton classes. Every term in the sum is divisible by p. Moreover p divides |G|=p^n because n>=1. Subtracting the sum from |G| proves that p divides |Z(G)|.

The identity element lies in Z(G), so |Z(G)| is positive. Since |Z(G)| is a positive multiple of the prime p and every prime is at least 2, |Z(G)| is at least 2. Thus Z(G) contains an element distinct from the identity.

## intuition
Conjugation partitions the group into central singleton classes and noncentral classes whose sizes are nontrivial powers of p. The class equation modulo p therefore forces the center's order to be divisible by p.
