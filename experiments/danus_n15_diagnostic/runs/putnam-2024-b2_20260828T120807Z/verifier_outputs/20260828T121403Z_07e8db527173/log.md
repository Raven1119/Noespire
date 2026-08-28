started_at_utc: 2026-08-28T12:14:03.276530+00:00
command: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/bin/codex exec --model gpt-5.6-sol --config 'model_reasoning_effort="xhigh"' -C /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent --skip-git-repo-check -c 'mcp_servers.danus={command="python3",args=["-m","danus.gateway"],env={DANUS_ROLE="verifier"}}' --dangerously-bypass-approvals-and-sandbox 'Run_id: 20260828T121403Z_07e8db527173. Statement: Two convex quadrilaterals are called partners if they have three vertices in common and they can be labeled \(ABCD\) and \(ABCE\) so that \(E\) is the reflection of \(D\) across the perpendicular bisector of the diagonal \(AC\). Is there an infinite sequence of convex quadrilaterals such that each quadrilateral is a partner of its successor and no two elements of the sequence are congruent?. Proof:
No.

Assume that \(Q_1,Q_2,\ldots\) is any sequence of convex quadrilaterals in which consecutive terms are partners. We prove that only finitely many congruence classes can occur.

For a convex quadrilateral, its two diagonals intersect at an interior point. In particular, the two diagonals are nonparallel, so their perpendicular bisectors are nonparallel and have a unique intersection.

Consider one partnership step. Label the old and new quadrilaterals \(ABCD\) and \(ABCE\), respectively, so that \(E\) is the reflection of \(D\) across the perpendicular bisector \(\ell\) of \(AC\). (If a partner labeling was initially given in the reverse order, interchange \(D\) and \(E\); reflection is an involution.) Let \(O\) be the unique intersection of the perpendicular bisectors of the diagonals \(AC\) and \(BD\) of \(ABCD\).

Because \(O\in\ell\), reflection across \(\ell\) fixes \(O\). Since that reflection sends \(D\) to \(E\), it follows that \(OD=OE\). Also, because \(O\) lies on the perpendicular bisector of \(BD\), we have \(OB=OD\). Hence \(OB=OE\), so \(O\) lies on the perpendicular bisector of \(BE\). It still lies on the perpendicular bisector \(\ell\) of \(AC\). The diagonals of the new convex quadrilateral \(ABCE\) are \(AC\) and \(BE\), and their perpendicular bisectors have a unique intersection. Consequently their intersection is the same point \(O\).

Applying this argument at every step shows that one point \(O\) is the intersection of the diagonal perpendicular bisectors for every quadrilateral in the sequence. Moreover, a partnership step keeps the three common vertices and replaces \(D\) by \(E\) with \(OD=OE\). Thus the unordered multiset \(\mathcal R\) of the four distances from \(O\) to the vertices is independent of the term of the sequence.

The unordered multiset \(\mathcal S\) of the four side lengths is also independent of the term. Indeed, in the partner labeling, the side lengths \(AB\) and \(BC\) are unchanged. Reflection across \(\ell\) interchanges \(A\) and \(C\), and sends \(D\) to \(E\). Since reflection preserves distance, \(CD=AE\) and \(DA=CE\). Therefore the old side-length multiset
\[
 \{AB,BC,CD,DA\}
\]
equals the new side-length multiset
\[
 \{AB,BC,CE,EA\}.
\]

It remains to show that the fixed finite metric data \(\mathcal R\) and \(\mathcal S\) allow only finitely many congruence classes. Cyclically label the vertices of any term as \(P_1,P_2,P_3,P_4\). There are only finitely many possible ordered choices of the four distances \(OP_1,OP_2,OP_3,OP_4\), because their multiset is \(\mathcal R\). There are likewise only finitely many possible ordered choices of the four side lengths \(P_1P_2,P_2P_3,P_3P_4,P_4P_1\), because their multiset is \(\mathcal S\).

Fix one such pair of ordered choices, and write the prescribed vertex distances as \(r_1,r_2,r_3,r_4\) and the prescribed consecutive side lengths as \(s_1,s_2,s_3,s_4\). Every \(r_i\) is positive: if \(O=P_i\), then \(O\), being on the perpendicular bisector of the diagonal joining \(P_i\) to the opposite vertex, would have distance \(0\) from both endpoints, making those two vertices equal.

