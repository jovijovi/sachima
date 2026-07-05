# Sachima live progress safe projection — implementation contract (PR3)

## 1. Title / status

- **Scope:** local/offline implementation plan for a Sachima-side **safe projection** that consumes agent-run-supervisor's already-merged caller cursor API (`read_event_page` / `load_progress` over an artifact dir's `progress.json` + `normalized-events.jsonl`) and maps it into a refs-only, validated, byte-stable Sachima read-model.
- **This is NOT:** live behavior, Gateway/IM/delivery, real external AGENT execution, Temporal Worker/service startup, a new durable runtime, a new Gateway route, a new Temporal activity, or a live renderer. No new runtime dependency is added; nothing is installed, fetched, or launched.
- **Design authority:** subordinate to `docs/architecture/private-hermes-runtime-spine-design.md` and `docs/plans/2026-07-03-sachima-private-hermes-runtime-spine-development-plan.md`. `TaskEventLog` remains Sachima's sole canonical per-`task_id` seq authority; this projection is a **separate read-model over a foreign artifact** and never appends to or renumbers the canonical log.

## 2. Goal and approved scope

Give Sachima a **queryable, safe view of a supervised run's live progress** without exposing raw material or treating supervisor state as a business verdict.

In scope:
- One small pure module under `sachima_supervisor/runtime_spine/` that, given an **injected reader** and an artifact directory path, emits a frozen, validated, refs-only `LiveProgressProjection` for **one cursor page** of events plus the progress summary.
- Closed mapping of `progress.json` → safe summary fields, and one `EventPage` → safe per-event records, with an exposed **resume cursor** (`after_seq` / `next_cursor`).
- Fail-closed handling of missing / stale / corrupt / library-absent inputs.

Out of scope (later, separately-approved slices): multi-page accumulation/streaming, composing live progress into the PR4 workbench view, any real supervisor artifact read from a live run, any IM/delivery surface.

## 3. Current baseline and integration seam

