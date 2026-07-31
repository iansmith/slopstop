# Test-Command Resolution — the Auto-detect Table (shared)

The one definition of the auto-detect table used to resolve a project's test command,
plus the C5 output-capping rule that governs what a gate does with the output once it has
run that command. Three sites consult this file — `:plan` Step 0a
(`plan-phase0-mechanics.md`), `:pr` Steps 0b/2 (`pr-test-gates.md`), and `:run`'s handoff
verification (`run-verification.md`) — and each keeps its own resolution *ladder* (what
order to try rungs in, whether to ask, whether to cache the answer). **This file is the
table only, not the ladder** — do not unify the three ladders here; they are a deliberate
asymmetry (see `pr-test-gates.md`'s own note on this).

## The auto-detect table

| Indicator | Test command |
|---|---|
| `Taskfile.yml` with a `test:` task | `task test` |
| `Makefile` with a `test:` target | `make test` |
| `package.json` with a `"test"` script + `pnpm-lock.yaml` | `pnpm test` |
| `package.json` with a `"test"` script + `yarn.lock` | `yarn test` |
| `package.json` with a `"test"` script (else) | `npm test` |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` |
| `pyproject.toml` with pytest config | `pytest` |

The `pnpm-lock.yaml` vs `yarn.lock` discriminator only matters when a `package.json`
already has a `"test"` script — the two lockfiles pick which package manager runs it.

## The C5 capping rule — full output to disk, decisive lines into context

Any gate that runs the resolved test command **writes its full output to a file in the
tracking dir and reads that file back to classify the result** — never `| tail -N` or
`| head -N` on a stream a gate must classify. Truncating the stream a gate reads from can
silently drop the very failure the gate exists to catch, changing its verdict. The
pattern:

```bash
( eval "$TEST_CMD" ) > "$TRACKING_DIR/$TICKET/<gate>.output" 2>&1
STATUS=$?
```

`STATUS=$?` is captured on the line immediately following the redirect — the exit code is
not present in the redirected text, and some gates classify on it rather than (or in
addition to) the file's contents.

**Step 0b** (`:pr`'s pre-PR health check, `pr-test-gates.md`) is the reference
implementation of this rule: it writes the full suite's output to disk and **reads it back
from that file** to classify every failing test as regression or expected-failure — the
gate's classification keeps access to every failure line, never a truncated tail. Only
**decisive lines** (the ones that inform the pass/fail/regression verdict) are quoted back
into context; the file itself is the durable, complete record.

This capping rule governs *what a gate does with test-command output once resolved* — it
composes with, but is distinct from, each site's own resolution ladder for *how the
command itself gets resolved*.
