# The five-section leaf-ticket standard

Every leaf ticket the slopstop process creates follows this standard. The consumer is
a **haiku-class model**: whatever isn't in the ticket effectively doesn't exist for the
implementer. Stage 2's ticket-writing does the thinking the small model can't — the
five sections *are* the investigation, pre-done by the medium tier.

Umbrella tickets are exempt (they carry scope and structure, not implementation
contracts). Process context: [slopstop-process.md](slopstop-process.md) §6.

> Interim home: this doc moves to the `:tickets` skill's `references/` when that skill
> lands (BILL-173); the standard itself is unchanged by the move.

## The five sections — with authoring guidance

### 1. Observable behaviors (2–5)

Concrete, testable statements of what changes. Each one should be checkable by a
person (or adversary) who has only the merged code and this ticket. Not "improve the
config handling" — instead "`.project-conf.toml.example` parses as TOML and carries
`[tiers]` with big/medium/small". **Two to five** — fewer means the ticket is
underspecified; more means it should be split.

### 2. File map

The exact files expected to be touched, and *why each one*. This does double duty:

- It is the small agent's **roadmap** — under `:plan --ticket-driven` the file map is
  the territory; there is no free investigation to discover it.
- It drives the orchestrator's **launch ordering** (file-affinity) and the
  **file-map violation kill** — an agent writing outside its map is killed
  mechanically.

Entries may be **directory-granular where exact filenames are unknowable at cut
time** — e.g. `tests/ — new behavior tests` (the new test file's name doesn't exist
yet). The violation kill treats a directory entry as covering everything under it.
If the author cannot name the files *or directories*, the ticket isn't ready to be a
leaf.

### 3. Definition of done

The checklist the handoff adversary later scores against — written at ticket-creation
time, not discovered later, so the adversary and the implementer read the *same*
contract. Every item must be verifiable from artifacts (code, test output, git state),
not from the implementer's claims.

### 4. Out of scope

Explicitly named temptations: "do NOT refactor the adjacent module", "do NOT touch the
schema". Small models drift by helpfulness; fences must be written down. Anything
fenced out here must have an owner elsewhere (another ticket) if the PRD requires it —
an out-of-scope entry with no owning ticket is a coverage hole the tree adversary
rejects.

### 5. Test expectations

Which tests must newly pass (named, with intent — the agent transcribes these into red
tests before implementing) and which existing suites must stay green. This is where
test-authoring risk shifts left: the medium tier decides *what to test*; the small
model only writes it down as code and shows it failing first.

## Copyable template

```markdown
> Provenance: <model> · <date> · run <run-id> · PRD: <prd reference>

Parent: <umbrella ref>. Blocked by: <refs, or "nothing">.

**Observable behaviors**
1. <concrete, testable statement>
2. <...>   (2–5 total)

**File map**
- `<path>` — <why this file>
- <...>

**Definition of done**
- [ ] <artifact-verifiable item>
- [ ] Test suite green

**Out of scope**
- Do NOT <named temptation>

**Test expectations**
- New: <named tests + intent>
- Existing suite stays green (<test command>)
```

## The structural check — mechanical precondition

Any adversary reviewing a ticket tree runs this check **first**, before any content
judgment. It is mechanical — no model reasoning required — and a ticket failing it is
rejected without further review:

- [ ] All five sections present and **non-empty**.
- [ ] Observable behaviors count is between **2 and 5**.
- [ ] File map names concrete paths or directories (not "various files";
      directory-granular entries are sanctioned where filenames are unknowable
      at cut time).
- [ ] Provenance header present: model, date, and a run-id — or a stage label
      (e.g. "v3 bootstrap Stage 2") for tickets cut outside a `:design` run —
      plus a PRD reference.
- [ ] A parent link (leaf tickets always live under an umbrella).

Only after a ticket passes structure does the adversary judge content: conformance to
the PRD + charter, omissions, scope drift, implementability, face-value traps.

## Version convention — rewrites

A failure-driven rewrite creates a **new contract**: fresh agent, fresh attempt
budget (see [slopstop-process.md](slopstop-process.md) §7e). Mark versions in the
ticket **title**:

```
Add webhook retry           ← V1 (unmarked)
Add webhook retry (V2)      ← first rewrite
Add webhook retry (V3)      ← second rewrite — with the default 3-version
                              budget, the last before G4 ([fleet.budget]
                              governs the actual cap)
```

The version marker makes the run ledger self-documenting in every ticket list. Every
rewrite must cite the specific code and instruction that failed the previous attempt,
and passes a big-tier delta check (specificity added, scope not subtracted) before any
relaunch.