Up to a rigid motion, place \(O\) at the origin and \(P_1\) at the point \((r_1,0)\). Once \(P_i\) is chosen, \(P_{i+1}\) must lie both on the circle centered at \(O\) with radius \(r_{i+1}\) and on the circle centered at \(P_i\) with radius \(s_i\). Two distinct circles have at most two intersection points; the circles here cannot coincide because their centers \(O\) and \(P_i\) are distinct. Hence there are at most two choices for each of \(P_2,P_3,P_4\), and therefore at most \(2^3\) configurations before the final condition \(P_4P_1=s_4\) is imposed. That final condition and convexity can only discard configurations. Thus each ordered metric choice yields finitely many congruence classes. Since there are finitely many ordered metric choices, only finitely many congruence classes occur in the entire sequence.

An infinite sequence with no two congruent terms would require infinitely many congruence classes, contradicting the preceding finiteness. Therefore no such infinite sequence exists.

Use AGENTS.md to verify the above proof for the statement. Write the verification JSON to this exact path: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json.'

Reading additional input from stdin...
OpenAI Codex v0.150.1
--------
workdir: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: xhigh
reasoning summaries: none
session id: 01a0484a-99f7-7222-85d8-421249dea329
--------
user
Run_id: 20260828T121403Z_07e8db527173. Statement: Two convex quadrilaterals are called partners if they have three vertices in common and they can be labeled \(ABCD\) and \(ABCE\) so that \(E\) is the reflection of \(D\) across the perpendicular bisector of the diagonal \(AC\). Is there an infinite sequence of convex quadrilaterals such that each quadrilateral is a partner of its successor and no two elements of the sequence are congruent?. Proof:
No.

Assume that \(Q_1,Q_2,\ldots\) is any sequence of convex quadrilaterals in which consecutive terms are partners. We prove that only finitely many congruence classes can occur.

For a convex quadrilateral, its two diagonals intersect at an interior point. In particular, the two diagonals are nonparallel, so their perpendicular bisectors are nonparallel and have a unique intersection.

Consider one partnership step. Label the old and new quadrilaterals \(ABCD\) and \(ABCE\), respectively, so that \(E\) is the reflection of \(D\) across the perpendicular bisector \(\ell\) of \(AC\). (If a partner labeling was initially given in the reverse order, interchange \(D\) and \(E\); reflection is an involution.) Let \(O\) be the unique intersection of the perpendicular bisectors of the diagonals \(AC\) and \(BD\) of \(ABCD\).

Because \(O\in\ell\), reflection across \(\ell\) fixes \(O\). Since that reflection sends \(D\) to \(E\), it follows that \(OD=OE\). Also, because \(O\) lies on the perpendicular bisector of \(BD\), we have \(OB=OD\). Hence \(OB=OE\), so \(O\) lies on the perpendicular bisector of \(BE\). It still lies on the perpendicular bisector \(\ell\) of \(AC\). The diagonals of the new convex quadrilateral \(ABCE\) are \(AC\) and \(BE\), and their perpendicular bisectors have a unique intersection. Consequently their intersection is the same point \(O\).

Applying this argument at every step shows that one point \(O\) is the intersection of the diagonal perpendicular bisectors for every quadrilateral in the sequence. Moreover, a partnership step keeps the three common vertices and replaces \(D\) by \(E\) with \(OD=OE\). Thus the unordered multiset \(\mathcal R\) of the four distances from \(O\) to the vertices is independent of the term of the sequence.

The unordered multiset \(\mathcal S\) of the four side lengths is also independent of the term. Indeed, in the partner labeling, the side lengths \(AB\) and \(BC\) are unchanged. Reflection across \(\ell\) interchanges \(A\) and \(C\), and sends \(D\) to \(E\). Since reflection preserves distance, \(CD=AE\) and \(DA=CE\). Therefore the old side-length multiset
\[
 \{AB,BC,CD,DA\}
\]
equals the new side-length multiset
\[
 \{AB,BC,CE,EA\}.
\]

