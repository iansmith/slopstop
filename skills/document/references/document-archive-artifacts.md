# Archiving the PRD and charter to the umbrella ticket

Posts `prd.md` and `charter.md` — the two `:design`-stage artifacts that live in
`scratch/runs/$RUN_ID/` and are never committed — to a run's umbrella ticket, so
they survive the run dir being cleaned. This is the procedure both
`run-final-report.md` (fleet completion, `:run` Step 8) and `merge-archive-chain.md`
(non-fleet completion, `:merge` Step 10) reach at their respective terminal points.
Reuses the comment-posting primitives in `document-push-backends.md` — no new
posting mechanism.

## Trigger point

When the run's umbrella ticket reaches a terminal state:
- Fleet path: `:run` Step 8's final report, after G-final.
- Non-fleet path: `:merge` Step 10's terminal-state archive chain, after the
  existing `:archive` invocation.

Not at `:design` time — the PRD is a draft until the tree is cut, and `:tickets` or a
rewrite round may still amend it.

## No umbrella case

Freestanding leaves and `:single-ticket` runs have no umbrella ticket. In that case:
do not post anywhere, do not fail — report where the files remain on disk
(`scratch/runs/$RUN_ID/prd.md` and `.../charter.md`).

## Posting — two separate comments

Post `prd.md` and `charter.md` as **two separate comments**, not one combined
comment — they are separate artifacts with separate audiences (the PRD is the
what/why, the charter is the per-run coding rules) and concatenating them makes
both harder to find.

Each comment opens with the provenance header `:design` already writes to the
artifact itself, plus an `artifact:` field this procedure adds — the bare
`:design` header is identical for the PRD and charter comments from the same
run, so without it the idempotency check below cannot tell the two comments
apart:

```
> Provenance: <model> · <date> · run <run-id> · artifact: prd
```

(`artifact: charter` for the charter comment), followed by the artifact body
verbatim.

Use `document-push-backends.md` 6b's per-backend "post a new comment" primitives
(JIRA `addCommentToJiraIssue`, Linear `save_comment`, GitHub MCP
`add_issue_comment`, GitHub CLI `gh issue comment`) to post.

## Idempotency — scoped to run-id

Re-running this procedure (a re-driven run, a retried `:merge`) must not duplicate
the comments. The dedup key is **run-id + artifact name** (`prd` or `charter`), not
"does the umbrella already have any archive comment" — an umbrella ticket can
receive artifacts from more than one run over its lifetime, and keying on presence
alone would match (and overwrite) a *different* run's PRD/charter comment.

- List the umbrella ticket's existing comments and search for one whose body opens
  with the provenance header carrying **this run's run-id** and **this artifact's
  name**.
- Found → update it in place, using `document-push-backends.md` 6b's
  divergent+`--force` edit-comment primitive (GitHub MCP `update_issue_comment`,
  GitHub CLI `gh api -X PATCH .../issues/comments/$ID`). If the backend doesn't
  expose edit-comment (some JIRA/Linear MCP installs), post a new comment and leave
  the old one, same as 6b.
- Not found → post new, per "Posting" above.

## Failure posture

Best-effort, matching `:merge` Steps 5 and 7: on failure, warn and continue — never
roll back a merge or block a run's completion.

## Outcome reporting

The calling step (`run-final-report.md`'s Archive confirmation line,
`merge-archive-chain.md`'s Step 10 addition) reports the real outcome per artifact,
not a bare success assertion:

- **posted** — new comment created.
- **already present** — existing comment for this run-id found and updated.
- **failed** — attempted and failed, with the reason.
- **no umbrella** — no umbrella ticket; files remain at
  `scratch/runs/$RUN_ID/<artifact>.md`.
