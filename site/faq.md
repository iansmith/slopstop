---
layout: article
title: FAQ
subtitle: Objections to AI-written code, answered with how slopstop actually works
---

For senior software engineers evaluating whether AI-generated code belongs in production.

---

**How does slopstop avoid slop being in my generated code?**

Slopstop writes failing tests *before* the implementation agent is launched, commits them at a frozen SHA, and mechanically prohibits the implementing agent from modifying any frozen test file — a byte-level `git diff` against the baseline SHA runs after implementation, and any change is a hard stop with no permissive setting. After implementation, a mutation-testing pass breaks every changed production symbol and checks whether any test notices; surviving mutations are defects. A separate vacuity check re-runs the branch's tests against the *pre-branch* code — a test that passes against the old code pins nothing and is flagged regardless of whether it also passes against the new code. The code that ships is code that made untouchable tests go green, was proven non-vacuous, and survived mutation.

---

**How does slopstop prevent hallucinations?**

Tests are written and committed before the implementation agent exists, so a test that references a hallucinated API, a nonexistent dependency, or a fabricated method signature fails for the wrong reason — an import error or a missing symbol, not an assertion failure. The mutation-check at stage 5 classifies *why* each test fails and rejects infrastructure failures; only tests that fail because the asserted behavior is genuinely absent are accepted as valid red tests. The implementation must then make those tests pass against the real codebase. If the API doesn't exist, the tests can't go green — there is no path through that route that doesn't involve real, working code.

---

**How does slopstop avoid spaghetti code?**

A complexity check at stage 9 measures cyclomatic complexity via `lizard` against configured thresholds (default: warn at 5, reject at 10) and file size (default: warn at 400 NLOC). New complexity introduced by the branch is gated; pre-existing complexity is exempted but tracked as a work queue for dedicated refactor tickets — it's not an excuse to pile on more. A separate slop-check flags over-engineering, duplicated abstractions, and parallel naming in the diff. The review worker — running in a forked context with no access to the authoring conversation — catches the same class of problem from a second angle. And the simplify pass, when invoked, hunts specifically for unnecessary abstraction and duplicated logic.

---

**How does slopstop avoid the problem of "AI writing the tests to confirm the implementation that the AI wrote?"**

Three structural separations prevent this circularity. First, temporal: tests are authored and committed at a frozen SHA before the implementation agent is launched — the implementing worker receives the test suite as a constraint it cannot modify, not output it authored. Second, adversarial: between test-writing and implementation, an adversary worker attacks the test suite for missing coverage against the *ticket's goals* (not against code, which doesn't exist yet), adding gap tests that must also be red before implementation begins. Third, vacuity: after implementation, every test is re-run against the pre-branch code — a test that passes against the old code proves it doesn't pin any new behavior and is flagged as vacuous. The tests define the contract before the code exists, are attacked for gaps by a separate agent, and are proven non-trivial by execution against a baseline — none of that is available to an agent confirming its own implementation.

---

**When you say a "ticket," what does that mean in slopstop?**

A ticket is a GitHub or Linear issue that slopstop both *generates* and *documents*. The `:design` skill grills the human to shared understanding and writes a PRD; `:tickets` cuts that PRD into an adversary-approved tree of issues, each with observable behaviors, a file map (which files should be touched), explicit out-of-scope boundaries, and a Definition of Done with checkboxes — not vague descriptions, but statements like "A server listening on a strict subset of its declared set is reported `partial`, not `up`." One ticket = one branch = one PR. After the work merges, the archive stage auto-documents back onto the ticket: it posts one comment per tracking file — the task plan with DoD scored post-merge, the findings log, the full `run.jsonl` timing/state record, and the per-launch compute record with model, tokens, and active seconds — each verified byte-identical to disk. The ticket becomes a self-contained audit trail: what was asked for, what was built, what was verified, and what it cost. See [AATK-80](https://linear.app/mazarin/issue/AATK-80/implement-the-exact-listen-set-check-design-62-declared-ports-are) for a real completed example — precise observable behaviors in the body, and a closing comment that names what changed, what didn't, and where the original ticket description was wrong.