It remains to show that the fixed finite metric data \(\mathcal R\) and \(\mathcal S\) allow only finitely many congruence classes. Cyclically label the vertices of any term as \(P_1,P_2,P_3,P_4\). There are only finitely many possible ordered choices of the four distances \(OP_1,OP_2,OP_3,OP_4\), because their multiset is \(\mathcal R\). There are likewise only finitely many possible ordered choices of the four side lengths \(P_1P_2,P_2P_3,P_3P_4,P_4P_1\), because their multiset is \(\mathcal S\).

Fix one such pair of ordered choices, and write the prescribed vertex distances as \(r_1,r_2,r_3,r_4\) and the prescribed consecutive side lengths as \(s_1,s_2,s_3,s_4\). Every \(r_i\) is positive: if \(O=P_i\), then \(O\), being on the perpendicular bisector of the diagonal joining \(P_i\) to the opposite vertex, would have distance \(0\) from both endpoints, making those two vertices equal.

Up to a rigid motion, place \(O\) at the origin and \(P_1\) at the point \((r_1,0)\). Once \(P_i\) is chosen, \(P_{i+1}\) must lie both on the circle centered at \(O\) with radius \(r_{i+1}\) and on the circle centered at \(P_i\) with radius \(s_i\). Two distinct circles have at most two intersection points; the circles here cannot coincide because their centers \(O\) and \(P_i\) are distinct. Hence there are at most two choices for each of \(P_2,P_3,P_4\), and therefore at most \(2^3\) configurations before the final condition \(P_4P_1=s_4\) is imposed. That final condition and convexity can only discard configurations. Thus each ordered metric choice yields finitely many congruence classes. Since there are finitely many ordered metric choices, only finitely many congruence classes occur in the entire sequence.

An infinite sequence with no two congruent terms would require infinitely many congruence classes, contradicting the preceding finiteness. Therefore no such infinite sequence exists.

Use AGENTS.md to verify the above proof for the statement. Write the verification JSON to this exact path: /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json.
warning: Under-development features enabled: current_time_reminder. Under-development features are incomplete and may behave unpredictably. To suppress this warning, set `suppress_unstable_features_warning = true` in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/codex-home/config.toml.
warning: Skill descriptions were shortened to fit the skills context budget. Codex can still see every skill, but some descriptions are shorter. Disable unused skills or plugins to leave more room for the rest.
codex
I’m using the three required verification skills in order: sequential proof checking, reference checking, then strict report synthesis. I’ll keep the review entirely text-based and write the resulting JSON to the exact requested path.
exec
/bin/bash -lc "pwd && sed -n '1,240p' /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/skills/verify/verify-sequential-statements/SKILL.md && sed -n '1,240p' /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/skills/verify/check-referenced-statements/SKILL.md && sed -n '1,280p' /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/agents/skills/verify/synthesize-verification-report/SKILL.md" in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 0ms:
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
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
The required skill instructions are loaded. The proof contains no external-paper citation and no 16-hex fact citation, so the reference-check stage has no references to query; I’m now completing the local logical audit and the hard-prohibition checks.
exec
/bin/bash -lc 'for f in OPERATOR.md ARCHITECTURE.md; do p=$(find /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus -name "$f" -print -quit); if [ -n "$p" ]; then echo "$p"; sed -n '"'1,260p' \""'$p"; fi; done
find /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects -maxdepth 2 -name PROBLEM.md -print 2>/dev/null | head -20' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 783ms:
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/OPERATOR.md
# OPERATOR.md — durable operator profile & standing preferences

> Read by the main agent (codex) at the start of every session — it is NOT
> auto-loaded, so `AGENTS.md` tells the agent to read it. It is the main agent's
> **long-term memory of the operator** —
> the things it learns by asking and must not forget when the session ends. Keep it
> short, factual, current; update in place (no duplicates). **No secrets here**
> (tokens/keys go to `config/*.env`, gitignored). This file is committed.
>
> On a fresh deployment this is the blank template — the `initialize` skill fills it.

