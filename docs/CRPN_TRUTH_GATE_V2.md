# CRPN statement-first truth gate

CRPN now places a fresh closed-book statement sanity call before each Fact-producing proof verification. The gate receives only the mechanically prepared full statement, ambient scope, and exact accepted predecessor statements. Candidate proof, research notes, old acceptance and externally discovered counterexamples are excluded. Existing proof-verifier prompt/schema and domain-specific bridge/representation checks remain intact.

The first call attempts concrete falsification, including relevant boundaries, degeneracy, strictness, concentrated parameters, domains and quantifiers. A structured concrete counterexample denies the candidate and skips proof verification. Uncertainty may proceed to the separate proof verifier. Neither lack of a counterexample nor sanity rejection creates truth or a Refutation. Acceptance requires both completed sanity evidence without a concrete contradiction and proof acceptance.

Ordinary FACT/SUPPORT/COMPOSE, explicit and loop Fact bridges, representation transport, conditional transport and deferred activation share `StatementSanityGate`. Frozen legacy/product verifiers do not opt into the new CRPN gate. Existing Refutation verification remains separate.

Immutable `statement_sanity_input.json` and `statement_sanity.json` bind the exact candidate and local interfaces; invocation request/result journals retain raw calls. Sanity or proof timeout produces local unverified failure with unknown usage retained. Corrupt saved sanity evidence is a control-plane stop. Confirmed calls replay from their exact journals. A new bridge has three accounted calls at most (Worker, sanity, proof); no hidden compute or extra Worker retry. Old bridge runtime fingerprints and budgets are not rewritten.

Revoked Fact identities cannot be re-admitted, including from cached proof PASS. An illegal active copy cannot override a tombstone on read. Existing cascade revocation retains proof bytes and lineage bindings; CRPN derives OPEN when its last accepted Fact is revoked. This change does not implement a new revocation transaction protocol.

## Validation protocol

Deterministic tests exercise proof blinding, asymmetric veto, uncertainty, malformed response, timeout, scope/predecessor binding, all existing admission paths, crash recovery, and revoked replay. `tests/fixtures/truth_gate_regression.json` freezes seven mathematical interfaces before live calls: three historical accepted controls, the actual false candidate, and three adversarial variants. Oracle labels and variant explanations never enter model packets. These fixtures test protocol mechanics; deterministic model stubs do not establish mathematical detection performance.

One bounded live regression batch will check the three controls with sanity then the original proof audit, and the three variants with sanity only. Each receives a single fresh call per applicable role, with no repair/resampling. The actual false candidate is evaluated only once, at the start of the derivative autonomous run, reusing its confirmed Worker result. No known counterexample hint enters that packet. Failure, false alarm, timeout and unknown usage are reported without retuning.

The derivative starts from rp2's last pre-admission mathematical state, reconstructed against rp1 and frozen visit 27 evidence. The original post-admission verifier, receipt, Study feedback and polluted visit 28 selections remain historical, not active recovery results. All inherited computation remains in the origin ledger and cost report. The run proceeds under the existing two-complete-epoch observer, stopping early only on target solved, explicit user pause, or the first new truth/infrastructure blocker. No live patch, scheduler change, forced Study, mathematical hint, or push.

The new pass reduces proof-induced anchoring but is still LLM verification, not a soundness guarantee or a formal kernel.
