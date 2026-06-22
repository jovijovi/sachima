## ARCHITECT Teach-Back Packet — Workspace File Profile-Scoped Management PRD

> Scope note: produced from the embedded PRD text only. I did not read `tools/workspace_file_tool.py`, tests, or live profile config (per the "PRD only" constraint and the no-touch rules). This packet authorizes nothing and proposes no edits.

---

### 1. VERDICT

**READY_FOR_TECHNICAL_DESIGN**

No P0 or P1 questions found. I independently stress-tested the PRD's own "no P0" claim rather than rubber-stamping it; the residual ambiguities are all P2 design choices with safe fail-closed defaults already implied by the document.

---

### 2. SCORE: 93 / 100

| Rubric dimension | Max | Score | Rationale |
|---|---|---|---|
| Goals / outcome | 20 | 19 | §1 outcome is unambiguous (narrow file mgmt inside `$HERMES_HOME`). Minor: success is expressed via acceptance criteria, not standalone metrics. |
| Scope / non-goals | 20 | 19 | §5 in-scope FRs + §6 explicit non-approvals are exemplary. One small scope seam left to design (import-root policy vs workspace policy). |
| Functional / NFR interpretation | 20 | 18 | All FRs interpretable with IDs. Two seams (dst-extension enforcement on copy/move; import policy composition) are design-resolvable, not specified. |
| Assumptions / open questions | 15 | 13 | §10 declares no P0s and lists real design questions. Could have nailed the import-vs-workspace policy interaction explicitly. |
| Risk / boundary interpretation | 15 | 14 | §9 risk table maps cleanly to mitigations; §8/FR-8 boundary list is comprehensive and fail-closed. |
| Trace IDs ready | 10 | 10 | FR-1..10, AC-1..14, scenarios, risk rows, config keys all provide stable anchors. |

---

### 3. Goals & success outcomes (as understood)

- **Primary goal:** give companion/worker profiles (initially Samiya, from Feishu) the ability to organize their own local files — list, stat, copy, move, delete, import text/media — **without** granting broad `file` or `terminal` access.
- **Hard outcome boundary:** every operation stays inside the active profile's `$HERMES_HOME` workspace; no cross-profile reach, no filesystem escape.
- **Continuity outcome:** existing text-note workflows (`workspace_read/write/patch/search`) and legacy `allowed_extensions` configs keep working unchanged.
- **Safety outcome:** destructive and binary-exposure risks are contained — delete is reversible (trash), binary never enters model context as raw bytes, and tool output is metadata-only for mutating ops.
- **Success = evidence:** behavior proven by RED/GREEN pytest + targeted gates before any PR/approval (§7, §8).

---

### 4. Scope & explicit non-approvals

**In scope (this PRD):** FR-1..FR-10 — extend the single generic `workspace_file` toolset with stat/copy/move/delete/import, a `file_type_policy`, a default media/text allowlist, import roots, trash-default delete, and registration/docs updates.

**Explicitly NOT approved (§6) — I will treat all of these as out of bounds:**
- Any implementation before PRD-quality → architect teach-back → technical design → user approval all complete.
- Enabling `workspace_file` for default / Satine / Skywalker / any new profile or platform.
- Editing live profile config, restarting any Gateway, production rollout, or default-on behavior.
- Granting Samiya full `file`/`terminal`/`web`/`search`/GitHub/delegation/messaging access.
- Network download/fetch (belongs to `media_fetch`), public hosting/upload/render/delivery of media.
- Recursive directory copy/move/delete.
- Raw binary/base64 read or write through model-visible JSON.

**Status:** PRD is a draft for pre-development governance; **not implementation-approved.**

---

### 5. Functional requirement interpretation

