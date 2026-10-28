// Which workspace checks .github/scripts/run-workspace-checks.mjs runs, driven through the exact
// argv js-tests.yml passes it: the fork drops only Desktop units, never a Linux-shipped check.
import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { load } from 'js-yaml'
import { beforeAll, expect, it } from 'vitest'

const repo = new URL('..', import.meta.url)
const script = '.github/scripts/run-workspace-checks.mjs'
// Each test spawns `npm query .workspace` over the whole monorepo once (~0.8 s on an idle
// 4-vCPU host): vitest's 5 s default is too close once the hosted lane runs every check at once.
const TIMEOUT = 20_000

const run = args => spawnSync(process.execPath, [script, ...args], { cwd: repo, encoding: 'utf8' })
const list = (args = []) => {
  const result = run(['--list', ...args])
  expect(result.status, result.stderr).toBe(0)
  return result.stdout.trim().split('\n')
}
const workspace = unit => unit.split(' :: ')[0]
const spec = unit => unit.replace(' :: ', ':')

let all
beforeAll(() => {
  all = list()
}, TIMEOUT)

it("the fork's JS job runs every check outside apps/desktop", () => {
  const steps = load(readFileSync(new URL('.github/workflows/js-tests.yml', repo), 'utf8')).jobs.check.steps
  const [node, file, ...args] = steps.find(step => step.run?.includes(script)).run.trim().split(/\s+/)
  expect([node, file]).toEqual(['node', script])

  const selected = list(args)
  const dropped = all.filter(unit => !selected.includes(unit))
  expect(dropped.length).toBeGreaterThan(0)
  expect(dropped.map(workspace)).toEqual(dropped.map(() => 'apps/desktop'))
  for (const shipped of ['web', 'ui-tui', 'apps/shared', 'tests-js']) {
    expect(selected.map(workspace)).toContain(shipped)
  }
  // Reads the shared update-marker corpus (scripts/ci/classify_changes.py _SHARED_FIXTURE_CONSUMERS).
  expect(selected).toContain('apps/desktop :: check:test:desktop:platforms')
}, TIMEOUT)

it('an --exclude drops exactly the check it names', () => {
  const target = all.find(unit => workspace(unit) === 'web')
  expect(list(['--exclude', spec(target)])).toEqual(all.filter(unit => unit !== target))
}, TIMEOUT)

it.each([
  ['a script its workspace does not declare', ['--exclude', 'apps/desktop:check:no-such-suite']],
  ['a workspace without a script', ['--exclude', 'apps/desktop']],
  ['nothing', ['--exclude']],
])('an --exclude naming %s fails instead of running another selection', (_, args) => {
  const result = run(['--list', ...args])
  expect(result.status).toBe(1)
  expect(result.stderr).toContain('names no workspace check')
}, TIMEOUT)

it('excluding every check fails instead of reporting an empty green run', () => {
  const result = run(['--list', ...all.flatMap(unit => ['--exclude', spec(unit)])])
  expect(result.status).toBe(1)
  expect(result.stderr).toContain('leaves no workspace check')
}, TIMEOUT)
