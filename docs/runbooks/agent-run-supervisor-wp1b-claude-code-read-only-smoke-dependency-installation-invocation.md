# WP1b — Claude Code read-only smoke dependency, installation, and invocation notes

Date: 2026-06-14
Status: documentation prerequisite for the separately approved WP1b single local smoke
Scope: local/offline only; no Gateway, Feishu, live surface, production config, or real delivery

## Purpose

This note records the concrete dependency surface for the WP1b Claude Code
read-only one-shot smoke in Sachima's `agent-run-supervisor` integration line.
It is intentionally narrow: it documents `acpx` and `agent-run-supervisor`
provisioning, version pins, and call shape so future operators do not confuse a
missing `PATH` entry with permission to use `npx` or a network fetch fallback.

The committed Sachima role remains non-runnable by construction:

- `sachima_supervisor/roles/claude_code_read_only_reviewer_v1.json`
- `runner.acpx_binary: null`
- `runner.type: acpx`
- `runner.acpx_version: 0.12.0`
- `runner.adapter_agent: claude`
- `session.strategy: exec`

A real local smoke requires a host-local, out-of-tree role overlay that sets
`runner.acpx_binary` to a verified absolute local executable path. That host
path must not be committed into the portable role file.

## Dependency inventory

| Component | Kind | Required for WP1b | Current pin / contract | Notes |
|---|---|---:|---|---|
| `acpx` | Node CLI package | Yes | `0.12.0` exactly | Must be a local executable path in `runner.acpx_binary`; no `npx`/network fetch fallback. |
| Node.js | Runtime for `acpx` | Yes | `agent-run-supervisor doctor` reports `>=22.12`; Sachima root package requires `>=20.0.0` | Current smoke host probe observed `v24.14.0`. |
| `agent-run-supervisor` | Python package (PyPI) | Yes | exact pin `0.1.4` | Declared as the exact-pinned `agent-run-supervisor` optional extra in Sachima's `pyproject.toml` (mirrored into `dev`); provision via `uv sync --extra agent-run-supervisor` (or `--extra dev`) and imported lazily behind default-off gates. No source-checkout / `PYTHONPATH` path is valid. |
| Python | Runtime for Sachima + supervisor | Yes | Sachima `>=3.11,<3.14`; supervisor `>=3.11` | Current smoke host probe observed Python `3.11.15`. |
| Claude Code CLI | Adapter target via `acpx claude` | Yes | local CLI availability required | Current smoke host probe observed `claude` version `2.1.177`. |

## `acpx` provisioning contract

### Current admitted local runner contract

After the acpx 0.12.0 contract refresh, Sachima admits only host-local overlays
that pin a verified absolute `acpx` 0.12.0 executable. Historical 0.10.0 smoke
paths and digests remain historical evidence only; they are not valid current
operator inputs for this gate.

No committed path or sha256 is authoritative here. A smoke host must provision a
fresh local executable outside the repo, record `acpx --version`, `realpath`, and
sha256 evidence, then set the out-of-tree role overlay's `runner.acpx_binary` to
that absolute path. The fact that `acpx` is not on `PATH` is not a blocker; the
controlled-exec provenance gate requires an absolute `runner.acpx_binary` anyway.

### Fresh-host installation shape

Installing `acpx` is a separate host provisioning action, not part of a
`no-network-fetch` smoke run. On a fresh host, provision it before the smoke and
record version + digest evidence:

```bash
npm install \
  --prefix sachima_supervisor/roles/local/npm-acpx-0.12.0 \
  --save-exact --no-audit --no-fund acpx@0.12.0

ACPX="$PWD/sachima_supervisor/roles/local/npm-acpx-0.12.0/node_modules/.bin/acpx"
"$ACPX" --version
realpath "$ACPX"
sha256sum "$(realpath "$ACPX")"
```

The smoke itself must then use that local absolute path. It must not run:

- `npx -y acpx@0.12.0 ...`
- `npm exec acpx ...`
- `pnpm dlx acpx ...`
- `yarn dlx acpx ...`
- `bunx acpx ...`
- shell wrappers such as `sh`, `bash`, or generated scripts that hide the true runner

The Sachima provenance gate enforces the same posture: absolute path, no
whitespace, forbidden package-runner/shell basenames rejected, role-file digest
bound before launch.

## `agent-run-supervisor` provisioning contract

`agent-run-supervisor` is an independent external Python project published to
PyPI (canonical repo: `https://github.com/jovijovi/agent-run-supervisor`). It
is declared in Sachima's `pyproject.toml` as the exact-pinned optional extra
`agent-run-supervisor` (and mirrored into `dev` so CI installs it):

```text
package: agent-run-supervisor
import_name: agent_run_supervisor
exact pin: 0.1.4
provisioning: uv sync --extra agent-run-supervisor   (or --extra dev)
resolution: uv.lock (registry source + sdist/wheel hashes)
```