- **FR-1 — single toolset:** New ops register under the *same* `workspace_file` toolset id; no persona-specific surface. Samiya gains capability purely via profile config enablement, not a new tool.
- **FR-2 — five new ops:** `workspace_stat` (metadata read), `workspace_copy`/`workspace_move`/`workspace_import` (mutating, `overwrite=false` default), `workspace_delete` (soft by default). All subject to FR-8 boundary checks and FR-3 extension policy on **both** source and destination paths. Existing five tools untouched. Names may change only if design finds a safer equivalent.
- **FR-3 — `file_type_policy`:** `{mode: allowlist|denylist|all, extensions:[]}`. Legacy `allowed_extensions` maps to an allowlist when `file_type_policy` is absent. When both present → explicit `file_type_policy` wins (I adopt the recommended default; see OQ). Normalize lowercase + leading-dot, compare suffix case-insensitively. `mode: all` disables **only** the extension check — all path/root/symlink/size/regular-file/operation checks still apply.
- **FR-4 — default allowlist:** text + image + audio + video set (incl. `.jpeg`, `.webp`, `.wav`). Optional set is *not* default; `.svg` excluded by default (scriptable-content risk). I read these as code-level defaults applied only when no policy/legacy config exists.
- **FR-5 — text vs binary:** `workspace_read` stays safe for text; binary/media → metadata or a safe marker, never raw bytes/base64. `workspace_search` searches text-like files only, skipping binary with clear metadata. `workspace_write`/`workspace_patch` remain text-only and must reject raw binary in JSON args.
- **FR-6 — import roots:** named, **read-only** source roots under `HERMES_HOME`, each with its own `file_type_policy`. They may copy *into* the workspace; never move/delete/write/traverse outside the configured root. I interpret import as: read from source root **and** write to workspace dst, with **both** the source-root policy and the workspace destination policy applying (fail-closed intersection) — flagged for confirmation.
- **FR-7 — delete→trash:** soft delete by default into a workspace-local `.trash`, collision-safe, returns path/bytes/action only. `permanent=true` allowed only if config permits or design justifies a safe explicit override.
- **FR-8 — hard boundaries:** relative paths only; reject absolute/empty-segment/`.`/`..`/traversal *before* normalization; resolve src+dst+parents; reject symlinked sources, symlinked dst parents, and any resolved path outside root; regular files only (no dirs/sockets/devices/FIFOs/recursion); `overwrite=false` default; respect read-only mode; outputs limited to action/path/bytes/status, never content.
- **FR-9 — scan & size:** `max_file_bytes` on every read/write/copy/move/import; secret-shaped + optional prompt-injection scans on text writes/patches; scan materialized **text** copy/import within size limit; never scan raw binary as text (rely on extension/size/root/regular-file).
- **FR-10 — registration/docs:** register new tools under `workspace_file`; keep them **out** of `_HERMES_CORE_TOOLS`; update tests so `resolve_toolset("workspace_file")` lists existing + new names; minimal user/dev docs.

---

### 6. Non-functional & security boundary interpretation

- **Profile isolation:** every root resolves under the active `HERMES_HOME`; no cross-profile access introduced.
- **Low intrusion:** implementation slice = tool code + tests + minimal docs only; no Gateway/adapter/scheduler/service-lifecycle changes unless later design proves need *and* user approves.
- **Backward compatibility:** text workflows and legacy `allowed_extensions` keep working; new policy is additive.
- **Fail-closed posture:** malformed config, traversal, symlink, oversize, disallowed extension, and unsafe src/dst all **reject** rather than degrade. This same principle is what lets me default the open ambiguities safely.
- **Evidence before claims:** RED/GREEN pytest + `git diff --check` + registration discovery + a targeted static scan proving no new terminal/shell/Gateway/platform/restart/network surface, before PR readiness; baseline failures classified honestly.
- **Key security insight:** non-scanned binary/media imports remain *inert* because Hermes never executes, renders, or delivers them (those are out-of-scope per §6). The residual risk is bounded to inert storage and is reversible via trash. The defense-in-depth is structural (extension + size + root + symlink + regular-file + no-render), not parser-based.

