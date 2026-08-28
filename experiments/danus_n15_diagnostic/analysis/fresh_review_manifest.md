# Fresh offline review manifest

## Execution boundary

- executed after all four DANUS runs completed
- mechanism: three independent Codex subagent sessions
- context isolation: `fork_turns=none`
- model: `gpt-5.6-sol`
- reasoning effort: `xhigh`
- repository access instruction: read only the named review packet; inspect no other file
- hypothesis disclosure: none
- mutation permission: write only the named review output
- outputs: the complete final YAML responses are persisted beside this manifest

## Review invocations

| Session task | Only input packet | Output |
| --- | --- | --- |
| `n15_review2_b2_intermediate` | `review_packets/b2_high2_intermediate.md` | `fresh_review_b2_high2_intermediate.md` |
| `n15_review2_b1_high_cost` | `review_packets/b1_high_cost.md` | `fresh_review_b1_high_cost.md` |
| `n15_review2_b2_reuse` | `review_packets/b2_xhigh3_reuse.md` | `fresh_review_b2_xhigh3_reuse.md` |

Each session received this instruction, with the paths substituted from the table:

> You are a fresh offline diagnostic reviewer. Read ONLY `<input packet>`; do not inspect any other repository file and do not infer a desired experiment outcome. The packet contains the original theorem, local premises, actual persisted worker attempt evidence, verifier result, and necessary local trace. Produce the required YAML classification exactly as requested. Write it to `<output>`. Do not modify anything else. Then report completion.

The orchestrator records no hidden chain of thought. The persisted YAML is the reviewer's complete deliverable used in the diagnostic report.
