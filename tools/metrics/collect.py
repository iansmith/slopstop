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

import active
import conventions
import ghapi
import github_source
import markers
import pricing
import signals
import spans
import spawns
import tokens
import version

SCHEMA = "slopstop.derived-metrics/2"


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
        "spans": None,
        "spawns": None,
        "active": None,
        "version": None,
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
        # slopstop's own checkout, which is NOT project_root when collecting for
        # a consumer repo. Derived from this file's location rather than config
        # because collect.py always ships inside the slopstop checkout, so the
        # path is a fact about the running code and cannot drift out of sync.
        # #453 reads git tag history from here to date a ticket to a version.
        "slopstop_root": pathlib.Path(__file__).resolve().parent.parent.parent,
    }

    # Order is a dependency order, fixed here so downstream tickets fill in one
    # module each and never re-touch this file (the #382 pattern): timing first,
    # since version dates against it and tokens windows on it; pricing after the
    # tokens it prices; active after the spans and spawns it decomposes.
    github_source.collect(record, ctx)
    version.collect(record, ctx)
    tokens.collect(record, ctx)
    pricing.collect(record, ctx)
    spans.collect(record, ctx)
    spawns.collect(record, ctx)
    active.collect(record, ctx)
    markers.collect(record, ctx)
    signals.collect(record, ctx)

    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
