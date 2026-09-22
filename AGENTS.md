# Noespire CRPN on DANUS

Read ARCHITECTURE_AFTER_REFACTOR.md and MIGRATION_AUDIT.md for the active boundary.
Current execution: `python -m crpn`. CRPN owns Claims/Supports/Studies and strategy;
CRPN also owns every proof and mathematical transition. DANUS owns only generic
memory, BM25, IO, capability transport, invocation and processes.

- Preserve the upstream commit/license and document every vendor patch.
- Do not import the retired `research` / `application` runtime into the new path.
- Only CRPN crpn.json is mathematical authority: Claims own proofs/refutations and
  Supports own conditional/representation certificates. Memory/cards are unverified.
  Never infer truth from alias, Support readiness, depth or a submission receipt.
- All new proof writes go through crpn.admission.Admission + a fresh VerifierBackend;
  explicit provenance-checked migration imports history without reverification.
  DANUS FactGraph/SubmissionGate/native main must never run on CRPN workspaces.
  Never discard proof history, transfer ownership, or revive revoked evidence.
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
