# Merge: Inline Archive Chain (Step 10 detail)

Runs **only** for Step 9's branches **A** and **C** — the post-transition state is
terminal. Branches B, D and E skip it entirely, and so does any run with
`[workflow] skip_archive = true`, where the tracking dir stays at
`$TRACKING_DIR/$TICKET/` indefinitely and nothing further is posted beyond Step 7's
commit-id comment.

## Procedure

Log: `Post-merge state is terminal — running archive sequence inline.`

Docs were already pushed in Step 7. This step only moves the **local tracking
directory** — it posts nothing.

Invoke `/slopstop:archive` against `$TICKET` as a Skill invocation. The user already
confirmed the merge in Step 3, and that confirmation covered the inline archive for
terminal tickets, so `:archive` proceeds **without its own confirm prompt** — treat this
invocation as `skip_confirm = true` regardless of the project config.

On success, print the archive result below the Step 9 summary, as a continuation of the
output after Step 9 completes.

On failure (divergence stop, unexpected state, anything else) surface the error and
continue — the merge succeeded, so archive failure is non-fatal:

```
⚠️ Archive failed: <error summary>. The merge is complete. Re-run /slopstop:archive manually when ready.
```
