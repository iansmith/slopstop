# archive-confirm-prompt — Step 3 interactive prompt

Show what will happen and get explicit approval (partially irreversible — hits the ticket system):

> About to archive $TICKET (currently in '<state name>'):
>
> 1. Push documentation to $SYSTEM via `/slopstop:document` — description body (with current ticket description preserved as `## Original description (preserved)`), DoD-confirmation comment (if `task_plan.md` has a Definition of Done section), and findings comment (if `findings.md` has content). Already-current artifacts are skipped cleanly. **If any artifact has a managed version on the ticket that differs from local** (someone hand-edited the ticket, or another session pushed different content), archive STOPS here without moving local tracking — you'd run `/slopstop:document --force` separately to overwrite, then re-run `/slopstop:archive`.
> 2. `mv ~/.claude/ticket-active/$TICKET/ → ~/.claude/ticket-archive/$TICKET/`
>
> Proceed? (yes / no / skip-push)

- `yes`: all steps.
- `skip-push`: skip the documentation push — jump straight to local mv. Useful when the ticket is already documented (e.g. via a prior standalone `:document` run).
- `no`: stop.