- **Producer (already merged, agent-run-supervisor PR #38, `hermes_caller/events.py`):**
  - `read_event_page(artifact_dir, *, after_seq=None, limit=100) -> EventPage(records, next_cursor, has_more)`; `after_seq` is **exclusive**; persisted `seq` when present, legacy 1-based line-cursor fallback. `EventRecord` exposes only `seq`, `family`, `kind`, `status`, `text_length`, `summary` — never raw text/body/content/message.
  - `load_progress(artifact_dir) -> ProgressSnapshot | None`; fields `schema_version`, `state`, `last_seq`, `event_count`, `updated_at`; missing file → `None`; invalid integer field → raises `ValueError`; no verdict / platform state / raw text.
- **Host reality:** the `agent_run_supervisor` library is **not importable on this host** (PR #117; `sachima_supervisor/supervisor_library.py` is an injectable-probe pin checker, exact pin `0.0.0`, deliberately absent from `pyproject.toml`). Therefore the consumer **must not** `import agent_run_supervisor` at module top level; it imports lazily inside an injected default reader and fails closed when absent.
- **Existing Sachima seam:** `AgentRunSupervisorPort.stream(since_seq=...)` reads **Sachima registry events**, not the ARS artifact `normalized-events.jsonl`. This slice does **not** modify that port; it adds a distinct artifact-read projection alongside it.
- **House idiom to mirror exactly:** `projection.py`, `view_model.py`, `agent_run_supervisor_workbench.py` (frozen dataclass + `__post_init__` normalize/validate, module-level `validate_*`/`build_*`/`serialize_*`, module-local `*_STABLE_CODES`, `SpineError(code)` where the message IS the code, `scan_for_leak` defense-in-depth, byte-stable `json.dumps(sort_keys=True, separators=(",", ":"))`). Injected-backend Protocol + closed state-map table: see `agent_run_supervisor_port.py` (`AgentRunSupervisorBackend`, `_BACKEND_TO_SESSION_STATE`). Injectable-probe lazy import: see `supervisor_library.check_supervisor_library_pin`.

## 4. Proposed Sachima source surface

New module: **`sachima_supervisor/runtime_spine/live_progress_projection.py`** (only file that adds source). Export all public names from `sachima_supervisor/runtime_spine/__init__.py` `__all__`.

Stable codes (module-local frozenset, mirroring the per-module pattern):

```
RUNTIME_INVALID_LIVE_PROGRESS = "runtime_invalid_live_progress"   # fail-closed validation
LIVE_PROGRESS_UNAVAILABLE     = "live_progress_unavailable"       # missing progress.json / reader (ARS lib) absent
LIVE_PROGRESS_CORRUPT         = "live_progress_corrupt"           # ValueError from load_progress / off-contract record
LIVE_PROGRESS_STABLE_CODES    = frozenset({RUNTIME_INVALID_LIVE_PROGRESS, LIVE_PROGRESS_UNAVAILABLE, LIVE_PROGRESS_CORRUPT})
LIVE_PROGRESS_PROJECTION_TYPE = "sachima.runtime_spine.live_progress_projection.v1"
SUPERVISOR_OBSERVED_STATES    = frozenset({"active", "waiting", "settled", "unknown"})
OBSERVED_EVENT_STATUSES       = frozenset({"active", "waiting", "settled", "unknown"})
```

Injected reader boundary:

```
@runtime_checkable
class LiveProgressReader(Protocol):
    def load_progress(self, artifact_dir: str) -> Any | None: ...          # ProgressSnapshot | None
    def read_event_page(self, artifact_dir: str, *, after_seq: int | None = None, limit: int = 100) -> Any: ...  # EventPage

class DefaultLiveProgressReader:
    """Lazily imports agent_run_supervisor.hermes_caller.events inside each
    method; on ImportError raises a module-local _ReaderUnavailable the builder
    maps to LIVE_PROGRESS_UNAVAILABLE. NEVER imports agent_run_supervisor at
    module top level."""
```

Safe per-event record + top-level projection (frozen; follow `AgentRunSupervisorWorkbenchView` shape):

```
@dataclass(frozen=True)
class LiveProgressEventRecord:
    seq: int            # >= 1, strictly increasing across the page (NOT required gap-free)
    family: str         # bounded lowercase token, _safe-token + scan_for_leak
    kind: str           # bounded lowercase token, _safe-token + scan_for_leak
    observed_status: str # ∈ OBSERVED_EVENT_STATUSES (closed map of ARS status)
    text_length: int    # >= 0, bounded (_safe_count); the ONLY text signal carried

@dataclass(frozen=True)
class LiveProgressProjection:
    type: str
    task_id: str | None          # optional safe_task_id association only; NO log coupling
    artifact_ref: str            # caller-supplied SAFE id (e.g. "artifact_local_0") — NEVER the path
    available: bool
    supervisor_state: str        # ∈ SUPERVISOR_OBSERVED_STATES (observation, NOT a verdict)
    schema_version: int
    progress_last_seq: int       # supervisor self-report (progress.json)
    progress_event_count: int    # supervisor self-report
    observed_last_seq: int       # max seq Sachima actually read this page (0 if none)
    observed_event_count: int    # == len(records)
    resume_cursor: int | None    # EventPage.next_cursor → next call's after_seq (None if unavailable)
    has_more: bool
    stale: bool                  # progress summary disagrees with observed event frontier
    records: tuple[LiveProgressEventRecord, ...]
    error_code: str | None       # ∈ LIVE_PROGRESS_STABLE_CODES or None
```

Functions (public):
- `build_live_progress_projection(reader, artifact_dir, artifact_ref, *, task_id=None, after_seq=None, limit=100) -> LiveProgressProjection` — `artifact_dir` (real path) is passed to `reader` **only** and never stored; `artifact_ref` is the safe public handle.
- `validate_live_progress_projection(obj) -> LiveProgressProjection` — rejects `object.__new__` forgery + hostile subclasses; re-runs field checks; returns unchanged.
- `serialize_live_progress_projection(obj) -> bytes` — re-validate then byte-stable JSON.
- `_check_live_progress_fields(obj, *, normalize=False)` and `_safe_token(...)` (module-local, tuned to the ARS `family`/`kind` charset: bounded lowercase `[a-z0-9]` + `_`/`-`; `scan_for_leak`; fail closed with `RUNTIME_INVALID_LIVE_PROGRESS`).

## 5. Mapping contract

### 5.1 `progress.json` → projection summary

| ARS `ProgressSnapshot` field | Projection field | Rule |
|---|---|---|
| `schema_version` (int) | `schema_version` | `_safe_count` (int ≥ 0); non-int → `LIVE_PROGRESS_CORRUPT` |
| `state` (str) | `supervisor_state` | closed map → `active` / `waiting` / `settled` / `unknown`; unknown/missing → `unknown` |
| `last_seq` (int) | `progress_last_seq` | `_safe_count` |
| `event_count` (int) | `progress_event_count` | `_safe_count` |
| `updated_at` | *(not carried)* | used, if at all, only as an internal freshness hint; **dropped** from the durable projection to keep it deterministic and leak-free |
| file missing (`None`) | — | `available=False`, `error_code=LIVE_PROGRESS_UNAVAILABLE`, empty records |
| invalid int (`ValueError`) | — | `available=False`, `error_code=LIVE_PROGRESS_CORRUPT`, **no raw exception text** |

Closed `state` map (deliberately coarse; collapses all terminal-ish supervisor states to a single **non-verdict** `settled`):
```
active:   running | active | in_progress | started
waiting:  permission_wait | waiting | waiting_for_permission | blocked
settled:  completed | succeeded | failed | cancelled | killed | exited | done   # NO success/failure distinction
*:        unknown   # any other / missing token
```
`OBSERVED_EVENT_STATUSES` uses the same closed map for each event's `status`.

### 5.2 `normalized-events.jsonl` cursor page → event records

The producer's `EventRecord` declares `kind`, `status`, and `text_length` **nullable** — lifecycle / delta records (`run_started`, `agent_message_delta`, `run_completed`, …) legitimately omit some of them. Only `seq` and `family` are required. A missing / `None` value on a nullable field is **normalized to a closed safe token** (never echoed raw material and never a corrupt page); a *present* value still runs the full allowlist, so a leaky/off-contract value on any field is still `LIVE_PROGRESS_CORRUPT`.

| ARS `EventRecord` field | Projection record field | Rule |
|---|---|---|
| `seq` (int) | `seq` | **required**; int ≥ 1; strictly increasing across the page; **not** required gap-free (foreign cursor) |
| `family` (str) | `family` | **required**; `_safe_token` + `scan_for_leak`; missing/violation → `LIVE_PROGRESS_CORRUPT` |
| `kind` (str \| None) | `kind` | nullable; `None`/absent → closed token `"unknown"`; a present value runs `_safe_token` + `scan_for_leak`, a leaky/off-charset token → `LIVE_PROGRESS_CORRUPT` |
| `status` (str \| None) | `observed_status` | nullable; closed map (§5.1) → `active`/`waiting`/`settled`/`unknown`; `None`/absent/unmapped → `"unknown"` |
| `text_length` (int \| None) | `text_length` | nullable; `None`/absent → `0`; a present value runs `_safe_count` (≥ 0, bounded, `bool`/negative → `LIVE_PROGRESS_CORRUPT`) — the only text signal |
| `summary` (str) | **DROPPED** | free text; never carried (see §6) |

After normalization the constructed `LiveProgressEventRecord` still carries **exact** safe fields (`kind: str`, `observed_status ∈ OBSERVED_EVENT_STATUSES`, `text_length: int`); the record validators are not weakened — normalization happens only while mapping the foreign record, never in the frozen record's own allowlist.

### 5.3 Cursor / resume mapping

- ARS `after_seq` (exclusive) **is** the Sachima-visible resume cursor. A caller resumes with `after_seq = projection.resume_cursor`.
- `resume_cursor = EventPage.next_cursor` (opaque monotonic int); `has_more = EventPage.has_more`. When `available` is False, `resume_cursor = None`, `has_more = False`.
- This cursor is **distinct from `TaskEventLog` seq** and is never fed into the canonical log; it is a read-model cursor over a foreign artifact. Treat `seq` as an opaque monotonic value (ARS may fall back to a line cursor), never as a gap-free 1..N spine sequence.

### 5.4 Missing / stale / corrupt fail-closed matrix

| Condition | Result |
|---|---|
| `load_progress` → `None` (missing `progress.json`) | `available=False`, `error_code=LIVE_PROGRESS_UNAVAILABLE`, records empty, `supervisor_state="unknown"`, counts 0, `resume_cursor=None`, `has_more=False` |
| reader/library unavailable (ARS lib absent on host — the **default host path**) | same as missing: `LIVE_PROGRESS_UNAVAILABLE` (no `ImportError` propagates) |
| `load_progress` raises `ValueError` (corrupt ints) | `available=False`, `error_code=LIVE_PROGRESS_CORRUPT`, no raw text |
| any event record off-contract (bad `seq`/`family`/`kind`/`status`/`text_length`, or non-monotonic `seq`) | fail the page: `available=False`, `error_code=LIVE_PROGRESS_CORRUPT` |
| progress present, event page empty | `available=True`, records empty, `has_more=False`, `resume_cursor=None`, `observed_*=0` (a legitimate "just started" state) |
| progress summary behind observed events | `available=True`, `stale=True` — canonical rule `stale = progress_last_seq < observed_last_seq`; also set `stale=True` when `has_more is False and progress_last_seq > observed_last_seq` (summary claims events the read stream lacks). `stale` is a surfaced flag, **not** an error — the data is shown but must not be trusted as the fresh frontier. |

## 6. No-leak contract

**Allowed** (exact projection surface): `type`; `task_id` (safe id or `None`); `artifact_ref` (safe id); `available`; `supervisor_state` ∈ `SUPERVISOR_OBSERVED_STATES`; `schema_version`, `progress_last_seq`, `progress_event_count`, `observed_last_seq`, `observed_event_count` (bounded ints); `resume_cursor` (int|None); `has_more`, `stale` (bool); `records[]` each `{seq:int, family:token, kind:token, observed_status ∈ OBSERVED_EVENT_STATUSES, text_length:int}`; `error_code` ∈ `LIVE_PROGRESS_STABLE_CODES` or `None`.

**Forbidden — never carried, in any field, any depth:**
- the artifact directory path or any filesystem path (already in `FORBIDDEN_MARKERS`: `/home/`, `/tmp/`, `/var/`, `/users/`);
- ARS `summary` free text, and any raw `text` / `content` / `message` / `body`;
- raw exception text / traceback from `load_progress` / `read_event_page`;
- platform ids, chat/user/message ids, media, secrets, signed URLs (existing denylist);
- any rich/unmapped supervisor state token carrying pass/fail verdict semantics (collapsed to `settled`/`unknown`).

**Enforcement:** `_check_live_progress_fields` runs the exact key/value allowlist AND `scan_for_leak(<raw dict>)`; `serialize_*` re-validates before emitting; unknown tokens are mapped to `unknown` or fail closed, never echoed. Supervisor state is labelled and treated as **runtime observation only, never a business verdict** — Sachima's own `TaskEventLog` remains the verdict authority.

## 7. TDD acceptance tests (main programmer; RED first)

New file `tests/sachima_supervisor/runtime_spine/test_live_progress_projection.py`. Fetch the module via `importlib.import_module(...)`; drive it with an in-test **fake reader** (no real library, no file I/O of real runs). Each test is RED before the module exists / before the mapping is written.

RED examples (illustrative, not exhaustive):

```python
import importlib
import pytest
from sachima_supervisor.runtime_spine import SpineError, scan_for_leak

def _mod():
    return importlib.import_module("sachima_supervisor.runtime_spine.live_progress_projection")

class _FakeProgress:  # shape of ARS ProgressSnapshot
    def __init__(self, **k): self.__dict__.update(k)

class _FakePage:      # shape of ARS EventPage
    def __init__(self, records, next_cursor, has_more):
        self.records, self.next_cursor, self.has_more = records, next_cursor, has_more

class _FakeRec:       # shape of ARS EventRecord
    def __init__(self, **k): self.__dict__.update(k)

class _FakeReader:
    def __init__(self, progress, page): self._p, self._page = progress, page
    def load_progress(self, artifact_dir): return self._p
    def read_event_page(self, artifact_dir, *, after_seq=None, limit=100): return self._page

def test_maps_progress_and_events_refs_only():
    m = _mod()
    reader = _FakeReader(
        _FakeProgress(schema_version=1, state="running", last_seq=3, event_count=3),
        _FakePage((_FakeRec(seq=1, family="lifecycle", kind="agent_started", status="running", text_length=0),
                   _FakeRec(seq=2, family="tool", kind="tool_call", status="running", text_length=42),
                   _FakeRec(seq=3, family="message", kind="assistant", status="running", text_length=120)),
                  next_cursor=3, has_more=False))
    proj = m.build_live_progress_projection(reader, "/tmp/run/abc", "artifact_local_0")
    assert proj.available is True
    assert proj.supervisor_state == "active"
    assert proj.observed_event_count == 3 and proj.resume_cursor == 3 and proj.has_more is False
    assert all(not hasattr(r, "summary") for r in proj.records)   # summary never carried

def test_resume_cursor_after_seq_no_duplicate():
    # page1 after_seq=None → resume_cursor=2; page2 after_seq=2 → seqs strictly > 2, monotonic
    ...

def test_missing_progress_fails_closed_unavailable():
    m = _mod()
    proj = m.build_live_progress_projection(_FakeReader(None, _FakePage((), None, False)),
                                            "/tmp/run/abc", "artifact_local_0")
    assert proj.available is False and proj.error_code == "live_progress_unavailable"
    assert proj.records == () and proj.supervisor_state == "unknown"

def test_corrupt_progress_valueerror_no_raw_text():
    class _Boom:
        def load_progress(self, d): raise ValueError("bad int at /home/user/run/progress.json")
        def read_event_page(self, d, **k): raise AssertionError("not reached")
    proj = _mod().build_live_progress_projection(_Boom(), "/tmp/run/abc", "artifact_local_0")
    assert proj.error_code == "live_progress_corrupt"
    assert scan_for_leak(proj.as_dict()) is None                  # "/home/" never echoed

def test_path_and_summary_never_leak():
    m = _mod()
    reader = _FakeReader(_FakeProgress(schema_version=1, state="running", last_seq=1, event_count=1),
                         _FakePage((_FakeRec(seq=1, family="message", kind="assistant",
                                             status="running", text_length=9, summary="visit /home/user/secret"),),
                                   next_cursor=1, has_more=False))
    blob = m.serialize_live_progress_projection(
        m.build_live_progress_projection(reader, "/tmp/run/abc/progress", "artifact_local_0"))
    for marker in (b"/tmp/", b"/home/", b"secret", b"summary"):
        assert marker not in blob

def test_leaky_token_fails_closed():
    # a record whose kind carries a forbidden marker (e.g. "chat_id") → LIVE_PROGRESS_CORRUPT, not carried
    ...

def test_terminal_states_are_not_a_verdict():
    m = _mod()
    for ars_state in ("completed", "failed", "cancelled"):
        proj = m.build_live_progress_projection(
            _FakeReader(_FakeProgress(schema_version=1, state=ars_state, last_seq=1, event_count=1),
                        _FakePage((), None, False)), "/tmp/run", "artifact_local_0")
        assert proj.supervisor_state == "settled"                 # no pass/fail asserted

def test_stale_when_progress_behind_events():
    # progress.last_seq=1 but observed_last_seq=3 → stale True, available True
    ...

def test_default_reader_absent_library_unavailable(monkeypatch):
    # DefaultLiveProgressReader with agent_run_supervisor unimportable → available False,
    # error_code live_progress_unavailable, NO ImportError propagates
    ...

def test_forgery_and_mutation_fail_closed():
    m = _mod()
    forged = object.__new__(m.LiveProgressProjection)
    with pytest.raises(SpineError):
        m.validate_live_progress_projection(forged)

def test_byte_stable_and_no_taskeventlog_mutation():
    # serialize twice → identical bytes; building appends nothing to a supplied TaskEventLog
    ...
```

Grader-integrity note: these tests assert externally-observable safe behavior (mapping, fail-closed codes, no-leak bytes, determinism). They must not be shaped to a specific internal implementation nor relaxed to pass; the no-leak and verdict tests are load-bearing.

## 8. Verification gates

Verification runs are Hermes-owned; the implementer writes the tests and delegates execution.

1. **Focused tests:** `python -m pytest tests/sachima_supervisor/runtime_spine/test_live_progress_projection.py -q` — all green, no skips.
2. **Adjacent regression:** `python -m pytest tests/sachima_supervisor/runtime_spine -q` — the whole spine suite stays green (`projection.py`, `view_model.py`, `agent_run_supervisor_*`, `execution_port.py`, `registry.py` are untouched; `__init__.py` only gains exports).
3. **Compile:** `python -m compileall sachima_supervisor/runtime_spine/live_progress_projection.py`.
4. **Lint (encoding):** `python -m ruff check sachima_supervisor/runtime_spine/live_progress_projection.py` — must pass; the module does **no bare file I/O** (PLW1514 cannot bite), which is also the design guarantee that reading stays inside the injected/ARS reader.
5. **No-leak / forbidden-surface scan:**
   - the §7 no-leak + path + summary + verdict tests;
   - a top-level-import scan: assert `agent_run_supervisor` is imported only lazily inside a function — e.g. `grep -n "^import agent_run_supervisor\|^from agent_run_supervisor" sachima_supervisor/runtime_spine/live_progress_projection.py` returns nothing;
   - a serialized-fixture scan for `FORBIDDEN_MARKERS` presence.
6. **Docs gates (only if docs change):** if the slice adds a runbook (`docs/runbooks/sachima-agent-run-supervisor-live-progress-projection.md`) and updates `docs/roadmap/reference-index.md` / the status board, those follow the existing per-slice runbook + reference-index convention. The plan `.md` here and any paired `-manifest.yaml` are PM/Hermes-owned.
7. **Codex CLI:** final repo-aware read-only blocker review before merge.

## 9. Explicit non-approvals and stop conditions

This slice does **not** approve or implement, and the programmer must stop and escalate if any is implied:
- real Feishu/IM send; Gateway restart/reload/lifecycle; production config writes; default-on enablement; public ingress/webhook;
- real external AGENT launch; Temporal Worker/service startup; real acpx/npx/agent execution;
- exposing raw `text` / `content` / `message` / `body` (or ARS `summary`) to Sachima; exposing artifact filesystem paths;
- treating supervisor state as a business verdict;
- adding `agent-run-supervisor` to `pyproject.toml`, or importing it at module top level, or installing/fetching/pinning it;
- feeding ARS artifact events or the ARS cursor into `TaskEventLog` / renumbering the canonical seq;
- reading a real live supervisor run's artifact dir in tests (use fakes/fixtures only).

## 10. Architecture concerns and recommendations

1. **Foreign-cursor boundary (highest risk).** Keep the ARS `seq`/`next_cursor` entirely out of `TaskEventLog`. This is a read-model cursor, not spine truth. Do not assume gap-free 1..N — validate only "strictly increasing, ≥ 1"; the sole supported resume contract is `after_seq = resume_cursor`.
2. **Library absence is the default path.** Because `agent_run_supervisor` is not importable on-host, the default `DefaultLiveProgressReader` path yields a clean fail-closed `LIVE_PROGRESS_UNAVAILABLE` projection — correct for a local/offline slice. Lazy import is mandatory; a top-level import would break package import everywhere.
3. **`summary` is the single largest leak vector — drop it.** Carry only `text_length`. A displayable summary, if ever wanted, is a separate surface under separate approval and its own no-leak gate.
4. **Verdict conflation.** Collapsing terminal ARS states to a non-verdict `settled` is intentional; distinguishing success/failure would import a business verdict Sachima must derive from its own Event Log. Keep the coarse observation vocabulary.
5. **Determinism.** Do not carry wall-clock `updated_at` in the durable projection; derive `stale` from seq disagreement (`progress_last_seq` vs `observed_last_seq`) so output stays byte-stable and testable without a clock.
6. **Field-name pinning.** The exact ARS attribute names/types above are taken from the Hermes-provided PR #38 contract; the ARS source is outside the Sachima worktree sandbox. The programmer must confirm the imported names against the importable module at implementation time and keep the fake-reader shapes in lockstep. If the real records use a different `family`/`kind` charset than `_safe_token` allows, that is a fail-closed `LIVE_PROGRESS_CORRUPT`, not a silent transform.
7. **Future composition.** A later slice may compose `LiveProgressProjection` into the PR4 workbench view (an optional live-progress panel). Keep this PR a standalone read-model; do not widen the workbench view here.

**Verdict:** the main programmer can proceed with this contract. Recommended surface is a single new module `sachima_supervisor/runtime_spine/live_progress_projection.py` + its focused test file + `__init__.py` exports, built as an injected-reader, fail-closed, refs-only, byte-stable projection. No blockers to starting; the one open item (exact ARS field names/charset) is resolved by the programmer pinning against the importable module and is already covered by the fail-closed corrupt path.
