# P6-A usage-limit invalidation

The first `eulerian-circuit` Arm A attempt (`eulerian-circuit_20260829T195223Z`) is
excluded as `SYSTEM_INVALID_RUN`.

Worker `high` completed its only round with `last_rc=1`. Its preserved raw round log
contains an explicit Codex usage-limit error after it had submitted work and was polling
the verifier. This is an execution-service failure, not a verifier rejection or a
mathematical failure. The other six workers' verifier artifacts are preserved, but no
partial metrics from this invalid batch enter the matched comparison.

The frozen protocol permits one valid replacement for an environment-invalid
`(problem, arm)` pair. No valid P6-A result existed before that replacement.