## Operator
- **Name / how to address:** _(ask once; fill in)_
- **Language:** _(the language the main agent replies in; code/comments/skills stay English)_
- **Timezone:** _(for scheduling summaries)_

## Standing preferences
- **Notifications:** _(how/where to reach them; what severity warrants a ping)_
- **Spend ceiling (paid backend API):** _(USD; warn before crossing)_
- **worker roster:** _(default `high:3,xhigh:4` — 3 high + 4 xhigh; asked per project at `danus new`)_

## Per-project pointers
_(One line per live project → where its durable facts live. The project's own
problem lives under `runtime/projects/<project>/PROBLEM.md`, not here.)_

## Notes
_(Anything else durable the operator told you: conventions, do/don't, contacts.)_
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/ARCHITECTURE.md
# Danus — Architecture

Danus turns the Rethlas single-problem proof engine (a codex agent plus proving
skills, inherited rather than redesigned) into a multi-agent, long-running,
strategy-steered research system, and renders verified results into papers and
human progress reports. This is the as-built map: the layered model, the folder
layout, the invariants, and the pinned cross-module contracts.

For the main agent's operating contract, see `AGENTS.md`
(→ `agents/contracts/main_agent.md`).

---

## 1. Layered model

```
operator → ① orchestration (main agent + danus CLI)   — conducts, never does math
              ② strategy   (the main agent's own periodic synthesis: elaboration → master_guidance)
              ③ execution  (worker swarm; each round = one codex session running the Rethlas proving skills)
   gm_* │         │ fact_submit
        ▼         ▼
   ⑤ truth      ④ verification (cold-start codex judge; correct ⟺ no critical_errors AND no gaps)
   (fact graph + memory)   — a fact exists iff the verifier accepted it
        ▲
        │ every read/write goes through …
   ⑥ gateway (role-gated MCP: 6 tools; main has NO fact_submit; verifier read-only)

cross-cutting: ⑦ observability (dashboard · theorem-search · human-summary · initialize)
               ⑧ ops/runtime (bootstrap · services · doctor · config)
bottom (inherited, don't redesign): Rethlas proof core = codex + worker proving skills
output: write-paper (publication) · human-summary (progress report) — each rendered by an isolated codex
```

---

## 2. Folder layout

```
Danus/
├─ ARCHITECTURE.md              this file (map + invariants + interface contract)
├─ README.md   pyproject.toml   top-level intro + the installable `danus` package
├─ .gitignore  .codex/          MCP wiring (`config.toml`): the `danus` gateway + the `write-paper` and `human-summary` services
├─ config/                      env templates (BYO key; only *.env.example committed)
├─ danus/                       THE ENGINE (installable Python package)
│  ├─ core/                     ⑤ truth: schema · factgraph · global/local memory · bm25 · glossary
│  ├─ gateway/                  ⑥ role-gated MCP: 6 tools · role table (roles.py)
│  ├─ verify/                   ④ verification HTTP service · prechecks · cold-start codex launcher
│  ├─ execution/                ③ worker swarm: round loop · project/worker lifecycle + layout
│  ├─ orchestration/            ① the `danus` CLI verbs
│  ├─ integrations/             arXiv theorem search (Matlas)
│  ├─ observability/            read-only dashboard
│  ├─ authoring/                shared main-only renderer primitives: the one-shot isolated codex driver + common helpers
│  ├─ write_paper/              write-paper MCP service: assembler + tools (drives `danus.authoring`)
│  └─ human_summary/            human-summary MCP service: scrubbing assembler + tool (drives `danus.authoring`)
├─ agents/                      AGENT CONTRACTS + CODEX-FACING SKILLS (data, not Python)
│  ├─ contracts/                main_agent.md · worker.md · verifier.md
│  └─ skills/
│     ├─ worker/                9 proving skills (inherited from Rethlas)
│     ├─ verify/                3 verify skills
│     └─ write-paper/           paper role prompts + house style (embedded by the write-paper MCP)
├─ .agents/skills/              MAIN-AGENT SKILLS (codex auto-discovers)
│  ├─ elaboration/  human-summary/  initialize/
│  └─ write-paper/              the recipe SKILL.md + driver/ scripts + templates/
├─ bin/                         thin wrappers: danus · danus-mcp · write-paper-mcp · human-summary-mcp · codex
├─ scripts/                     bootstrap · doctor · services · env · setup/check-codex · start-verify/-dashboard · recover · install-tex
├─ docs/                        human docs: getting started · concepts · operating guide · security & trust · …
└─ examples/                    unattended-ops examples + a toy project
```

---

## 3. Design invariants (must not regress)

1. Three memory tiers, one correctness boundary: local (private) → global
   (shared awareness) → fact graph (the only truth). A proof may build only on
   `fact_id`s; global memory is never a correctness source.
2. Permission is enforced by which tools a role can even see (the gateway role
   table), not by prompt convention. `main` cannot `fact_submit`; `verifier` is
   read-only.
3. The verifier is the sole write-gate. A fact exists only if a `correct` verdict
   came back; the gate lives in the `fact_submit` code path, not in prose.
4. Content-addressed, cascade-revocable fact graph. `fact_id` hashes content
   (problem_id + predecessors + glossary_introduces + statement + proof);
   `external_refs` is deliberately excluded so the paper pipeline can rewrite
   citations without breaking the DAG.
5. Autonomy and resumability. Workers run detached; a "round" continues from
   persisted memory rather than adding one increment, so no single crash loses
   verified work.
6. The main agent's own reasoning is the brain. Between rounds the main agent
   reasons over the shared stores itself — optionally spawning exploratory codex
   subagents — distills the project's state into an `elaboration`, and writes the
   direction it decides on as the swarm's `master_guidance`. This periodic steer
   is not optional — it is how the swarm gets steered.
7. Portable and BYO. No hardcoded absolute paths, no committed secrets; keys come
   from gitignored `config/*.env` (templates committed as `*.example`).
8. Clean author context. Any agent that produces an artifact for an outside
   audience (a paper, a human report) is a fresh isolated codex fed a scoped,
   machinery-free prompt, never the orchestrator's own contaminated window. It
   cannot leak `fact_id`s or swarm vocabulary it never received.

---

## 4. Interfaces & ports — the coordination contract

> **Rule:** these rows are the seams where two modules meet. If a change touches a
> row, update both ends in the same change. Ports and contract shapes are pinned:
> one side must treat the other's contract as fixed, and must not change a port or
> interface unilaterally.

**Network ports (loopback — do not renumber):**

| port | service | producer → consumer |
|---|---|---|
| 8091 | verify `/verify`, `/health` | `danus.gateway` `fact_submit` → `danus.verify` (via `DANUS_VERIFY_URL`) |
| 8099 | dashboard | operator browser → `danus.observability` (read-only) |

**Cross-module contracts (both ends must agree):**

| contract | pinned shape | ends |
|---|---|---|
| MCP tool set + role gating | 6 tools; `roles.py` `ROLE_TOOLS` (main has NO `fact_submit`; verifier read-only) | `danus.gateway` ↔ worker/main/verifier agents |
| MCP launch | `python -m danus.gateway` + `DANUS_ROLE` env | `danus.verify` launcher · worker `.codex/config.toml` · `.codex/config.toml` (main) → `danus.gateway` |
| verify HTTP | `POST /verify {statement,proof}` → `{verification_report,verdict,repair_hints}`; verdict ⟺ no critical_errors & no gaps | `danus.gateway.fact_submit` ↔ `danus.verify` |
| fact id inputs | `problem_id + sorted(predecessors) + sorted(glossary) + normalized(statement,proof)`; **external_refs EXCLUDED** | `danus.core` ↔ everyone (write-paper reads `external_refs`) |
| global-memory kinds | the 11 `GLOBAL_KINDS` (incl. `master_guidance`/`elaboration`/`verification`) | `danus.core` ↔ agents |
| write-paper prompt assets | codex role prompts + style read from `agents/skills/write-paper/` (via `DANUS_WRITE_PAPER_SKILL_DIR`) | `danus.write_paper` assembler ↔ `agents/skills/write-paper/` |
| env-var contract | `DANUS_* / CODEX_* / VERIFY_*` names; the codex CALL + env (bin/model/effort/PATH/`exec` prefix) is resolved through the shared `danus.codex` launcher: neutral `DANUS_CODEX_BIN` / `DANUS_MAIN_MODEL` / `DANUS_MAIN_EFFORT` (back-compat aliases `DANUS_CODEX_MODEL` / `DANUS_CODEX_EFFORT`) + `DANUS_WORKER_MODEL` for workers + per-service `DANUS_{VERIFY,WRITE_PAPER,HUMAN_SUMMARY}_{MODEL,EFFORT}` overrides | `danus.codex` + `config/` + `scripts/env.sh` ↔ every codex-exec site (`danus.execution.loop` · `danus.verify.launcher` · `danus.authoring.driver`) |
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/baseline_a_divisibility_by_6/PROBLEM.md
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/baseline_a_odd_sum/PROBLEM.md
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/baseline_a_triangular_sum/PROBLEM.md
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/n15_putnam_2023_b1/PROBLEM.md
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/n15_putnam_2024_a1/PROBLEM.md
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/n15_putnam_2024_a2/PROBLEM.md
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/n15_putnam_2024_b2/PROBLEM.md

exec
/bin/bash -lc 'rg -l -F "Two convex quadrilaterals are called partners" /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/*/PROBLEM.md 2>/dev/null' in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 0ms:
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/n15_putnam_2024_b2/PROBLEM.md

exec
/bin/bash -lc "sed -n '1,260p' /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/projects/n15_putnam_2024_b2/PROBLEM.md" in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 0ms:
Two convex quadrilaterals are called partners if they have three vertices in common and they can be labeled \(ABCD\) and \(ABCE\) so that \(E\) is the reflection of \(D\) across the perpendicular bisector of the diagonal \(AC\). Is there an infinite sequence of convex quadrilaterals such that each quadrilateral is a partner of its successor and no two elements of the sequence are congruent?

codex
The sequential audit passes: the common center \(O\) is preserved at every partnership step, both finite multisets are genuinely invariant, and the circle-intersection argument gives a finite upper bound for every ordered assignment. No hard prohibition is triggered, and the statement is self-contained. I’m synthesizing a zero-finding verdict and persisting it now.
exec
/bin/bash -lc "test -d /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173 && if [ -e /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json ]; then sed -n '1,200p' /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json; fi" in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 0ms:
apply patch
patch: completed
/mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
diff --git a/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..a74bf6af0ce6f062f4bae62c7be99a837ec222ec
--- /dev/null
+++ b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

diff --git a/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..a74bf6af0ce6f062f4bae62c7be99a837ec222ec
--- /dev/null
+++ b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

exec
/bin/bash -lc "sed -n '1,240p' /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json" in /mnt/c/Users/wmywb/PycharmProjects/Noespire/baselines/danus/danus/verify/agent
 succeeded in 0ms:
{
  "verification_report": {
    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}

diff --git a/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..a74bf6af0ce6f062f4bae62c7be99a837ec222ec
--- /dev/null
+++ b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

codex
{
  "verification_report": {
    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}
diff --git a/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
new file mode 100644
index 0000000000000000000000000000000000000000..a74bf6af0ce6f062f4bae62c7be99a837ec222ec
--- /dev/null
+++ b/runtime/verify-runs/20260828T121403Z_07e8db527173/verification.json
@@ -0,0 +1,9 @@
+{
+  "verification_report": {
+    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
+    "critical_errors": [],
+    "gaps": []
+  },
+  "verdict": "correct",
+  "repair_hints": ""
+}

tokens used
42,152
{
  "verification_report": {
    "summary": "The proof is correct and complete. It shows that the intersection O of the perpendicular bisectors of the diagonals is preserved by every partnership step, and consequently both the multiset of vertex distances from O and the multiset of side lengths are invariant. For each ordering of these two finite multisets, fixing O and one vertex leaves at most two choices at each of the next three circle-intersection steps, so only finitely many configurations, hence finitely many congruence classes, can occur. This rules out an infinite sequence of pairwise noncongruent quadrilaterals. No external references or internal fact citations require checking, and no hard prohibition is triggered.",
    "critical_errors": [],
    "gaps": []
  },
  "verdict": "correct",
  "repair_hints": ""
}