Sachima consumes it ONLY as this installed distribution: there is no
source-checkout, `PYTHONPATH`, or `sys.path` channel anywhere in the repo
(`tests/test_packaging_metadata.py::test_no_agent_run_supervisor_source_path_references`
guards this), so a checkout can never shadow the reviewed pin.

Sachima's pin checker is:

- `sachima_supervisor/supervisor_library.py`
- expected import: `agent_run_supervisor`
- expected distribution: `agent-run-supervisor`
- expected exact version: `0.1.4` (mirrors the pyproject extra; drift fails
  `tests/test_packaging_metadata.py`)

This checker is deliberately not a hard import at module load time. Sachima's
local/offline seam imports the supervisor lazily only when an approved invocation
path needs it, so normal Sachima imports and tests do not require the supervisor
package to be installed; without it, consumers fail closed with stable codes
(`supervisor_library_unavailable` / `live_progress_unavailable`).

### Installed distribution invocation

With the extra installed, invoke the supervisor CLI through the project
environment — no `PYTHONPATH`:

```bash
uv sync --extra agent-run-supervisor   # or: uv sync --extra dev
uv run python -m agent_run_supervisor doctor
uv run python -m agent_run_supervisor validate-role <role-file>.json
uv run python -m agent_run_supervisor run \
  --role <role-file>.json \
  --prompt-file <prompt>.txt \
  --runs-dir <runs-dir>
```

### Validating unreleased agent-run-supervisor changes

The only sanctioned way to test an unreleased ARS change against Sachima is to
build and **install** it as a package into an isolated, throwaway environment —
never to reference its source tree:

```bash
# In the agent-run-supervisor repo: build a wheel.
uv build

# In a disposable environment (NEVER the Sachima project env — uv.lock and
# --frozen semantics stay authoritative there):
uv venv /tmp/ars-preview
VIRTUAL_ENV=/tmp/ars-preview uv pip install <path-to-built-wheel>
# (an editable install of the ARS repo into that same disposable env is
# equally acceptable — both go through packaging metadata)
```

`check_supervisor_library_pin` reports such environments honestly
(`supervisor_library_version_mismatch` / `..._version_unknown`); gates that
require `ready` are expected to fail there — that is by design, never
special-cased. Forbidden in every environment: `PYTHONPATH` pointing at an ARS
source tree, `sys.path` insertion, or installing an unpinned version into the
Sachima project environment.

## Sachima call path

The integration is caller-owned and local/offline:

1. Sachima/FlowWeaver durable state validates the operator gate, lease, state
   version, role allowlist, role digest, prior dry-run evidence digest, and
   read-only constraints.
2. A host-local role overlay supplies the verified `runner.acpx_binary` absolute
   path while preserving the committed role's ID, adapter, permissions, limits,
   and `session.strategy: exec` shape.
3. Sachima calls `agent_run_supervisor.caller.invoke_caller(...)` through the
   local/offline boundary using `CallerInvocationSpec`.
4. `agent-run-supervisor` loads the `AgentRoleSpec`, compiles an argv list, and
   supervises the local process. It writes redacted local artifacts and returns a
   supervisor status. It never returns a business verdict; `business_verdict`
   remains `null` and caller-owned.

For the WP1b Claude read-only one-shot role, the effective `acpx` argv shape is:

```text
<absolute-acpx-binary>
  --format json
  --json-strict
  --suppress-reads
  --timeout 900
  --max-turns 8
  --cwd <approved-local-cwd>
  --permission-policy <default-deny-json-policy>
  --non-interactive-permissions fail
  --no-terminal
  claude exec <prompt>
```

The permission policy is generated from the role:

```text
defaultAction: deny
autoApprove: read, search
autoDeny: delete, edit, execute, fetch, move, other, switch_mode
```

The command is compiled as an argv list, not a shell string.

## WP1b hard boundaries

The dependency setup above does not approve any of the following:

- write-capable Claude or Codex roles
- additional real local smokes beyond the single approved WP1b run
- persistent or unbounded sessions
- cancellation execution
- Satine/Hermes-profile ACP execution
- controlled AI FLOW execution
- Gateway involvement or mutation
- Feishu/IM delivery
- public ingress
- production config writes
- live/default-on behavior
- real delivery

## Operator verification checklist

Before a WP1b smoke, verify and record sanitized evidence:

```bash
ACPX=/home/ecs-user/workspace/hermes/worktrees/sachima/phase-d-smoke-host-provisioning-dor/sachima_supervisor/roles/local/npm-acpx-0.12.0/node_modules/.bin/acpx

test -x "$ACPX"
"$ACPX" --version              # must be 0.12.0
realpath "$ACPX"
sha256sum "$(realpath "$ACPX")" # record in the operator evidence packet

node --version
python3 --version
claude --version

uv run python -m agent_run_supervisor doctor
uv run --frozen python - <<'PY'
import importlib.metadata as md
print(md.version('agent-run-supervisor'))  # must print 0.1.4
PY
```

Then run exactly one bounded local/offline smoke through the Sachima-controlled
wrapper, not by ad-hoc direct `acpx` execution, so the durable claim/replay and
no-duplicate gates remain authoritative.
