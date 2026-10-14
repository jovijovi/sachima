# Contributor email → GitHub login mappings

This directory replaces appending entries to `AUTHOR_MAP` in
`scripts/releases/authors_legacy.py`. The old dict caused constant merge conflicts when
several salvage PRs landed at once — every PR edited the same lines of the
same file. Here, **each mapping is its own file**, and file additions never
conflict.

## Adding a mapping

One file per commit-author email, under `emails/`:

```bash
python3 scripts/add_contributor.py <email> <github-login>
# or by hand:
echo "<github-login>" > contributors/emails/<email>
```

- File **name** = the exact commit-author email (as shown by `git log --format='%ae'`).
- File **content** = the GitHub login on the first non-comment line.
  Lines starting with `#` are comments (use them for the PR reference).

Example — `contributors/emails/jane.doe@example.com`:

```
janedoe
# PR #12345 salvage (gateway: fix session key routing)
```

## Rules

- Do NOT add new entries to `AUTHOR_MAP` in `scripts/releases/authors_legacy.py`. That dict
  is frozen legacy data; the release tooling merges it with this directory
  (directory entries win on duplicates).
- GitHub noreply emails (`<id>+<login>@users.noreply.github.com` and
  `<login>@users.noreply.github.com`) auto-resolve — no file needed.
- The `Contributor Attribution Check` CI job fails a PR whose commits carry
  an unmapped email; the failure message prints the exact command to run.

## Crediting one commit

A mapping file claims that every commit with that email belongs to the
login. Do not add one for an address you cannot tie to the account, such as
git's placeholder `you@example.com` (many people commit with it) or an
address no GitHub account is linked to. When the only evidence is the pull
request that carried the commit, add a row to `commits.tsv` instead: the full
commit sha, its author email, the PR submitter's login and the PR. The check
accepts exactly that commit; any other commit with the same email still needs
a mapping.
