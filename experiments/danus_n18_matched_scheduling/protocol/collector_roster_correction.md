# Pre-valid-run completion collector correction

The first attempted pair, Arm A / `vieta-jumping-square`, launched the frozen seven identical workers concurrently. All seven reached `max_rounds` with `last_rc=0`, but the experiment controller continued waiting because it imported `experiments.danus_n16_blind.run_once::worker_statuses`. That helper enumerates the historical `high:3,xhigh:4` names and therefore returned only `high`, `high2`, and `high3` for the N1.8 `high:7` roster.

The controller was interrupted rather than waiting for its 15,000-second collector timeout. Its verifier was terminated, all project and verifier evidence was preserved without nested `.agents`, `.git`, `.lake`, or `__pycache__`, and the attempt is `SYSTEM_INVALID_RUN`; none of its mathematical output enters N1.8 metrics.

The correction replaces the imported enumerator with a local reader over the exact worker tuple from the freshly created project's frozen metadata. A red/green regression covers `high` through `high7`. It changes no problem, prompt, model, effort, tools, verifier, arm order, launch batch, timeout, or scheduling semantics. Per the frozen protocol, exactly one valid replacement of this pair is allowed.
