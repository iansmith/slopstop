# slopstop — invite message

_A short, ready-to-send message for Claude Code-using friends. Paste it into Slack / email / a DM. The link points at the hands-on quickstart._

---

## Message

If you use Claude Code, you've probably watched it confidently write code that
passes no tests, quietly drifts from what you actually asked for, and buries a
bug or two on the way. **slopstop** is a plugin that puts guardrails around that.

It's a **ticket-anchored workflow**: every change starts from a ticket (a GitHub
Issue — or Linear / JIRA), Claude writes the **failing tests first** to pin down
the expected behavior, then implements until they pass, runs a simplify +
self-review pass, and opens the PR — all through a few slash commands
(`/slopstop:start`, `:plan`, `:pr`, `:merge`).

The whole point is to stop the slop *before* it lands, instead of cleaning it up
afterward.

There's a 15-minute hands-on quickstart — you spin up an example repo from a
template and take a real bug from ticket to merged PR, so you see the whole loop
once with your own hands:

👉 **https://github.com/iansmith/slopstop/blob/master/QUICKSTART.md**

---

## Even shorter (one-liner for a busy channel)

> slopstop is a Claude Code plugin that makes AI work ticket-first and
> tests-first — plan → red tests → code → review → PR, so the slop gets caught
> before it lands. 15-min hands-on quickstart:
> https://github.com/iansmith/slopstop/blob/master/QUICKSTART.md
