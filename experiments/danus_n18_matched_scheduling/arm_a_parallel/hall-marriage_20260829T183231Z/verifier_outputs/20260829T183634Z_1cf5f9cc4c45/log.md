started_at_utc: 2026-08-29T18:36:34.850059+00:00
command: /mnt/c/Users/wmywb/PycharmProjects/Noespire/experiments/danus_n16_blind/protocol/codex_blind_wrapper.sh exec --model gpt-5.6-sol --config 'model_reasoning_effort="xhigh"' -C /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent --skip-git-repo-check -c 'mcp_servers.danus={command="python3",args=["-m","danus.gateway"],env={DANUS_ROLE="verifier"}}' --dangerously-bypass-approvals-and-sandbox 'Run_id: 20260829T183634Z_1cf5f9cc4c45. Statement: Let (G=(X\sqcup Y,E)) be a finite bipartite graph. For (S\subseteq X), let

\[
N(S)=\{y\in Y: \text{(y) is adjacent to at least one vertex of (S)}\}.
\]

Prove that (G) has a matching saturating every vertex of (X) if and only if

\[
|N(S)|\ge |S|
\]

for every subset (S\subseteq X).. Proof:
Write \(N(U)\) for the set of all vertices of \(Y\) adjacent to at least one vertex of a set \(U\subseteq X\).

First suppose that \(M\) is a matching saturating every vertex of \(X\). For every \(x\in X\), there is exactly one edge of \(M\) incident with \(x\); let \(m(x)\in Y\) be its other endpoint. If \(x_1,x_2\in X\) are distinct, then \(m(x_1)\ne m(x_2)\), because otherwise the two matching edges incident with \(x_1\) and \(x_2\) would share their endpoint in \(Y\). Thus \(m:X\to Y\) is injective. For any \(S\subseteq X\), every vertex \(m(x)\) with \(x\in S\) is adjacent to a vertex of \(S\), so \(m(S)\subseteq N(S)\). Consequently
\[
|S|=|m(S)|\le |N(S)|.
\]
This proves the necessary direction.

Conversely, suppose that
\[
|N(S)|\ge |S| \qquad\text{for every }S\subseteq X.
\]
We prove that \(G\) has a matching saturating \(X\) by strong induction on \(n=|X|\). If \(n=0\), the empty matching saturates \(X\).

Fix \(n\ge 1\), and assume the assertion already holds for every finite bipartite graph whose left vertex class has cardinality strictly less than \(n\). There are two cases.

Case 1: there is a nonempty proper subset \(A\subsetneq X\) such that \(|N(A)|=|A|\).

Let \(G_A\) be the bipartite graph induced by the vertex classes \(A\) and \(N(A)\). If \(B\subseteq A\), every neighbor in \(G\) of a vertex of \(B\) belongs to \(N(A)\). Therefore the neighborhood of \(B\) in \(G_A\) is exactly \(N(B)\), and the assumed inequality gives \(|N(B)|\ge |B|\). Since \(0<|A|<n\), the induction hypothesis gives a matching \(M_A\) in \(G_A\) saturating \(A\).

Let \(G_R\) be the bipartite graph induced by the vertex classes \(X\setminus A\) and \(Y\setminus N(A)\). For any \(T\subseteq X\setminus A\), its neighborhood in \(G_R\) is \(N(T)\setminus N(A)\). Also,
\[
N(A\cup T)=N(A)\cup N(T).
\]
Because the sets are finite,
\[
\begin{aligned}
|N(T)\setminus N(A)|
&=|N(A)\cup N(T)|-|N(A)|\\
&=|N(A\cup T)|-|N(A)|\\
&\ge |A\cup T|-|A|\\
&=|T|.
\end{aligned}
\]
Here the inequality uses the assumed Hall inequality for \(A\cup T\), the equality \(|N(A)|=|A|\), and the fact that \(A\cap T=\varnothing\). Hence \(G_R\) satisfies the same neighborhood inequalities on its left vertex class. Since \(A\) is nonempty, \(|X\setminus A|<n\), so the induction hypothesis gives a matching \(M_R\) in \(G_R\) saturating \(X\setminus A\). The vertex sets of \(G_A\) and \(G_R\) are disjoint on both sides. Therefore \(M_A\cup M_R\) is a matching in \(G\), and it saturates every vertex of \(X\).

Case 2: there is no nonempty proper subset \(A\subsetneq X\) such that \(|N(A)|=|A|\).

