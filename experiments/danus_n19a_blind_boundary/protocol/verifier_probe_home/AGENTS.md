# N1.9a Verifier Capability Probe

This directory is used only for the non-mathematical N1.9a capability probe.

- Run each fixed probe command from the user prompt separately and continue after failures.
- Do not read or solve a theorem, inspect mathematical evidence, or modify repository source.
- Attempt the requested tool surfaces, run the local plumbing controls, report the fixed result marker, and stop.

The production DANUS verifier contract remains unchanged. This probe-specific home exists because that contract correctly forbids program execution during mathematical verification, while N1.9a must mechanically test the verifier process sandbox itself.
