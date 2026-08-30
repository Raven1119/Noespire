# Center of a finite p-group

## Private source

Pre-registered self-contained reconstruction of the conjugation-action class equation. It was selected for its proof structure, not from model performance.

## Reference proof

Let \(G\) act on itself by conjugation. The orbit of \(x\in G\) is its conjugacy class, and the stabilizer of \(x\) is the centralizer \(C_G(x)\). Orbit-stabilizer gives
\[
|\operatorname{Cl}(x)|=[G:C_G(x)].
\]
Because \(|G|\) is a power of \(p\), every such index is a power of \(p\).

An element has a one-element conjugacy class exactly when it commutes with every element of \(G\), that is, exactly when it belongs to \(Z(G)\). Every conjugacy class outside the center therefore has size a power of \(p\) greater than one and hence has size divisible by \(p\).

Partitioning \(G\) into its conjugacy classes yields the class equation
\[
|G|=|Z(G)|+\sum_j |\operatorname{Cl}(x_j)|,
\]
where the sum ranges over the noncentral classes. The left side and every term of the sum are divisible by \(p\), so \(|Z(G)|\) is divisible by \(p\). The identity belongs to the center, making the center nonempty; since its order is a positive multiple of \(p\), it has at least \(p\) elements and therefore contains a nonidentity element.
