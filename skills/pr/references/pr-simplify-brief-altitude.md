# `:pr` Step 1 — Altitude brief

You are **one of four independent cleanup agents** on this branch's diff. The other
three cover the dimensions you do not — stay in your lane; duplicating their work
wastes a pass.

**You were also given `pr-simplify-brief-common.md`.** It carries the rules that bind
every dimension: read the repository's own `CLAUDE.md`, never touch generated /
vendored / test-corpus files, never edit a frozen Phase 0 test, apply your own fixes,
preserve behavior. If you did not receive it, say so and stop — you are missing half
your instructions.

## Your dimension: altitude

Ask whether each change in the diff is implemented at the **right depth**, or whether it
is a bandaid over a problem that lives lower down.

What to look for:

- **A special case layered onto shared infrastructure.** One `if` for one caller, added
  to a function used by many, is the classic signal that the underlying mechanism does
  not do what its callers need. Prefer generalizing the mechanism.
- **A fix at the call site that belongs in the callee** — every caller now has to
  remember to apply it, and the next one will not.
- **A symptom patched where the cause is visible.** If the diff handles a malformed
  value, ask where the malformed value came from and whether that is the real fix.
- **Cherry-picked cases within a category.** When working through a class of failures,
  handling the easy ones and declaring the work done leaves the hard ones as a trap.
  "Nearly passing" is failing.
- **Configuration or a flag introduced to avoid making a decision.** A knob with one
  sensible value is a decision deferred onto every future reader.

Balance this against scope. Structural changes — renaming exported symbols, altering
public signatures, moving files, reshaping module boundaries — are **out of scope** for
you unless the repository's rules say otherwise. When you find one that is genuinely
needed, **flag it for the human rather than doing it**; that is the correct outcome for
this dimension, not a failure to act.

Your most valuable finding is often a short note explaining that the fix is in the wrong
place and where it belongs.

## Maintain balance — the failure mode of your own dimension

Every instruction above pushes you toward *more* generalization. This section pushes back, and
it carries equal weight. Avoid changes that:

- Reduce code clarity or maintainability
- Create overly clever solutions that are hard to understand
- Combine too many concerns into a single function or component
- Remove helpful abstractions that improve organization
- Prioritize "fewer lines" over readability
- Make the code harder to debug or extend

**When a change trades clarity for generalization, do not make it.** A reviewer who cannot
follow the result will not be able to maintain it, and the cost lands later on someone
with less context than you have now.

