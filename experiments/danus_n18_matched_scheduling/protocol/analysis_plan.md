# N1.8 Frozen Analysis Plan

Primary endpoints are solve rate; total tokens, workers, verifier calls, and outside-closure Fact ratio; and both first-target latency and terminal wall clock. Tokens are never estimated.

For Arm C, a worker-1 failure followed by success at index greater than one is a `SEQUENTIAL_RECOVERY`. If worker 1 passes all six, sequential recovery is explicitly untested.

Use exactly one verdict:

1. `SEQUENTIAL_RECOVERY_SUPPORTED` when B/first-worker failures are recovered later by C, preferably on two problems, C solves at least as many as B, and C uses less expected compute than A.
2. `PARALLEL_REDUNDANCY_SUPPORTED` when A solves a problem C fails or other clear matched robustness evidence favors parallel execution, with cost and latency reported.
3. `SINGLE_WORKER_SUFFICIENT_ON_SET` when B solves 6/6, every C worker 1 solves, and A has no extra solve benefit.
4. `MATCHED_DEMAND_DRIVEN_SUPPORTED` when B or C approximately matches A's solve rate and materially reduces workers or tokens, but the stricter single-worker or sequential-recovery gate does not apply.
5. `INCONCLUSIVE` only for integrity failure, invalid sample, runtime mismatch, or incomplete valid arms.

“Materially” is frozen as at least a 50% reduction in total launched workers or total tokens relative to A. Descriptive differences smaller than this are reported without promotion.
