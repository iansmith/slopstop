#!/usr/bin/env python3
"""Merge slopstop's subagent recorder into ~/.claude/settings.json. Idempotent.

    python3 tools/hooks/install-hooks.py            # show what would change
    python3 tools/hooks/install-hooks.py --apply    # write
    python3 tools/hooks/install-hooks.py --remove   # take it back out

USER LEVEL, DELIBERATELY.  Hooks merge across ~/.claude/settings.json (all projects),
.claude/settings.json (per project, committable) and .claude/settings.local.json (per project,
gitignored). Installing once at user level covers every repo in the fleet with no per-repo
file, no .gitignore change, and nothing committed -- which matters because the fleet's
.gitignore un-ignores only .claude/{rules,skills,agents}, so a per-repo hook config would be
ignored and silently absent.

The cost, stated rather than discovered: this is MACHINE-LOCAL. A fresh clone, another
contributor, or CI gets no hooks. That is correct while testing; fleet-wide use needs the
per-repo committed form, which is deliberately not this ticket.

The recorder scopes itself by looking for .slopstop/ above cwd, so firing in unrelated projects
costs one process that exits 0.
"""

import argparse
import copy
import json
import pathlib
import sys

SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"
HOOK = pathlib.Path(__file__).resolve().parent / "slopstop_hook.py"
MARKER = "slopstop_hook.py"

# `async` so the recorder never sits in the run's path; a short timeout because appending one
# line cannot legitimately take longer, and a hung recorder must not become a stalled run.
def entry():
    return {"type": "command", "command": f"python3 {HOOK}", "async": True, "timeout": 10}


# No `matcher`: every subagent is worth recording, and a matcher listing slopstop-effort-* by
# name would silently stop recording the moment a launch falls back to general-purpose -- which
# is precisely the event the record exists to catch.
EVENTS = ("SubagentStart", "SubagentStop", "StopFailure")


def load():
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text() or "{}")
    except json.JSONDecodeError as e:
        sys.exit(f"{SETTINGS} is not valid JSON ({e}) — refusing to touch it")


def mutate(cfg, remove=False):
    cfg = copy.deepcopy(cfg)
    hooks = cfg.setdefault("hooks", {})
    changed = []
    for ev in EVENTS:
        groups = hooks.setdefault(ev, [])
        # Idempotence is by CONTENT, not by position: drop any group that already points at this
        # script, then re-add. Appending blindly is how a settings file grows a duplicate hook
        # per install and fires the recorder N times.
        kept = [g for g in groups
                if not any(MARKER in str(h.get("command", "")) for h in g.get("hooks", []))]
        dropped = len(groups) - len(kept)
        if remove:
            if dropped:
                changed.append(f"{ev}: removed {dropped}")
        else:
            kept.append({"hooks": [entry()]})
            changed.append(f"{ev}: installed" if not dropped else f"{ev}: replaced {dropped}")
        if kept:
            hooks[ev] = kept
        else:
            hooks.pop(ev, None)
    if not hooks:
        cfg.pop("hooks", None)
    return cfg, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()

    if not HOOK.exists():
        sys.exit(f"recorder missing at {HOOK}")
    before = load()
    after, changed = mutate(before, remove=args.remove)

    print(f"  settings: {SETTINGS}")
    print(f"  recorder: {HOOK}")
    for c in changed:
        print(f"    {c}")
    if before == after:
        print("  already in the desired state — nothing to do")
        return 0
    if not args.apply:
        print("\n  dry run — nothing written. Re-run with --apply.")
        return 1
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(after, indent=2) + "\n")
    print("\n  written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
