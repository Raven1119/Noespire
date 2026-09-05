# Repository contents

Commit application/research source, reusable experiment drivers, deterministic
tests, and maintained architecture/development documentation. The
`experiments/` directory contains reusable verifier and orchestration code,
so it is not ignored as a whole.

Keep generated runs, workspaces, invocation records, evidence, logs, cached
outputs, and reports about individual runs outside new commits. `.gitignore`
covers the output directories; it does not remove files from existing
commits. Never delete local evidence merely to obtain a clean Git status.

Historical development documents can mention locally archived reports.
Those reports are not prerequisites for the deterministic test suite.
Frozen replay scripts do require their original local inputs; their absence
in a source checkout does not authorize substituting fabricated experiment
evidence or automatically running new model calls.

Run deterministic regression tests with `python -m pytest tests -q`.
Test fixtures construct synthetic graphs and rejected attempts in temporary
directories. They exercise the same copy, scheduling, admission, and lineage
interfaces without depending on an archived research run.

When local unpushed commits already contain outputs, adding an ignore rule
alone will not exclude those outputs from a push. Preserve that local branch
and its evidence, prepare a source-only commit from the destination remote
tip, and check the outgoing commit's contents and ancestry before a normal
fast-forward push. Frozen tags and existing commits must remain unchanged.
