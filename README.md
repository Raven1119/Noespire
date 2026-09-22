# Noespire

CRPN research strategy on the pinned DANUS substrate. Read
[Architecture](ARCHITECTURE_AFTER_REFACTOR.md) and [Authority migration report](CRPN_AUTHORITY_MIGRATION.md).

```text
Claim / Study -> CRPN 3:1:1 selection -> DANUS persistent worker lane
 -> fresh VerifierBackend -> CRPN admission -> Claim proofs / Support certificates
 -> Support / frontier / representation strategy -> further research
```

The sole truth authority is the CRPN AND/OR graph in `crpn.json`. There is one invocation
lifecycle. Local and global memory are unverified. A Support certificate establishes
an implication, not its conclusion. Aliases do not discharge Claims. LLM-verified
Facts are not kernel-checked theorems.

## Install and run

```powershell
python -m pip install -e .
python -m crpn init workspaces/new --problem-id problem --statement-file problem.txt
python -m crpn status workspaces/new
python -m crpn run workspaces/new
python -m crpn pause workspaces/new
python -m crpn resume workspaces/new
python -m crpn export workspaces/new
```

Real calls require Docker, the existing `noespire-codex-isolated:local` image and
Codex credentials. No host-execution fallback. Each call is Sol/xhigh/600s; the
research lifetime has no cumulative attempt, timeout or no-progress stopping budget.
Pause is cooperative. Model-generated metadata cannot acquire truth authority.

## Import frozen mathematical state

```powershell
python -m crpn migrate FROZEN_OLD_WORKSPACE FRESH_DESTINATION
```

The importer checks hashes, retains evidence/Claim/Support IDs, preserves source
bytes and explicit maps, keeps revoked closures invalid, and imports research
into DANUS memory. It creates a new run; historical invocation bookkeeping is
provenance, never a resumed old runtime fingerprint. Never import into the source.

## Verify

```powershell
python -m pytest -q tests/crpn
python -m pytest -q vendor/danus/danus/core/tests vendor/danus/danus/execution/tests/test_durable.py vendor/danus/danus/gateway/tests/test_submission_recovery.py
```

The no-model Docker permission check is opt-in with `DANUS_RUN_DOCKER_PROBE=1`:

```powershell
$env:DANUS_RUN_DOCKER_PROBE="1"
python -m pytest -q vendor/danus/danus/execution/tests/test_isolation.py
```
Runtime evidence stays in ignored workspaces.

## Historical code

The previous CRPN and v3 application are preserved in Git at
`0b68c6c138364d12b4adbd6b5aa335c013171f9f` and the existing frozen worktree. They are
not imported by this package. Historical experiments and frontend use that checkout;
the new research runtime is not frontend-wired. Older docs retain dated design history.
The frozen `noespire-proof-core-v3` tag is unchanged. Lean remains deferred.
