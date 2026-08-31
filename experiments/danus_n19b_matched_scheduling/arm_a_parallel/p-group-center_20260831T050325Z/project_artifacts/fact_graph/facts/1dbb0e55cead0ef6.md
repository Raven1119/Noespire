---
fact_id: 1dbb0e55cead0ef6
problem_id: n19ba_p_group_center_20260831t050325z
author: high6
predecessors: []
glossary_introduces:
  C_G(x): the centralizer of x in G
  Cl_G(x): the conjugacy class of x in G
  G: the finite group in the theorem
  K_i: the i-th conjugacy class of G having more than one element
  Phi_x: the map from left cosets of C_G(x) to the conjugacy class of x
  Z(G): the center of G, namely the set of elements commuting with every element of G
  e: the identity element of G
  r: the number of conjugacy classes of G having more than one element
external_refs: []
---

## statement
Let \(p\) be a prime and let \(G\) be a finite group of order \(p^n\) for some integer \(n\ge 1\). Prove that the order of the center \(Z(G)\) is divisible by \(p\), and hence that \(Z(G)\) contains a nonidentity element.

## proof
Let \(e\) denote the identity element of \(G\). For each \(x\in G\), define
\[
C_G(x)=\{c\in G:cx=xc\}
\quad\text{and}\quad
\operatorname{Cl}_G(x)=\{gxg^{-1}:g\in G\}.
\]
The set \(C_G(x)\) is a subgroup of \(G\): it contains \(e\); if \(a,b\in C_G(x)\), then
\[
(ab^{-1})x=a(b^{-1}x)=a(xb^{-1})=(ax)b^{-1}=(xa)b^{-1}=x(ab^{-1}).
\]

Consider the left cosets of \(C_G(x)\) in \(G\). Define
\[
\Phi_x(gC_G(x))=gxg^{-1}.
\]
This map is well-defined and injective. Indeed, if \(gC_G(x)=hC_G(x)\), then \(h^{-1}g\in C_G(x)\), so
\[
h^{-1}gxg^{-1}h=x,
\]
which is equivalent to \(gxg^{-1}=hxh^{-1}\). Conversely, if \(gxg^{-1}=hxh^{-1}\), then
\[
(h^{-1}g)x(h^{-1}g)^{-1}=x,
\]
so \(h^{-1}g\in C_G(x)\), and hence \(gC_G(x)=hC_G(x)\). The map is surjective onto \(\operatorname{Cl}_G(x)\) by the definition of that set. Therefore
\[
|\operatorname{Cl}_G(x)|=[G:C_G(x)].
\]

The left cosets of \(C_G(x)\) partition \(G\), and every such coset has \(|C_G(x)|\) elements. Hence
\[
|G|=[G:C_G(x)]\,|C_G(x)|.
\]
Thus \(|C_G(x)|\) is a positive divisor of \(p^n\). Since \(p\) is prime, there is an integer \(m\) with \(0\le m\le n\) such that \(|C_G(x)|=p^m\). Consequently
\[
|\operatorname{Cl}_G(x)|=p^{n-m}.
\]

If \(x\notin Z(G)\), then \(C_G(x)\ne G\), because \(C_G(x)=G\) would mean that \(x\) commutes with every element of \(G\). Thus \(C_G(x)\) is proper, its index is greater than \(1\), and therefore \(n-m\ge 1\). It follows that \(|\operatorname{Cl}_G(x)|=p^{n-m}\) is divisible by \(p\).

Also, \(\operatorname{Cl}_G(x)\) has one element if and only if \(gxg^{-1}=x\) for every \(g\in G\), which is equivalent to \(x\in Z(G)\). Since conjugacy classes partition the finite set \(G\), let \(K_1,\ldots,K_r\) be all conjugacy classes having more than one element; these are precisely the classes of noncentral elements. (If there are none, take \(r=0\) and the following sum to be empty.) The class equation is therefore
\[
|G|=|Z(G)|+\sum_{i=1}^{r}|K_i|.
\]
Each \(|K_i|\) is divisible by \(p\), as proved in the preceding paragraph. Moreover, \(|G|=p^n\) is divisible by \(p\) because \(n\ge 1\). Rearranging the displayed equation shows that \(|Z(G)|\) is divisible by \(p\).

Finally, \(e\in Z(G)\), so \(|Z(G)|\) is a positive integer. Since \(p\mid |Z(G)|\) and every prime satisfies \(p\ge 2\), one has \(|Z(G)|\ge p\ge 2\). Therefore \(Z(G)\) contains an element different from \(e\), as required.

## intuition
Conjugation partitions G into singleton orbits indexed by central elements and non-singleton orbits whose sizes are positive powers of p. Reducing the class equation modulo p isolates the center.
