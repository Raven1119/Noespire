# danus/execution — the worker swarm (round loop + scaffolding + layout)

Where autonomous `codex` workers actually prove. This module owns the on-disk
**layout**, project/worker **scaffolding**, and the per-worker **round loop**. The
`danus` CLI (`danus/orchestration`) is a thin UX layer over this; the real lifecycle
lives here.

```
danus/execution/
  layout.py     paths + names; WorkerLayout; parse_roles("high:3,xhigh:4")
  scaffold.py   do_new (project + worker dirs, .codex config, symlinks), spawn_loop
  loop.py       the round loop: kickoff prompt, run_round, stop conditions, status
  __main__.py   `python -m danus.execution <worker_dir>` → loop.main
  tests/{test_execution.py, test_loop.py}
```

## On-disk layout (`layout.py`)

`<agents_root>/<project>/` holds the shared `global_memory/` + `fact_graph/` +
`project.json`; each `workers/<worker>/` is a codex cwd with `AGENTS.md` →
`agents/contracts/worker.md`, `.agents/skills` → `agents/skills/worker`, a
`.codex/config.toml` (MCP = `python -m danus.gateway`, `DANUS_ROLE=worker`,
`DANUS_VERIFY_URL`, `tool_timeout_sec=3600`), `TASK.md`, `local_memory/`, and the
control files (`.status.json` `.pid` `.stop` `logs/`). `agents_root` =
`DANUS_AGENTS_ROOT` (default `runtime/projects`).

## The round loop (`loop.py`)

A **round = one `codex exec` continuation session** that resumes from persisted
memory (NOT one increment). Launched detached in its **own process group**
(`start_new_session`), so it survives your shell and `stop --force` can `killpg` the
loop + its codex child. Stop conditions checked at the round boundary: `.stop` flag,
`.run_deadline`, `DANUS_MAX_ROUNDS` (0 = unlimited), `DANUS_MAX_CONSEC_FAILURES`
(5). Config read at call time (`DANUS_ROUND_HARD_TIMEOUT` 4h, `DANUS_ROUND_BEAT` 5s).
`.status.json` is written atomically. **Resumability is continuity in the stores**,
not process state — a fresh `start` rebuilds context from memory + the fact graph.

## Connects to

Reads `TASK.md` (from `danus assign`) + `master_guidance` (the main agent's own
periodic direction). Writes facts
only via a worker's `fact_submit` (gateway → verify). The loop itself never writes
the truth stores — it only scrapes the resulting `fact_id` from the round log for
status.

## Tests

`python -m pytest danus/execution/` (offline; a fake codex stub drives the loop /
stop / scaffolding).


## Isolated durable deployment (downstream patch)

Install `pip install -e 'vendor/danus[execution]'` (or the equivalent uv command).
`DurableRounds(..., runner=DockerRoundRunner(...))` uses the existing
`run_round` process lifecycle, with a Docker command factory. The runner requires
Docker, a prebuilt Codex image and `auth.json`; it never falls back to native
Windows execution or an unrestricted host process. Defaults remain Sol/xhigh and
600 seconds in the durable API. Use the runner's `fingerprint()` as part of the
application runtime fingerprint.

`DockerRoundRunner(tools=lambda worker, role: [...])` receives only trusted,
host-bound `CapabilityTool(name, description, input_schema, call)` definitions.
The adapter owns lane/problem/scope checks. The generic broker checks a fresh
per-invocation bearer capability, the method/name allowlist, self-contained JSON
Schema arguments, and a 2 MiB message ceiling. There is no arbitrary filesystem,
URL, shell or graph capability. Pass an empty list for a proof-only verifier.

Each container sees only a fresh `/work` stage plus read-only auth and sanitized
provider configuration. No project/worker/FactGraph directory or Docker socket
is mounted. Local/shared memory remains on the host and is accessible only
through explicitly granted tools. Provider credentials are never copied into
runtime evidence. Host hooks, MCP servers, instructions, trust and plugins are
not inherited. The image is pinned by its inspected digest.

The container filesystem is read-only except the fresh stage and tmpfs. Inside
it Codex's `:read-only` permission profile also denies command network access;
MCP runs outside that command sandbox and can reach only the authenticated host
broker. Web/browser/apps/multi-agent surfaces are disabled. Nested bubblewrap
requires `seccomp=unconfined` and SETUID/SETGID/SETFCAP for UID mapping on this
image; the container is not privileged and has no SYS_ADMIN capability. These
settings are a tested deployment requirement, not a claim of universal kernel
sandbox equivalence.

The host streams public process output straight into DANUS's exclusive round
log. A returned response artifact is copied before stage cleanup, including
unconfirmed timeout output; only `DurableRounds` assigns completion authority.
Timeout/exception cleanup removes the container. A same-timeout container
watchdog bounds an orphan after abrupt host death; a request without a receipt
still resumes as INTERRUPTED, never silently reruns. Complete tool writes made
before interruption persist in the actual host memory backend.

No-model permission test (explicit opt-in):

```
DANUS_RUN_DOCKER_PROBE=1 python -m pytest danus/execution/tests/test_isolation.py
```

It checks inaccessible host truth, read-only credentials, denied unauthenticated
broker access, allowlisted local-memory persistence, absence of a truth-mutating
tool, and sandbox write/network denial. It does not call a model or claim
mathematical correctness.