Then every nonempty proper subset \(T\subsetneq X\) satisfies
\[
|N(T)|\ge |T|+1,
\]
because \(|N(T)|\ge |T|\), equality is excluded by the assumption of this case, and both cardinalities are integers. Choose any \(x\in X\). Applying the assumed inequality to \(\{x\}\) gives \(|N(\{x\})|\ge 1\), so choose \(y\in N(\{x\})\). In particular, \(xy\in E\).

Delete \(x\) and \(y\), and let \(G'"'"'\) be the resulting bipartite graph with left vertex class \(X\setminus\{x\}\) and right vertex class \(Y\setminus\{y\}\). If \(T=\varnothing\), its neighborhood in \(G'"'"'\) has size \(0=|T|\). If \(T\) is a nonempty subset of \(X\setminus\{x\}\), then \(T\) is a nonempty proper subset of \(X\). Its neighborhood in \(G'"'"'\) is \(N(T)\setminus\{y\}\), and hence
\[
|N(T)\setminus\{y\}|\ge |N(T)|-1\ge |T|.
\]
Thus \(G'"'"'\) satisfies the neighborhood inequalities on its left vertex class. Since \(|X\setminus\{x\}|=n-1<n\), the induction hypothesis gives a matching \(M'"'"'\) in \(G'"'"'\) saturating \(X\setminus\{x\}\). No edge of \(M'"'"'\) is incident with \(x\) or \(y\), so \(M'"'"'\cup\{xy\}\) is a matching in \(G\) saturating every vertex of \(X\).

The two cases exhaust all possibilities. Therefore the neighborhood inequalities imply the existence of a matching saturating \(X\), completing the proof of both directions.

Use AGENTS.md to verify the above proof for the statement. Write the verification JSON to this exact path: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json.'

Reading additional input from stdin...
OpenAI Codex v0.150.1
--------
workdir: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR]
reasoning effort: xhigh
reasoning summaries: none
session id: 01a04ecf-2ef3-7932-95b4-1edcff59d448
--------
user
Run_id: 20260829T183634Z_1cf5f9cc4c45. Statement: Let (G=(X\sqcup Y,E)) be a finite bipartite graph. For (S\subseteq X), let

\[
N(S)=\{y\in Y: \text{(y) is adjacent to at least one vertex of (S)}\}.
\]

Prove that (G) has a matching saturating every vertex of (X) if and only if

\[
|N(S)|\ge |S|
\]

for every subset (S\subseteq X).. Proof:
Write \(N(U)\) for the set of all vertices of \(Y\) adjacent to at least one vertex of a set \(U\subseteq X\).

First suppose that \(M\) is a matching saturating every vertex of \(X\). For every \(x\in X\), there is exactly one edge of \(M\) incident with \(x\); let \(m(x)\in Y\) be its other endpoint. If \(x_1,x_2\in X\) are distinct, then \(m(x_1)\ne m(x_2)\), because otherwise the two matching edges incident with \(x_1\) and \(x_2\) would share their endpoint in \(Y\). Thus \(m:X\to Y\) is injective. For any \(S\subseteq X\), every vertex \(m(x)\) with \(x\in S\) is adjacent to a vertex of \(S\), so \(m(S)\subseteq N(S)\). Consequently
\[
|S|=|m(S)|\le |N(S)|.
\]
This proves the necessary direction.

Conversely, suppose that
\[
|N(S)|\ge |S| \qquad\text{for every }S\subseteq X.
\]
We prove that \(G\) has a matching saturating \(X\) by strong induction on \(n=|X|\). If \(n=0\), the empty matching saturates \(X\).

Fix \(n\ge 1\), and assume the assertion already holds for every finite bipartite graph whose left vertex class has cardinality strictly less than \(n\). There are two cases.

Case 1: there is a nonempty proper subset \(A\subsetneq X\) such that \(|N(A)|=|A|\).

Let \(G_A\) be the bipartite graph induced by the vertex classes \(A\) and \(N(A)\). If \(B\subseteq A\), every neighbor in \(G\) of a vertex of \(B\) belongs to \(N(A)\). Therefore the neighborhood of \(B\) in \(G_A\) is exactly \(N(B)\), and the assumed inequality gives \(|N(B)|\ge |B|\). Since \(0<|A|<n\), the induction hypothesis gives a matching \(M_A\) in \(G_A\) saturating \(A\).

Let \(G_R\) be the bipartite graph induced by the vertex classes \(X\setminus A\) and \(Y\setminus N(A)\). For any \(T\subseteq X\setminus A\), its neighborhood in \(G_R\) is \(N(T)\setminus N(A)\). Also,
\[
N(A\cup T)=N(A)\cup N(T).
\]
Because the sets are finite,
\[
\begin{aligned}
|N(T)\setminus N(A)|
&=|N(A)\cup N(T)|-|N(A)|\\
&=|N(A\cup T)|-|N(A)|\\
&\ge |A\cup T|-|A|\\
&=|T|.
\end{aligned}
\]
Here the inequality uses the assumed Hall inequality for \(A\cup T\), the equality \(|N(A)|=|A|\), and the fact that \(A\cap T=\varnothing\). Hence \(G_R\) satisfies the same neighborhood inequalities on its left vertex class. Since \(A\) is nonempty, \(|X\setminus A|<n\), so the induction hypothesis gives a matching \(M_R\) in \(G_R\) saturating \(X\setminus A\). The vertex sets of \(G_A\) and \(G_R\) are disjoint on both sides. Therefore \(M_A\cup M_R\) is a matching in \(G\), and it saturates every vertex of \(X\).

Case 2: there is no nonempty proper subset \(A\subsetneq X\) such that \(|N(A)|=|A|\).

Then every nonempty proper subset \(T\subsetneq X\) satisfies
\[
|N(T)|\ge |T|+1,
\]
because \(|N(T)|\ge |T|\), equality is excluded by the assumption of this case, and both cardinalities are integers. Choose any \(x\in X\). Applying the assumed inequality to \(\{x\}\) gives \(|N(\{x\})|\ge 1\), so choose \(y\in N(\{x\})\). In particular, \(xy\in E\).

Delete \(x\) and \(y\), and let \(G'\) be the resulting bipartite graph with left vertex class \(X\setminus\{x\}\) and right vertex class \(Y\setminus\{y\}\). If \(T=\varnothing\), its neighborhood in \(G'\) has size \(0=|T|\). If \(T\) is a nonempty subset of \(X\setminus\{x\}\), then \(T\) is a nonempty proper subset of \(X\). Its neighborhood in \(G'\) is \(N(T)\setminus\{y\}\), and hence
\[
|N(T)\setminus\{y\}|\ge |N(T)|-1\ge |T|.
\]
Thus \(G'\) satisfies the neighborhood inequalities on its left vertex class. Since \(|X\setminus\{x\}|=n-1<n\), the induction hypothesis gives a matching \(M'\) in \(G'\) saturating \(X\setminus\{x\}\). No edge of \(M'\) is incident with \(x\) or \(y\), so \(M'\cup\{xy\}\) is a matching in \(G\) saturating every vertex of \(X\).

The two cases exhaust all possibilities. Therefore the neighborhood inequalities imply the existence of a matching saturating \(X\), completing the proof of both directions.

Use AGENTS.md to verify the above proof for the statement. Write the verification JSON to this exact path: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json.
warning: Codex could not find bubblewrap on PATH. Install bubblewrap with your OS package manager. See the sandbox prerequisites: https://developers.openai.com/codex/concepts/sandboxing#prerequisites. Codex will use the bundled bubblewrap in the meantime.
warning: Under-development features enabled: current_time_reminder. Under-development features are incomplete and may behave unpredictably. To suppress this warning, set `suppress_unstable_features_warning = true` in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/codex-home/config.toml.
warning: Skill descriptions were shortened to fit the skills context budget. Codex can still see every skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room for the rest.
codex
I’m using the three required verification skills in order: sequential proof checking, reference checking, then strict report synthesis. I’ll keep the review text-only and write only the required JSON artifact.
  → Read and apply verify-sequential-statements instructions; audit the proof in textual order
  • Read and apply check-referenced-statements instructions; validate any cited external results
  • Read and apply synthesize-verification-report instructions; enforce strict verdict and write JSON
  • Read back the output file and confirm its JSON content
exec
/bin/bash -lc 'cat /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/skills/verify/verify-sequential-statements/SKILL.md' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 1134ms:
---
name: verify-sequential-statements
description: Verify a markdown proof in the order it is written. Use when the task is to check local correctness, theorem applicability, and reasoning gaps statement by statement through a paper-style proof.
---

# Verify Sequential Statements

Check each statement and subproof in order and log all local issues.

## Input Contract

Assume:

- `Proof` is markdown text.
- The proof is written in good mathematical order.
- `Statement` contains the target theorem statement and its hypotheses.

Do not split the proof with utility code. Read the markdown in order and use its own structure.

## Procedure

1. Extract the assumptions and hypotheses from `Statement` before checking the proof.
2. Iterate through the statements/subproofs in the order they appear in the markdown.
3. For each item, determine a location key:
   - use the displayed theorem/lemma/claim heading if present,
   - otherwise use a local textual locator such as `proof paragraph 2`.
4. Check local reasoning:
   - Is the inference valid?
   - Are assumptions stated and sufficient?
   - Is each theorem application valid in context?
   - Are there skipped or hand-wavy steps?
5. Pay special attention to assumptions that an object exists or satisfies a property — sometimes such an object has not been constructed, or it exists but has not been proved to satisfy the claimed property.
6. Audit whether the assumptions from `Statement` are actually used in the proof.
7. If some assumptions seem unused, do not assume they are harmless. Reason carefully about whether:
   - the assumption is truly redundant, or
   - the proof is silently omitting a necessary use of it and therefore has a gap or error.
8. Classify findings:
   - `critical_error`: logical contradiction, invalid theorem use, false implication.
   - `gap`: missing derivation, vague justification, unsupported step, or suspiciously unused assumptions whose role is not justified.
9. Also apply the **Hard Prohibitions** defined in the verifier contract (`agents/contracts/verifier.md`, "Hard Prohibitions to enforce"): P1 (citing `problem.md` / `data/<NAME>.md` as a substantive math source), P3 (an unproven conditional premise with no same-paragraph `fact_id` citation), P5 (a vague gesture at a "well-known"/"classical" result without a specific citation), and P6 (a statement that is not self-contained). Do not restate or fork the prohibition wording here — read and apply it from the contract so there is a single source of truth. These prohibitions are strictly additive: they only ever add findings (reject more), never remove them.
10. Keep each checked item in context for the synthesis step. You persist nothing —
   the verifier is stateless; the worker does all writing.

## Output Contract

Produce one record per checked item, kept in context for synthesis:

```json
{
  "location": "Lemma 3",
  "status": "checked",
  "critical_errors": [
    {"location": "Lemma 3", "issue": "Incorrect implication from A to B."}
  ],
  "gaps": [
    {"location": "Lemma 3", "issue": "Missing justification of boundedness."}
  ]
}
```

## Tools

- None — pure reasoning over the proof; findings stay in context.

codex
The sequential-check skill reinforces the contract’s hard prohibitions, so I’m consulting the referenced verifier contract before recording findings. No proof step cites a fact graph item or named external theorem so far.
exec
/bin/bash -lc 'cat /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/contracts/verifier.md' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 1096ms:
# Proof Verification Agent

This agent verifies the correctness of a mathematical proof provided in markdown format. It checks the logical flow, theorem applications, and external references to ensure the proof is valid. The agent produces a detailed verification report and a strict verdict on the proof's correctness.

## Objective

You are the verifier behind the Danus verify service — the **sole authority on
mathematical correctness**. When a worker calls `fact_submit` on a candidate fact,
the service hands you that fact's statement and proof; you decide correctness and
produce the verdict. **The fact is written to the fact graph iff you return
`"correct"`** — your verdict is the gate.

Given:

- `Run_id: <run_id>` — the service's handle for this verification
- `Statement: <the candidate fact's statement>`
- `Proof: <the candidate fact's proof, markdown>`

produce the verdict (the service returns it to `fact_submit`), with JSON fields:

- `verification_report`
- `verdict` (`"correct"` or `"wrong"`)
- `repair_hints`

## Input Contract

Assume `Proof` is markdown text written in normal mathematical order, like a paper proof with lemmas, propositions, claims, and a main theorem proof.

- Verify the statements and subproofs sequentially in the order they appear in the markdown.
- The main theorem conclusion is accepted only if the full markdown proof passes.

No code-level proof parser is required. Do not invent parser modules for subgoal extraction. Read the markdown in order and use its displayed structure.

## Resource safety

Verification is text-only reasoning. Never execute Python or any other program to
test a claim, enumerate cases, perform numerical or symbolic algebra, call a
solver or proof assistant, compile code, or run parallel computation—not even for
a supposedly tiny check. Lightweight reading of proof/fact text and literature
retrieval are allowed. If validity depends on a machine computation that is not
reconstructed as a complete written argument, record the corresponding gap or
error instead of running it yourself.

You may read the project **fact graph** for context: when the proof cites a
`fact_id`, read `runtime/projects/<PROJECT>/fact_graph/facts/<fact_id>.md` to get
that fact's own statement (and proof) and check the citation is really what the
step needs; read `runtime/projects/<PROJECT>/fact_graph/glossary.json` to resolve
project symbols, and `danus/core/glossary_global.json` for universal notation (Z,
Q, R, C, floor/ceil, Greek parameter names, …) — these need no project definition.
The fact graph and external paper search are the only sources you consult — no LLM
(see below).

## Required Skills

Use these skills in this order:

1. `$verify-sequential-statements`
2. `$check-referenced-statements`
3. `$synthesize-verification-report`


## Statelessness

You are stateless with respect to the system: you **persist nothing** to global
memory or the fact graph — the worker does all writing (`gm_add` updates global
memory; `fact_submit` writes the fact to the graph, but only after you accept, and
also records your verdict to global memory as a `verification` trace). Your sole
job is the verdict: hold your per-item findings in context as you check, then
synthesize the single verification report. Your only output is that report — the
feedback on whether the proof is correct and, if not, where.

## Verification Workflow

### Step 1: Initialize run context

1. Read `Run_id`, `Statement`, `Proof`.
2. Treat `Proof` as markdown text and read it in the order written.
3. Extract the assumptions and hypotheses stated in `Statement` before checking the proof.
4. If the proof text is empty or not usable as mathematical proof text, record a critical error at location `proof` and continue to final report with `verdict="wrong"`.

### Step 2: Sequential proof-item verification

For each statement/subproof in the markdown, in textual order:

1. Set location string:
   - use the displayed lemma/proposition/theorem/claim name if present,
   - otherwise use a textual location such as `proof paragraph 3` or `middle section after Lemma 2`.
2. Check:
   - logical validity of inferences,
   - correct theorem application,
   - missing assumptions,
   - unjustified jumps / hand-wavy reasoning.
3. Check whether the assumptions from the problem statement are actually used in the proof.
4. If some assumptions appear unused, think carefully before classifying them:
   - decide whether the assumptions are genuinely redundant,
   - or whether the proof is missing a necessary argument and therefore contains a gap or error.
5. Record all findings using:
   - Critical errors: incorrect logic, theorem misuse, contradiction, wrong referenced theorem.
   - Gaps: skipped derivations, vague arguments, missing intermediate justification, suspiciously unused assumptions whose role is not justified.
6. Keep each finding (its location, type, and issue) in context for the report.

### Step 3: External reference checking

When a statement or subproof cites a theorem/lemma/definition from an external paper:

1. Query `search_arxiv_theorems` with the full referenced statement text.
2. Compare returned theorem texts to the referenced statement directly in agent reasoning.
3. Expand the definitions and terminology in the cited statement using the cited paper's context before deciding whether the theorem applies.
4. Check whether the current proof uses those terms with the same meanings and hypotheses. In mathematics, the same word can refer to different definitions in different contexts.
5. Accept only when both are true:
   - the returned statement clearly matches the cited statement,
   - the cited paper's contextual definitions and assumptions fit the current problem.
6. If the theorem exists but is used with mismatched definitions, assumptions, or ambient context, add a critical error for incorrect application.
7. If no match is found, use Codex's built-in web search with the same referenced statement.
8. If still not found, add a critical error:
   - location: where the reference is used
   - issue: non-existent or wrong external reference.
9. Keep each reference-check finding in context for the report.


### Step 4: Build verification report

Aggregate every error and gap across the full markdown proof.

`verification_report` must include:

- `summary`
- `critical_errors` (list of objects; each has `location` and `issue`)
- `gaps` (list of objects; each has `location` and `issue`)

Do not drop any finding.

### Step 5: Verdict rule and repair hints

Verdict rule is strict:

- Return `"correct"` if and only if both `critical_errors` and `gaps` are empty.
- Otherwise return `"wrong"`.

Repair hints:

- If verdict is `"correct"`, set `"repair_hints": ""`.
- If verdict is `"wrong"`, provide concrete non-empty hints to repair each major issue.

### Step 6: Output write and completion

Write the final JSON **directly** to the exact output path named in the prompt
(there is no `write_*` tool — the verify service reads this file back):

- `results/{run_id}/verification.json`

Stop only after this file is written successfully.

## Output JSON Contract

The final response and file content must be:

```json
{
  "verification_report": {
    "summary": "string",
    "critical_errors": [
      {"location": "string", "issue": "string"}
    ],
    "gaps": [
      {"location": "string", "issue": "string"}
    ]
  },
  "verdict": "correct",
  "repair_hints": ""
}
```

If any error or gap exists, `verdict` must be `"wrong"` and `repair_hints` must be non-empty.

## Hard Invariants

1. Verify the markdown proof in textual order.
2. Include every critical error and every gap in the report.
3. External-paper references must be checked via `search_arxiv_theorems` first, then Codex's built-in web search.
4. Accept iff there are zero errors and zero gaps.
5. Persist final JSON to `results/{run_id}/verification.json`.
6. Use text-only reasoning; never execute mathematical computation.

## Hard Prohibitions to enforce

Each of the following patterns, if found anywhere in the proof, MUST be recorded as a `critical_error`. The HTTP server's pre-checks already reject the most blatant single-line violations before this prompt runs, but you may encounter the same violations spread across multiple lines or inside larger paragraphs. Be strict.

> The example phrasings below (e.g. "master reduction package", "post-W_q") are
> instances, not an exhaustive list. Enforce the *category* each prohibition
> names — citing the problem statement as a source, unproven conditional
> premises, vague appeals to well-known results — not only the exact wording.

### P1. Citation of `problem.md` / `data/<NAME>.md` as a substantive math source

If any proof step's justification is one of:

- "as declared in problem.md" / "as declared in data/<NAME>.md"
- "from problem.md item N" / "from data/<NAME>.md item N"
- "by the master reduction package declared in problem.md / data/<NAME>.md / the problem statement"
- "as known from the problem prompt"
- "by the verified reductions / building blocks listed in problem.md"
- "as stated in problem.md"
- "the master reduction package declared in problem.md"

then record a `critical_error` at that location with `issue` containing "Hard Prohibition P1: cites problem.md as math source. Replace with a specific signed fact_id from the fact graph (runtime/projects/<PROJECT>/fact_graph/facts/)."

`problem.md` is the target description, NOT a source of premises. Every step must cite either an elementary tactic, a specific signed `fact_id` (16 hex characters, from the fact graph), or an external paper following Step 3 above.

The legitimate phrase "from the problem statement, X = ..." is OK when it just restates a hypothesis; the patterns above flag substantive justifications, not hypothesis re-statements.

### P3. Unproven conditional premises

If a step has the form

- "Assume the verified ... reductions have [reduced | narrowed | placed] a (putative) (no-hit) survivor to ..."
- "Assume the verified post-W_q ... reductions have ..."
- "Suppose the residual / cell / data has been [reduced | narrowed] to ..."

then check the SAME paragraph (delimited by blank lines) for a 16-hex `fact_id` citation that proves the assumption. If no such citation exists, record a `critical_error` with `issue` containing "Hard Prohibition P3: unproven conditional premise; the proof assumes a residual narrowing without citing the signed fact that proves it."

The HTTP server's pre-check catches the simple single-line case. You catch the case where the assumption is set up in one paragraph and then USED several paragraphs later without an intervening citation; in that case the citation must be in the using paragraph.

### P5. Vague gestures at "well-known" results

If any step's justification is

- "by some Beatty / Dirichlet / Diophantine / Vinogradov / Weyl / classical / well-known argument / theorem / inequality / estimate"
- "as is well known [that | in the literature]"
- "by an obvious / elementary / standard density / Diophantine / integer / approximation / counting / equidistribution argument / theorem / principle"

then record a `critical_error` with `issue` containing "Hard Prohibition P5: vague gesture at classical result without specific citation."

The proof must replace each such gesture with either (a) a specific signed `fact_id`, or (b) an external paper citation following Step 3 of this document (with `paper_id`, `theorem_id`, and `arXiv id` when applicable).

### P6. Self-contained statement check

Check that the candidate fact's `statement` is self-contained. If it begins with "Under the standard ... hypotheses" or similar without listing those hypotheses, record a `gap` with `issue` containing "Hard Prohibition P6: statement is not self-contained; the reader cannot determine the hypotheses from the statement alone."

### P3-supplement (chain check)

When a step cites a 16-hex `fact_id`, treat that fact's own `statement` as if it were inlined. If the cited fact's statement contains an unproven conditional premise (per P3 above), the citing proof inherits that defect: record a `critical_error` with `issue` "Hard Prohibition P3 (chain): cited fact `<id>` itself contains an unproven conditional premise — the proof transitively depends on an unproven assumption."

Read the cited fact from the fact graph to perform this chain check, and flag any such inherited defect here so the verification report itself is honest.

### Notes on these prohibitions

- These prohibitions add to the existing accept rule (zero `critical_errors` AND zero `gaps`), making it strictly more strict. They never cause acceptance of a proof that the previous logic would have rejected.
- The HTTP server's pre-checks are deterministic regex matches. Your role is to catch the multi-line and contextual cases that regex misses.
- If a proof legitimately uses one of the matched phrases in a non-justification context (e.g., quoting a problematic phrase to argue against it), use your judgment and make the call clear in the `issue` text. False positives here are recoverable (workers can rephrase); false negatives let bogus proofs through.

The statement is self-contained and the induction proof checks out through the necessity direction, the tight-subset decomposition, and the strict-inequality deletion case; no hard-prohibition pattern or unsupported premise appears.
  ✓ Read and apply verify-sequential-statements instructions; audit the proof in textual order
  → Read and apply check-referenced-statements instructions; validate any cited external results
  • Read and apply synthesize-verification-report instructions; enforce strict verdict and write JSON
  • Read back the output file and confirm its JSON content
exec
/bin/bash -lc 'cat /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/skills/verify/check-referenced-statements/SKILL.md' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 1485ms:
---
name: check-referenced-statements
description: Validate externally referenced theorems by querying arXiv theorem search first and Codex's built-in web search second. Use when a markdown proof cites statements from external papers.
---

# Check Referenced Statements

Validate every external-paper reference used in the proof.

## Input Contract

For each cited external theorem/lemma/definition:

- location where it is used,
- the full referenced statement text.

## Procedure

1. Query `search_arxiv_theorems` using the full referenced statement as `query`.
2. Inspect returned results and compare theorem text directly to the referenced statement in reasoning.
3. Expand the definitions and terminology appearing in the cited statement using the cited paper's context before deciding whether the theorem applies.
4. Check whether the same words in the current proof mean the same thing as they do in the cited paper. In mathematics, identical words can carry different definitions in different contexts. Distinguish similar-looking definitions: compare their exact formulas, notation, and quantifiers; do not collapse two just because the names or formulas look close.
5. Accept as matched and applicable only when both are true:
   - the result clearly corresponds to the cited statement,
   - the contextual definitions and hypotheses align with the current problem.
6. If the theorem exists but the current proof uses different definitions, hypotheses, ambient objects, or a subtly different defining formula, record a critical error for incorrect application.
7. If the proof uses the cited statement to derive further conclusions, verify that transition too: a hand-wavy specialization or instantiation is a `gap`; a logically invalid transition is a `critical_error`; if it deduces one property from another, compare their exact defining formulas before accepting.
8. If no match is found, use Codex's built-in web search with the same statement text.
9. If still not found, emit a critical error:
   - location: where the citation is used,
   - issue: referenced theorem appears non-existent or incorrectly cited.
10. When a step cites an internal `fact_id` (16 hex characters) rather than an external paper, apply the verifier contract's P3-supplement **chain check** (`agents/contracts/verifier.md`): read the cited fact from the project fact graph and, if its own statement carries an unproven conditional premise, record the inherited defect as a `critical_error`. Read and apply the wording from the contract; do not fork it here.
11. Keep each reference check in context for the synthesis step (you persist nothing —
   the verifier is stateless).

Do not rely on dedicated comparison utility code; perform comparison through careful reasoning.

## Output Contract

Produce one record per reference check, kept in context for synthesis:

```json
{
  "location": "Lemma 2",
  "referenced_statement": "Exact statement text",
  "context_expansion": "In the cited paper, 'regular' means regular with respect to the valuation topology.",
  "arxiv_match_found": false,
  "web_match_found": false,
  "critical_error": {
    "location": "Lemma 2",
    "issue": "Referenced external theorem was not found in arXiv search or Codex built-in web search."
  }
}
```

## Tools

- `search_arxiv_theorems`
- Codex's built-in web search

(Findings stay in context for synthesis — nothing is persisted.)

codex
The reference-check stage finds no external-paper citations and no 16-hex internal fact citations, so there is nothing to query or chain-check. The proof is fully self-contained.
No referenced statements occur, so the required reference-check stage completes without literature searches or fact-graph reads.
  ✓ Read and apply verify-sequential-statements instructions; audit the proof in textual order
  ✓ Read and apply check-referenced-statements instructions; validate any cited external results
  → Read and apply synthesize-verification-report instructions; enforce strict verdict and write JSON
  • Read back the output file and confirm its JSON content
exec
/bin/bash -lc 'cat /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/skills/verify/synthesize-verification-report/SKILL.md' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 1034ms:
---
name: synthesize-verification-report
description: Aggregate all detected errors and gaps into the final verification report, apply strict accept/reject logic, and produce repair hints when rejected.
---

# Synthesize Verification Report

Produce the final verification output JSON and verdict.

## Input Contract

Aggregate all findings you produced earlier in this verification session — the
per-item records from the sequential check and the reference check, held in
context. Each issue must include `location` and `issue`.

## Procedure

1. Collect all critical errors and all gaps from previous checks.
2. Build a complete `verification_report` object with:
   - `summary`
   - `critical_errors`
   - `gaps`
3. Apply strict verdict rule:
   - `correct` iff `critical_errors=[]` and `gaps=[]`.
   - otherwise `wrong`.
4. If verdict is `wrong`, produce concrete non-empty `repair_hints`.
5. Self-check the JSON against its schema before emitting — do this by reasoning, not by calling a tool:
   - `verdict` is exactly `"correct"` or `"wrong"`,
   - `repair_hints` is non-empty **iff** `verdict == "wrong"` (empty string when `"correct"`),
   - every entry of `critical_errors` and `gaps` has both `location` and `issue`,
   - the verdict is consistent with the rule in step 3 (any critical error or gap forces `"wrong"`).
   If the self-check fails, correct the object before continuing.
6. Write the final JSON to the run's result file and emit it as your final message.
   The verify service injects the absolute path for this run — write to
   `results/{run_id}/verification.json` under the service-provided run directory
   (`{run_id}` is the `Run_id` given to you). The verify service reads this file
   back and returns it verbatim as the HTTP `/verify` response; you invoke no MCP
   tool to persist it. Stop only after the file is written and the same JSON is
   your final message.

## Output Contract

Final output JSON:

```json
{
  "verification_report": {
    "summary": "string",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}
```

If there is any error or gap, verdict must be `"wrong"` and `repair_hints` must be non-empty.

## Tools

- None — you build, self-check, and write the report by reasoning. The final JSON
  is written to `results/{run_id}/verification.json`; the verify service returns it
  as the `/verify` response.

(The verdict is the verifier's only output — no memory is written; the worker does
all writing to global memory and the fact graph.)

codex
Synthesis yields zero critical errors and zero gaps. Under the strict rule, the verdict is `correct`; I’m now writing that exact schema to the requested run file.
exec
/bin/bash -lc 'ls -ld /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 957ms:
drwxrwxrwx 1 wmywb wmywb 4096 Aug 30 02:36 /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45

apply patch
patch: completed
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
diff --git a//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..5f2feaeca6bc7b1e02268d7c596d2f576f9c7c78
--- /dev/null
+++ b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

diff --git a//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..5f2feaeca6bc7b1e02268d7c596d2f576f9c7c78
--- /dev/null
+++ b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

exec
/bin/bash -lc 'cat /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 877ms:
{
  "verification_report": {
    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}

diff --git a//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..5f2feaeca6bc7b1e02268d7c596d2f576f9c7c78
--- /dev/null
+++ b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

The strict report was synthesized, written to the requested path, and read back successfully with the expected schema and correct verdict.
  ✓ Read and apply verify-sequential-statements instructions; audit the proof in textual order
  ✓ Read and apply check-referenced-statements instructions; validate any cited external results
  ✓ Read and apply synthesize-verification-report instructions; enforce strict verdict and write JSON
  ✓ Read back the output file and confirm its JSON content
diff --git a//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..5f2feaeca6bc7b1e02268d7c596d2f576f9c7c78
--- /dev/null
+++ b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

codex
{
  "verification_report": {
    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}
diff --git a//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..5f2feaeca6bc7b1e02268d7c596d2f576f9c7c78
--- /dev/null
+++ b//mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260829T183634Z_1cf5f9cc4c45/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

tokens used
29,344
{
  "verification_report": {
    "summary": "The proof is correct and complete. The forward implication constructs an injection from X into Y along a matching saturating X, which immediately gives the neighborhood inequalities. For the converse, the strong-induction argument is valid: a nonempty proper tight subset permits compatible matchings on the induced tight part and its complement, while in the absence of a proper tight subset, deleting an arbitrary left vertex together with one of its neighbors preserves Hall's inequalities for the remaining graph. The two cases are exhaustive, all uses of finiteness and induction are justified, and no external references or prohibited unsupported premises occur.",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}
