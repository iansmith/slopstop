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

    conf_path = pathlib.Path(args.conf)
    if not conf_path.is_absolute():
        conf_path = pathlib.Path.cwd() / conf_path
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
