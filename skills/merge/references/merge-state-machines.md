# merge-state-machines.md — Full preference-ranking algorithms for Step 2

Used by `/slopstop:merge` Step 2 to compute the next ticket state per system.

## JIRA — `$NEXT_TRANSITION` computation

1. **Exclude** transitions whose target name matches `/won.?t do|cancel|reject|abandon|invalid|duplicate/i` (negative completion).
2. **Prefer same-category** transitions — ones whose target's `statusCategory.key` equals the current category. This is the "advance one slot within the same bucket" rule (e.g., from `indeterminate`, prefer another `indeterminate` like "In Review" rather than jumping to `done`).
3. Within the same-category set, prefer target name matching `/review|qa|verify|test|pending|ready|merged|shipped/i` (forward-progress idioms).
4. **If no same-category candidates exist** (workflow has no intermediate state), fall back to category-advancing transitions — i.e., `indeterminate` → `done`. Among those, prefer target name `/^done$/i` exactly, then `/done|closed|resolved|complete|fixed/i`.
5. **If multiple still tie**, pick the first.
6. **If nothing remains after exclusions**: `$NEXT_TRANSITION = null`. Note this for Step 3.

## Linear — `$NEXT_STATE` computation

1. **Exclude** states with `type === "canceled"` and, defensively, states whose name matches `/won.?t do|cancel|reject|abandon|invalid|duplicate/i`.
2. **Prefer same-type advance**: among states with `type === <current.type>` AND `position > current.position`, pick the one with the **smallest** position (the immediate next slot). E.g., from "In Progress" (`type: started`, `position: 2`), advance to "In Review" (`type: started`, `position: 3`).
3. **If no same-type advance** exists, advance the type: pick the state with the **lowest position** among `type === "completed"` (the next bucket up). Apply the name preference `/^done$/i` then `/done|merged|shipped|complete|fixed|closed|resolved/i`.
4. **If multiple still tie**, pick lowest position then first.
5. **If nothing remains**: `$NEXT_STATE = null`. Note this for Step 3.

## GitHub — `$NEXT_GH_ACTION` computation

Github has no introspectable workflow — the shape is declared in `.project-conf.toml`'s `[status_labels]`. No "preference logic" needed; the dispatch is hardcoded by workflow shape.

Compute `$NEXT_GH_ACTION` based on workflow shape:

- **3-state** (`$IN_REVIEW_LABEL` empty): from `OPEN-in-progress` → `{kind: "close-and-remove-label", remove: $IN_PROGRESS_LABEL}` (close issue + remove the label). From any other current state → leave `$NEXT_GH_ACTION = null` (already terminal or in a non-standard state; merge proceeds, transition step becomes a no-op).
- **4-state** (`$IN_REVIEW_LABEL` set): from `OPEN-in-progress` → `{kind: "swap-labels", remove: $IN_PROGRESS_LABEL, add: $IN_REVIEW_LABEL}` (remove in-progress, add in-review; issue stays open). From `OPEN-in-review` or `CLOSED` → `$NEXT_GH_ACTION = null` (already past in-progress).

Human-readable target for Step 3's confirmation prompt:
- `{kind: "close-and-remove-label", ...}` → `"Close issue + remove '$IN_PROGRESS_LABEL' label"`.
- `{kind: "swap-labels", ...}` → `"Remove '$IN_PROGRESS_LABEL', add '$IN_REVIEW_LABEL' (issue stays open)"`.
- `null` → `"already past in-progress — no transition needed"`.

## Already-terminal handling

If the current state is already terminal (JIRA `status.statusCategory.key === "done"`, Linear `state.type` is `"completed"` or `"canceled"`, GitHub `state === "CLOSED"`): set `$NEXT_TRANSITION` / `$NEXT_STATE` / `$NEXT_GH_ACTION` to `null`. The merge can still proceed; the transition step becomes a clean no-op. Surface this in Step 3 as `"already terminal — no transition needed"`.
