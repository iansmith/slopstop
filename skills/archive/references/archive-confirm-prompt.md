# archive-confirm-prompt — Step 2 interactive prompt

Show what will happen and get explicit approval:

> About to archive $TICKET:
>
> `mv ~/.claude/ticket-active/$TICKET/ → ~/.claude/ticket-archive/$TICKET/`
>
> (Documentation was already pushed to $SYSTEM by :merge. Text DB re-harvest will run if enabled.)
>
> Proceed? (yes / no)

- `yes`: move the tracking dir.
- `no`: stop. No state changed.
