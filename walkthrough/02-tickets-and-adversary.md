[← 1. Design and grill](01-design-and-grill.md) · **2. Tickets and the adversary** · [3. The handoff →](03-handoff-and-gates.md) · [Index](README.md)

---

# 2. Tickets and the adversary

**10:26:32 – 10:52:43 · `claude-opus-5` · ends at gate G2**
Source: Transcript A, turns cited as `[n]`. Notation key: [index §3](README.md#3-notation).

Stage 2 turns the PRD into a ticket tree and then tries to destroy it. Three adversary rounds,
18 findings, and the defect that justifies the whole apparatus.

The human says nothing at all in this section. It opens with `/slopstop:tickets kvstore-20260725-1001`
at 10:26:32 and closes 26 minutes later at a gate. Everything in between is machine-checking-machine
— which is the point: the **adversary** is a freshly spawned agent that has never seen the grill,
is handed only the artifacts, and is told to prove the tickets wrong.

---

### 10:31:46 `[160]` — Self-check before the adversary

> **SLOPSTOP SAYS:** "Structural checklist over all 7 leaves and 2 umbrellas myself first — five sections non-empty, behavior counts 4/4/4/4/4/5/5 (all within 2–5), concrete paths, provenance, parent links. All pass. Now the huge-tier adversary."

**Why interesting:** the structural check passing clean is what makes the next finding meaningful.
The tree was well-formed and still wrong. Anything that only checks shape would have shipped it.

---

<a id="flock"></a>
### 10:38:13 – 10:39:12 `[164]`, `[168]` — **The adversary rejects the tree. This is the moment.**

> **ADVERSARY:** "`flock` locks an inode, but D8's temp-file-plus-rename replaces the inode, so the lock as specified would not actually prevent the lost update D13 exists to stop."

Trace it back precisely:

- **D8** (temp-file+rename) was decided at **10:14:37**, Q9, on the recommendation.
- **D13/D14** (flock on the store file) was decided at **10:18:41 / 10:19:44**, Q12–Q13, both overrides.
- They were **4 minutes apart, never cross-checked**, and the foundation ticket *"names both mechanisms without ever stating how they coexist"* `[164]`.
- The failure is invisible: process A locks the store file's inode; the rename swaps in a new inode; process B locks *that* one. Two processes hold "the lock" simultaneously.

As the model put it at 10:41:39 `[169]`:

> **SLOPSTOP SAYS:** "The lost update D13 exists to prevent survives the lock entirely, and **no test in the round-1 draft would have noticed.**"

The adversary did not only flag it — it specified the missing test by name,
`TestConcurrentUpdatesDoNotLoseWrites` (N goroutines each `Update`-increment a distinct key;
assert all N present).

It also verified byte-level claims against the real toolchain:

- `json.MarshalIndent` on a nil map yields `null`, not `{}`
- `os.WriteFile` does not chmod an existing file
- stdlib `flag` stops parsing at the first non-flag argument — so `--file` must precede the verb, meaning one ticket's precedence test would have failed spuriously **in a ticket that was fenced from fixing it**

**Round 1 — FAIL, 13 findings.**

---

### 10:41:39 `[169]` — The fix reinstates the option the grill rejected at 10:19:44

> **SLOPSTOP SAYS** *(applying the finding)*: "the lock is taken on a **sidecar file, `<store>.lock`, which is never renamed, never removed, and never read** — only locked. `View` takes a shared lock on it, `Update` an exclusive one, and the store file continues to be replaced atomically underneath."

**This is the sharpest link in the run, and it needs stating carefully.** The grill rejected
"sidecar lockfile" at 10:19:44 as a *mechanism* — `O_CREATE|O_EXCL` advisory locking, whose stated
flaw was stale locks after a crash. The adversary's fix keeps the chosen mechanism (`x/sys` flock)
and moves only the *lock target* onto a sidecar file. The 10:19:44 objection does not apply to it:
the kernel releases an flock when the process dies, and the file is never removed, so there is no
staleness problem.

The grill was right to reject what it rejected and still ended up needing the sidecar. Do not
flatten that into "the adversary undid the grill's mistake."

---

### 10:41:42 `[174]` — Round 2 is sent to the *same* adversary, and it must re-read

> **SLOPSTOP SAYS:** "Round 2 — back to the same adversary, which must **re-read rather than trust the claim of correction**."

**Why interesting:** the cheap version of this loop asks "did you fix it?" and accepts yes. The
round-2 prompt at `[177]` instead lists what changed and asks specifically whether the corrections
introduced new defects — *"Consider whether the sidecar introduces problems of its own that no
ticket owns."*

---

<a id="experiment"></a>
### 10:46:19 – 10:46:55 `[193]`, `[195]` — **Round 2: measured, not argued**

The adversary ran the experiment rather than reasoning about the fix — 20 goroutines × 40 trials,
`syscall.Flock` + temp-file-plus-rename, real filesystem:

```
mode=store   trials=40  failed(!=20 keys)=40  worst-case-keys=11
mode=side    trials=40  failed(!=20 keys)=0   worst-case-keys=20
```

> **ADVERSARY:** "The sidecar fix is correct, and `TestConcurrentUpdatesDoNotLoseWrites` is a genuinely discriminating test — it failed **40 out of 40 times** against a store-file lock, losing up to 9 of 20 writes. **I had expected this to be probabilistic; it is effectively deterministic at 20 goroutines**, so my round-1 conclusion understated it."

And the verdict is still **FAIL**: all 13 originals verified resolved, but the corrections
introduced **5 new defects, 2 blocking**.

The new findings are worth listing, because they are the kind of thing only a re-read catches:

| | Finding |
|---|---|
| N1 | error-prefix requirement landed in two layers → users would see `kv: kv: store file is corrupt` |
| N2 | `filepath.Abs` handling regressed a resolver test |
| N3 | the `<store>.lock` sidecar had no specified mode next to a deliberately-0600 store → 0600 |
| N4 | **sidecar locking makes every *read* require a writable directory; stated nowhere** |
| N5 | two test files share `package main`, so a redeclared helper is a build error, not a merge conflict |

**N4 is the one to remember.** It becomes Observable behavior 4 of the foundation ticket, and it
is the requirement an implementing agent violates 69 minutes later, at 11:55:55 in
[§4](04-fleet-execution.md).

**N1 is the second one to remember**, and the model says so itself at 10:52:43 `[272]`:

> **SLOPSTOP SAYS** *(at the G2 gate)*: "**My own fix for one finding created another.** Adding the `kv: ` prefix requirement to the store package put it in two layers, so users would have seen `kv: kv: store file is corrupt`. Neither the 'contains' assertion nor a `^kv: ` regex catches that."

---

### 10:48:34 `[235]` — The round budget is real

> **SLOPSTOP SAYS:** "Waiting on round 3 — this is the last round the process allows, so **a FAIL here goes to you rather than to the ticket system.**"

**Why interesting:** the ≤3-round bound is not decoration. The consequence of exhausting it is
stated in advance: escalate to the human, do not quietly accept. The same bound comes up again at
the very end of the run, at 13:37 in [§5](05-report-adversary.md).

---

### 10:50:55 `[247]` → 10:52:43 `[272]` — PASS, G2

Round 3 clean. **18 findings across 3 rounds** on a tree that had passed its own structural
checklist. Tree created on GitHub in dependency order, then a second pass to resolve placeholders
(the root umbrella forward-references its own children, so one pass cannot resolve everything).

The G2 gate message:

**GATE:**
```
G2 — ticket tree created for run kvstore-20260725-1001

Tree: 2 umbrellas, 7 leaves — root #1
      #2 foundation (blocking) → #4–#8 five commands (fully parallel,
      disjoint directories) → #9 integration fan-in
Adversary: PASS after 3 rounds — 18 findings total (13 round 1, 5 round 2), all fixed
```

---

## Section summary

| Round | Time | Verdict | Findings | Character |
|---|---|---|---|---|
| Self-check | 10:31:46 | PASS | 0 | structural only — shape, not truth |
| 1 | 10:39:12 | **FAIL** | 13 | one spec-level defect (flock/inode) + toolchain fact-checks |
| 2 | 10:46:55 | **FAIL** | 5 (2 blocking) | defects introduced *by the round-1 corrections*; fix validated by experiment |
| 3 | 10:50:55 | PASS | 0 | — |

The headline, in one line: **the tree passed every check it applied to itself, and the specified
lock did not lock.**

---

[← 1. Design and grill](01-design-and-grill.md) · **2. Tickets and the adversary** · [3. The handoff →](03-handoff-and-gates.md) · [Index](README.md)
