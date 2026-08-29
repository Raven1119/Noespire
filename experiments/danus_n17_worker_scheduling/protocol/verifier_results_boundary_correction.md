# N1.7 Verifier Results Boundary Correction

Status: **FROZEN BEFORE FIRST VALID RUN**

## Excluded Attempt

`arm_b_single/cubic-form-image_20260829T150856Z` is `SYSTEM_INVALID_RUN`. Four completed verifier requests wrote mathematically correct verdict files but returned HTTP 500, so no Fact was promoted. A fifth request was terminated after the invalid condition was already conclusive and the unchanged worker began an out-of-scope decomposition response.

All run artifacts are preserved. The five launcher logs that were misdirected into the nested DANUS source tree were copied byte-for-byte to the invalid run's `misdirected_verifier_outputs/`; source/copy SHA-256 multisets matched before the generated source directory was removed.

## Root Cause

The frozen DANUS launcher defaults `VERIFIER_RESULTS_DIR` to `danus/verify/runs` when the environment variable is absent. The N1.6 blind wrapper grants verifier writes only to the intended external runtime location `baselines/danus/runtime/verify-runs`. This shell did not carry the ambient variable used by the earlier N1.6 execution, so the verifier wrote outside its allowed scope and Codex exited nonzero during sandbox completion.

## Correction

The experiment harness now explicitly sets:

```text
VERIFIER_RESULTS_DIR=<frozen DANUS>/runtime/verify-runs
```

This makes the launcher output path equal to the wrapper's already-frozen verifier write scope and to the location used by artifact capture. No worker count, order, role, reasoning effort, assignment, prompt, theorem, timeout, verifier behavior, Fact Graph behavior, or scheduling decision changed.

The regression test `test_verifier_results_are_pinned_to_the_wrapper_write_scope` failed before the correction and passes after it. The canonical N1.6 real-role capability probe already verifies that this exact runtime directory is writable by the verifier and not by workers.
