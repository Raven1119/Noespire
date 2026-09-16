# Noespire CRPN on DANUS

Read ARCHITECTURE_AFTER_REFACTOR.md and MIGRATION_AUDIT.md for the active boundary.
Current execution: `python -m crpn`. CRPN owns Claims/Supports/Studies and strategy;
vendored DANUS owns Facts, three-tier memory, retrieval, invocation and processes.

- Preserve the upstream commit/license and document every vendor patch.
- Do not import the retired `research` / `application` runtime into the new path.
- Only DANUS FactGraph is verified truth. All action notes/cards/summaries are derived
  or unverified. Never infer truth from memory, alias, Support readiness or graph depth.
- All fact writes go through SubmissionGate + a fresh VerifierBackend, except the
  explicit provenance-checked legacy importer. Never silently revive revoked Facts.
- Exact ambient scope and actual accepted predecessor closure remain mandatory.
- Keep 3:1:1 and fixed REVISIT semantics. Notes/inspection/bridge do not count as Study service.
- Runtime/model drift fails closed; reuse confirmed DANUS round results; never guess
  that an interrupted call completed. Missing usage remains unknown.
- Normal model execution requires the DANUS Docker capability runner, with no host fallback.
- New experiments use GPT-5.6 Sol / xhigh / 600 seconds unless explicitly varied.
- No skills (user instruction). Independent investigation/review may be delegated.
- Test changed behavior through the public path; tests/crpn plus relevant vendor tests.
- Keep historical evidence read-only. Commit only authorized source/tests/docs, never
  runtime workspaces. No push without explicit authorization.

Legacy implementation and product are frozen at
0b68c6c138364d12b4adbd6b5aa335c013171f9f. Use a detached checkout at that SHA for
historical execution; it is deliberately not installed beside the new runtime.
Lean remains deferred; LLM verification is not a mathematical kernel.
