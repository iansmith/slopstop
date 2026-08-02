#!/usr/bin/env python3
"""Stub for BILL-382 Phase 0 -- entrypoint not yet implemented."""
import argparse
import json
import sys


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket")
    parser.add_argument("--conf", default=".project-conf.toml")
    return parser.parse_args(argv)


def main(argv=None):
    parse_args(argv if argv is not None else sys.argv[1:])
    print(json.dumps({"stub": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
