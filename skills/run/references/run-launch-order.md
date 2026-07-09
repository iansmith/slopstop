# Run: Launch Order (Step 3 detail)

Order agents so that **if they all succeed, integration is conflict-free by
construction** — this converts a hard N-way merge into a sequence of trivial ones.
Carried from the retired fleet doc via `design/slopstop-process.md` §7b.

## The algorithm

1. **Collect file maps** from every leaf's File map section. Directory-granular
   entries (`tests/`) count as their whole subtree for overlap purposes.
2. **Explicit relations first:** `Blocked by:` lines and umbrella structure are hard
   edges — a ticket never launches before its blockers are *integrated* (not merely
   "done": §7d verification and §7f `:merge` must have landed them on the tip).
3. **File affinity second:** among unblocked tickets, disjoint file maps → launch in
   parallel; overlapping maps → serialize. The later ticket launches only after the
   earlier one is integrated, and its worktree forks from the **updated tip**, so it
   builds on the landed work instead of colliding with it.
4. When the heuristic and an explicit relation disagree, the explicit relation wins.

## Practical notes

- Recompute the frontier after every integration: newly-unblocked tickets join the
  launch queue; their fork SHA is always the current tip.
- The parallel-safe first wave from the G2 draft's dependency summary is a starting
  hint, not the authority — recompute from the actual tickets.
- Overlap detection is path-prefix comparison, nothing fancier: two maps overlap if
  any entry of one is a prefix of (or equal to) an entry of the other.
- Record the computed order and every frontier recomputation in `fleet-state.md`.
