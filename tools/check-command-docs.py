#!/usr/bin/env python3
"""Fail when the skills on disk and the commands documented in COMMANDS.md disagree.

    python3 tools/check-command-docs.py             # this repo
    python3 tools/check-command-docs.py ../slopstop # some other checkout

Exits 0 when they agree, 1 when they do not, 2 on a usage error.

WHY THIS FILE EXISTS.  A doc survey on 2026-08-16 found four claims in the root docs that
the skills contradicted outright -- stage 3 documented as `git switch -c` a week after it
became a worktree, the stage-9 gates justified by a reason `run/SKILL.md` explicitly
corrects, `implement` described as never touching tests when its own body says it may add
them, and two shipping skills still reading a `[autonomous]` config table deleted on
2026-08-06.  None of it was caught because nothing checks the docs against the tree.

WHAT THIS CHECKS, AND WHY ONLY THIS.  Structural facts: does a documented command have a
skill, does a skill on disk appear in the docs, does a config key named in a root doc exist
in the example config.  It does NOT scan prose.  This repo deliberately deleted ~4,500
lines of tests whose job was asserting on the content of its own markdown -- they pinned
wording, proved no behavior, and could not catch the failures that actually occurred (see
CLAUDE.md, `## Tests`).  A checker that greps for a sentence is that mistake again.  A
checker that asks "does this file exist" is not: it would have caught three of the four.

WHAT IT CANNOT CATCH.  A command documented with the wrong description, a stage table that
drifted from the skill it describes, a config key documented with the wrong default.  Those
need a reader.  This narrows the surface a reader has to cover; it does not replace one.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The six commands a human types.  COMMANDS.md documents these and only these.
#
# This list is the ONE place the split lives.  Frontmatter cannot supply it:
# `disable-model-invocation` marks four of the six (design, tickets, run, doc-sync) and
# none of the other two, so deriving the set from frontmatter would silently drop `grill`
# and `gh-init` -- both of which a human very much types.
USER_COMMANDS = {"design", "tickets", "run", "grill", "gh-init", "doc-sync"}

# The workers.  Launched as agents by the orchestrators; never typed.  COMMANDS.md names
# them in one place -- its "What is not a command" section -- so a reader who meets a
# verdict string can find out what produced it.
WORKERS = {
    "adversary", "archive", "complexity-check", "create-ticket", "implement",
    "investigate", "mutation-check", "red-tests", "review", "slop-check", "vacuity-check",
}

# Root docs whose config-key claims are checked against the example config.
ROOT_DOCS = ("README.md", "COMMANDS.md", "QUICKSTART.md", "SETUP-GUIDE.md", "REPORT.md")

# `[section] key` or `[section].key` as written in prose, inside backticks.
CONFIG_KEY = re.compile(r"`\[([a-z_]+)\]\s*\.?\s*([a-z_]+)`")

# Config sections that exist but carry no keys we can check this way, plus tables that are
# documented as REMOVED -- naming a deleted table to say it is deleted is correct.
CONFIG_EXEMPT_SECTIONS = {"autonomous", "exp", "fleet"}


def fail(problems: list[str], heading: str) -> None:
    print(f"\n{heading}", file=sys.stderr)
    for p in problems:
        print(f"  {p}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".", help="repo root (default: cwd)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / "skills").is_dir():
        print(f"{root} has no skills/ -- not a slopstop checkout", file=sys.stderr)
        return 2

    commands_md = root / "COMMANDS.md"
    if not commands_md.is_file():
        print("COMMANDS.md is missing", file=sys.stderr)
        return 2
    text = commands_md.read_text(encoding="utf-8")

    on_disk = {p.name for p in (root / "skills").iterdir() if (p / "SKILL.md").is_file()}
    problems: list[str] = []

    # 1. Every skill on disk is accounted for as either a command or a worker.
    unclassified = on_disk - USER_COMMANDS - WORKERS
    for name in sorted(unclassified):
        problems.append(
            f"skills/{name}/ exists but is in neither USER_COMMANDS nor WORKERS in this "
            f"script. A new skill must be classified before it can be checked."
        )

    # 2. Every name we classify actually exists.
    for name in sorted((USER_COMMANDS | WORKERS) - on_disk):
        problems.append(
            f"'{name}' is classified in this script but skills/{name}/SKILL.md does not "
            f"exist. Renamed or deleted?"
        )

    # 3. Every user command is documented in COMMANDS.md, by its invocation form.
    for name in sorted(USER_COMMANDS & on_disk):
        if f"/slopstop:{name}" not in text:
            problems.append(
                f"COMMANDS.md never mentions /slopstop:{name}, but skills/{name}/ exists "
                f"and it is a command a human types."
            )

    # 4. Every worker is named in COMMANDS.md so its verdicts are traceable.
    for name in sorted(WORKERS & on_disk):
        if f"`{name}`" not in text:
            problems.append(
                f"COMMANDS.md never names the `{name}` worker. A reader who is handed one "
                f"of its verdicts has nowhere to look it up."
            )

    # 5. COMMANDS.md must not advertise a worker as a slash command.
    #
    # Match the DOCUMENTED form -- a heading or a table row -- not the bare string.  The
    # naive `f"/slopstop:{name}" in text` check fires on COMMANDS.md's own sentence "There
    # is no `/slopstop:implement`", which is the doc being right.  A checker that demands an
    # edit to a correct doc gets muted, and then it is worth nothing.
    heading_or_row = re.compile(
        r"^(?:#{1,6}\s*|\|\s*)`?/slopstop:([a-z-]+)", re.MULTILINE
    )
    advertised = set(heading_or_row.findall(text))
    for name in sorted(WORKERS & advertised):
        problems.append(
            f"COMMANDS.md documents /slopstop:{name} as a command, but {name} is a worker. "
            f"There is no slash command for it and typing it does nothing."
        )

    if problems:
        fail(problems, "COMMAND / SKILL DRIFT")

    # 6. Config keys named in root docs exist in the example config.
    example = root / ".project-conf.toml.example"
    cfg_problems: list[str] = []
    if example.is_file():
        example_text = example.read_text(encoding="utf-8")
        for doc in ROOT_DOCS:
            path = root / doc
            if not path.is_file():
                continue
            for section, key in set(CONFIG_KEY.findall(path.read_text(encoding="utf-8"))):
                if section in CONFIG_EXEMPT_SECTIONS:
                    continue
                if f"[{section}]" not in example_text:
                    cfg_problems.append(
                        f"{doc} names `[{section}] {key}` but [{section}] is not in "
                        f".project-conf.toml.example"
                    )
                elif key not in example_text:
                    cfg_problems.append(
                        f"{doc} names `[{section}] {key}` but '{key}' is not in "
                        f".project-conf.toml.example"
                    )
    if cfg_problems:
        fail(sorted(set(cfg_problems)), "CONFIG KEY DRIFT")

    total = len(problems) + len(cfg_problems)
    if total:
        print(f"\n{total} drift problem(s).", file=sys.stderr)
        return 1

    print(
        f"OK: {len(USER_COMMANDS)} commands and {len(WORKERS)} workers on disk, "
        f"all accounted for in COMMANDS.md; config keys resolve."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
