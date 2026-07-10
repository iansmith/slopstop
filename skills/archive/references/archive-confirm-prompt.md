# archive-confirm-prompt — Step 2 interactive prompt

Show what will happen and get explicit approval:

> About to archive $TICKET:
>
> `mv $TRACKING_DIR/$TICKET/ → $ARCHIVE_DIR/$TICKET/`
>
> (Documentation is not pushed by this step — run `/slopstop:document` separately if needed.)
>
> Proceed? (yes / no)

- `yes`: move the tracking dir.
- `no`: stop. No state changed.
