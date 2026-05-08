# Preserve explicit context length during overflow compression

## Task Background

狗哥 approved implementing a low-intrusion fix so a configured `model.context_length: 400000` is not automatically reduced to the 256K probe tier after a generic context-overflow/compression path.

```text
Base branch: feature/sachima-channel
Implementation branch: fix/preserve-explicit-context-length-on-overflow
Implementation worktree: /home/ubuntu/workspace/hermes/worktrees/sachima/fix-preserve-explicit-context-length-on-overflow
Started at: 2026-05-08 17:06:11 CST +0800
```

## Implementation

- Added `context.preserve_explicit_context_length` defaulting to `true`.
- Added `_resolve_context_overflow_context_length(...)` to keep provider-limit decisions explicit and testable.
- Preserves runtime `context_length` when:
  - `model.context_length` is explicitly configured,
  - preserve flag is enabled,
  - provider did not report a concrete lower context limit.
- Still steps down when the provider parses a real lower limit.
- Existing opt-out: set `context.preserve_explicit_context_length: false` to keep old probe-tier stepdown behavior.

## TDD Evidence

### RED

```text
scripts/run_tests.sh tests/run_agent/test_preserve_explicit_context_length.py -q
ImportError: cannot import name '_resolve_context_overflow_context_length'
```

### GREEN

```text
scripts/run_tests.sh tests/run_agent/test_preserve_explicit_context_length.py -q
5 passed in 1.54s

scripts/run_tests.sh \
  tests/run_agent/test_preserve_explicit_context_length.py \
  tests/run_agent/test_invalid_context_length_warning.py \
  tests/run_agent/test_1630_context_overflow_loop.py \
  tests/run_agent/test_long_context_tier_429.py \
  -q
41 passed in 1.60s

scripts/run_tests.sh \
  tests/hermes_cli/test_config.py \
  tests/hermes_cli/test_custom_provider_context_length.py \
  -q
64 passed in 1.30s

python -m py_compile run_agent.py hermes_cli/config.py tests/run_agent/test_preserve_explicit_context_length.py
py_compile: PASS

python -m ruff check run_agent.py hermes_cli/config.py tests/run_agent/test_preserve_explicit_context_length.py
ruff: PASS

git diff --check
git diff --check: PASS
```

## Fresh-Context Review

Independent blocker-only review returned PASS:

```text
passed: true
blockers: []
notes: preserves explicit context_length on generic overflow; provider-parsed lower limits still step down; opt-out flag supported.
```

## PR CI Follow-up

PR #51 initially failed the Nix web package build because `web/src/pages/ProgressPage.tsx` imported missing local shadcn-style UI modules:

```text
src/pages/ProgressPage.tsx:20:23 - error TS2307: Cannot find module '@/components/ui/badge'
src/pages/ProgressPage.tsx:21:24 - error TS2307: Cannot find module '@/components/ui/button'
```

Low-intrusion fix: align `ProgressPage` with the repo's existing `@nous-research/ui` Badge/Button imports and props (`tone`, `outlined`).

Local web verification after the fix:

```text
npm ci
added 346 packages, and audited 347 packages in 3s
found 0 vulnerabilities

npm run build
tsc -b && vite build
✓ built in 3.81s
```

`npm run lint` was also probed but is not a clean gate on this branch: it reports existing repo-wide React/ESLint issues outside this fix path. The CI blocker was the TypeScript build error above, and `npm run build` now passes.

Follow-up fresh-context review returned PASS:

```text
passed: true
blockers: []
notes: @nous-research/ui Badge/Button paths and props match installed types; TypeScript app no-emit check passed.
```

Local `nix build .#web --print-build-logs` could not run in this workspace because `nix` is not installed (`nix: command not found`); final Nix verification remains GitHub CI.
