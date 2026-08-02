#!/usr/bin/env python3
"""CLI entrypoint: assembles the derived-metrics record for one ticket.

Usage: python3 tools/metrics/collect.py <TICKET> [--conf PATH]
"""

import argparse
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import conventions
import ghapi
import github_source
import markers
import pricing
import signals
import tokens

SCHEMA = "slopstop.derived-metrics/1"


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket")
    parser.add_argument("--conf", default=".project-conf.toml")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # Resolving anchors a relative --conf to cwd and normalises it, which is
    # what lets conf_path.parent below stand in for the project root.
    conf_path = pathlib.Path(args.conf).resolve()
    conv = conventions.load(conf_path)

    if not args.ticket.startswith(f"{conv.prefix}-"):
        print(
            f"{args.ticket} does not match prefix '{conv.prefix}' in .project-conf.toml",
            file=sys.stderr,
        )
        return 1

    record = {
        "schema": SCHEMA,
        "ticket": args.ticket,
        "system": conv.system,
        "repo": conv.repo,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "timing": None,
        "tokens": None,
        "phases": None,
        "signals": None,
    }

    ctx = {
        "conventions": conv,
        "gh_api": ghapi.gh_api,
        "transcript_root": pathlib.Path.home() / ".claude" / "projects",
        # The conf file sits at the repo root, so its parent IS the project
        # root -- true for an out-of-root invocation (`cd tests && collect.py
        # --conf ../...`) too, which is why cwd cannot be used instead: cwd
        # there encodes to a transcript directory that exists nowhere, and a
        # missing directory yields zero tokens silently.
        "project_root": conf_path.parent,
    }

    github_source.collect(record, ctx)
    tokens.collect(record, ctx)
    pricing.collect(record, ctx)
    markers.collect(record, ctx)
    signals.collect(record, ctx)

    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