---

### 7. Assumptions

1. `source_root` in `workspace_import` names a configured `import_roots` key; an unknown key fails closed (reject).
2. Extension policy applies to the **destination** path's extension on copy/move/import — a rename cannot smuggle a disallowed extension into the workspace.
3. Import enforces the **intersection** of source-root policy and workspace destination policy (fail-closed), not a source-root override/escape hatch.
4. Default allowlist (FR-4) applies only when neither `file_type_policy` nor legacy `allowed_extensions` is set; explicit config **replaces** defaults rather than augmenting them.
5. Creating missing destination parent dirs *within* root is permitted (consistent with existing write behavior), still bounded by root + no-symlinked-parent.
6. `permanent=true` is disabled unless config opts in (fail-closed reading of FR-7).
7. `.trash` lives inside the workspace root, is itself subject to all boundary checks, and trashed files are operator-recoverable — not silently agent-recoverable.
8. "metadata" for stat/read = name/size/bytes/mtime/type-label only (no content), bounded by `max_output_chars`.

---

### 8. Open questions

**P0 (blocks technical design): NONE.**
**P1 (blocks technical design): NONE.**

> Stated explicitly as required: there are no P0 or P1 open questions. Technical design may proceed; the items below are P2 confirmations to resolve *during* design, each with a recommended safe default.

**P2 (design-time confirmations, non-blocking):**
- **OQ-1 (FR-6 × FR-3):** Confirm import composes as intersection of source-root + workspace destination policy (my default), not source-root override.
- **OQ-2 (FR-3):** Confirm explicit `file_type_policy` fully wins over legacy `allowed_extensions` when both are present.
- **OQ-3 (FR-4 × FR-3):** Confirm explicit config *replaces* the FR-4 defaults rather than merging with them.
- **OQ-4 (FR-2 × FR-8):** Confirm copy/move enforce the **dst** extension against policy (rename guard).
- **OQ-5 (FR-5, §10):** `workspace_read` on binary → generic file marker vs metadata-only (both safe; pick one).
- **OQ-6 (FR-5, §10):** Text-vs-binary classification method — extension-first vs bounded content sniff — must not add an unsafe parser surface.
- **OQ-7 (FR-7, §10):** Permanent delete — config-disabled-by-default (recommended) vs allowed via `permanent=true` + audit.
- **OQ-8 (FR-7):** Trash collision strategy (timestamp/counter suffix vs dated subdir).
- **OQ-9 (FR-10, §10):** Docs scope — tool docs/tests only vs also include profile-config examples.

---

### 9. Trace IDs to carry into technical design

- **Requirements:** `FR-1` … `FR-10`
- **Acceptance criteria:** `AC-1` … `AC-14` (the §8 numbered list, in order)
- **Scenarios:** `SC-A` media organization · `SC-B` safe cleanup/trash · `SC-C` text-note continuity
- **Risks:** `RK-1` binary context flood · `RK-2` symlink/traversal escape · `RK-3` destructive delete · `RK-4` `mode: all` over-permission · `RK-5` legacy config breakage · `RK-6` media→download/render drift
- **New operations:** `OP-STAT`, `OP-COPY`, `OP-MOVE`, `OP-DELETE`, `OP-IMPORT`
- **Config keys:** `CFG-file_type_policy`, `CFG-import_roots`, `CFG-delete`
- **Open questions:** `OQ-1` … `OQ-9` (all P2)
- **Source anchors (not opened here):** `SRC=tools/workspace_file_tool.py`, `TST=tests/tools/test_workspace_file_tool.py`, toolset id `workspace_file`, registration guard `_HERMES_CORE_TOOLS`

---

**Handoff:** PRD is coherent, fail-closed, and well-traced. Recommend proceeding to technical design with OQ-1..OQ-9 resolved inline; none gate the start. No implementation, config edits, Gateway actions, or profile-enablement changes were taken or are requested.
