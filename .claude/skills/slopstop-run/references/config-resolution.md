# Configuration resolution — the one definition

Every orchestrator resolves configuration this way. Read this instead of re-deriving it.

## Three sets, each overriding the last

| set | source | tracked? | role |
|---|---|---|---|
| 1 | the documented defaults in `CONFIG.md` | — | the floor |
| 2 | `.project-conf.toml` | **yes** | the project's settings, shared by everyone |
| 3 | `.project-conf-local.toml` | **no — gitignored** | one developer's overrides |

Set 3 beats set 2 beats set 1.

The point of set 3 is that `.project-conf.toml` can be **committed and reviewed** while the
handful of values that are genuinely per-developer are not. The motivating case is working
from a fork: a local file containing one line —

```toml
key = "joe_blow/my-fork-of-repo"
```

— must change `key` and leave every other value exactly as the project set it.

## Override is per leaf key, never per table

**This is the rule that is easy to get wrong, and getting it wrong is silent.**

A local file naming a table does **not** replace that table. Merge key by key, descending
into sub-tables:

```toml
# .project-conf.toml
[tiers.small]
provider = "anthropic"
model    = "sonnet"
version  = "5"

# .project-conf-local.toml
[tiers.small]
model = "qwen"
```

resolves to `provider = "anthropic"`, `model = "qwen"`, `version = "5"`. It does **not**
resolve to a `[tiers.small]` holding only `model`, and it does not touch `[tiers.huge]`.

A whole-table replacement here would silently drop `provider` and `version`, and the tier
would then resolve to a bare model family with no version pin — which *works*, and quietly
selects a different model than the project asked for. Nothing would report an error.

## Resolution order

1. Locate `.project-conf.toml` — cwd, else the main worktree root
   (`dirname "$(git rev-parse --git-common-dir)"`). Absent from both → stop; this is the
   existing error, unchanged.
2. Look for `.project-conf-local.toml` **beside it**, in the same directory. Never search
   upward for it, and never take one from cwd when the tracked file came from the worktree
   root — a local file that overrides a *different* project's config is worse than none.
3. Start from the documented defaults, apply set 2, then apply set 3, per leaf key.
4. Absent set 3 → resolution is byte-for-byte what it was before this mechanism existed.
   **That equivalence is the first thing to check when changing any of this.**

## A local file overrides; it does not extend

A key in `.project-conf-local.toml` that does not exist in the documented schema is an
error, not a new setting. Report it by name and stop. Silently accepting unknown keys turns
a typo (`prefx = "BILL"`) into a value that is never read and never complained about, which
is the failure mode the whole three-set arrangement is otherwise designed to avoid.

## Say where a value came from

When reporting resolved configuration, name the source file for every value that is **not**
a default:

```
prefix       BILL                    .project-conf.toml
key          joe_blow/my-fork        .project-conf-local.toml   ← local override
tiers.small  sonnet 5                .project-conf.toml
cc_reject    10                      (default)
```

A run that behaves unexpectedly because of an untracked file nobody else can see is
exactly the confusion this mechanism could introduce. Naming the source is what keeps it
from being a mystery — and a local override should be visible in the run's own output, not
discoverable only by finding the file.

## The fleet tools read set 2 only

`tools/fleet-sync/audit-project-conf.py` and `sync-project-conf.py` operate on
`.project-conf.toml` and **must ignore `.project-conf-local.toml` entirely**. A local file
is one developer's, on one machine. Auditing it would report a personal choice as fleet
drift; syncing it would push one developer's fork URL to everyone.
