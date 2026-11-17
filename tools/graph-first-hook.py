#!/usr/bin/env python3
"""PreToolUse hook: graph for discovery, grep for content — enforced, not requested.

Registered on Bash, Grep and Glob. Blocks a search over the tree unless the call
carries a content marker, and logs every decision so the discovery/content split
is measured by the harness rather than self-reported.

Blocked:
  - Grep / Glob tool calls (always; the marker cannot be attached to them).
  - Bash where grep, rg, ug, ag or find STARTS a pipeline segment — i.e. it is
    searching the tree, not filtering another command's output — and the command
    has no `# content: <reason>` marker.

Allowed without a marker:
  - grep/rg/find fed by a pipe (`go test ./... | grep FAIL`, `ls | grep foo`):
    that is filtering output, which is content.
  - anything that is not one of the search commands.

Allowed with a marker:
  - `grep -rn SOPHIE_DB_URL . # content: env var, not code` — logged as marked.

Log: $CLAUDE_PROJECT_DIR/.slopstop/graph-first.log if that directory exists,
else ~/.claude/graph-first.log. One JSON line per decision.

Exit 2 blocks the call and feeds stderr to the model. Exit 0 lets it through.
"""
import json
import os
import re
import sys
import time

SEARCH = re.compile(r"^\s*(?:sudo\s+)?(?:GOWORK=\S+\s+)?(grep|rg|ug|ag|find|git\s+grep)\b")
MARKER = re.compile(r"#\s*content:\s*(.+?)\s*$", re.M)
SPLIT = re.compile(r"\|\||&&|;|\n|\(")  # segment boundaries that are NOT a pipe


def segments(cmd):
    # a segment fed by `|` is filtering; only the head of a non-pipe segment counts
    for chunk in SPLIT.split(cmd):
        head = chunk.split("|", 1)[0]
        yield head


def tree_search(cmd):
    for head in segments(cmd):
        m = SEARCH.match(head)
        if m:
            return m.group(1)
    return None


def log(entry):
    proj = os.environ.get("CLAUDE_PROJECT_DIR", "")
    d = os.path.join(proj, ".slopstop") if proj else ""
    path = os.path.join(d, "graph-first.log") if d and os.path.isdir(d) else os.path.expanduser("~/.claude/graph-first.log")
    try:
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}
    base = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "session": data.get("session_id", "")[:8], "tool": tool}

    if tool in ("Grep", "Glob"):
        log({**base, "decision": "blocked", "arg": (inp.get("pattern") or "")[:80]})
        sys.stderr.write(
            f"{tool} is blocked in this repo: it is discovery by text search.\n"
            "Use search_graph (symbols), trace_path (callers/callees), search_code (graph-ranked text),\n"
            "get_architecture (layout). For a content read of a file you already located, use Read or sed -n.\n"
            "If the graph genuinely cannot answer, run the same search in Bash with a trailing\n"
            "`# content: <why the graph cannot answer>` marker.\n"
        )
        return 2

    if tool != "Bash":
        return 0
    cmd = inp.get("command", "") or ""
    hit = tree_search(cmd)
    if not hit:
        return 0
    mk = MARKER.search(cmd)
    if mk:
        log({**base, "decision": "marked", "cmd": cmd[:120], "reason": mk.group(1)[:120]})
        return 0
    log({**base, "decision": "blocked", "cmd": cmd[:120]})
    sys.stderr.write(
        f"`{hit}` over the tree is blocked: that is discovery by grep (Rule A).\n"
        "Finding a definition -> search_graph. Finding callers -> trace_path. Finding a literal string,\n"
        "TODO, or log message -> search_code. Reading a located file -> Read or sed -n.\n"
        "If this is genuinely content (non-code file, test output, a file check_index_coverage reports\n"
        "uncovered), re-run it with a trailing marker:  <same command>  # content: <reason>\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
