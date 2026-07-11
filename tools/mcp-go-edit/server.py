#!/usr/bin/env python3
"""go-edit MCP Server — whitespace-tolerant Edit for .go files, then gofmt.

Same contract as the built-in Edit tool, with one difference: matching
ignores whitespace shape. The `old_string` is split on whitespace runs and
each run is matched as `\\s+` against the file. After a successful
replacement, gofmt is run on the entire file. If gofmt fails (broken
syntax post-edit), the file is reverted and the tool returns an error —
atomic semantics.

Stdlib only. JSON-RPC 2.0 over stdio.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Core edit logic
# ---------------------------------------------------------------------------

def _build_pattern(old_string: str) -> re.Pattern:
    """Turn old_string into a regex where each whitespace run matches \\s+.

    Leading/trailing whitespace in old_string is stripped — the user's
    intent is the non-whitespace shape. Each non-whitespace token is
    re.escape'd; tokens are joined with \\s+.
    """
    tokens = re.split(r"\s+", old_string.strip())
    if not tokens or tokens == [""]:
        raise ValueError("old_string is empty after whitespace strip")
    escaped = [re.escape(t) for t in tokens]
    return re.compile(r"\s+".join(escaped))


def _gofmt(file_path: str) -> tuple[bool, str]:
    """Run `gofmt -w` on file_path. Returns (ok, stderr)."""
    gofmt = shutil.which("gofmt") or "/usr/local/go/bin/gofmt"
    proc = subprocess.run(
        [gofmt, "-w", file_path],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def _handle_edit(args: dict) -> dict:
    file_path = args.get("file_path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    replace_all = bool(args.get("replace_all", False))

    if not file_path:
        return {"error": "file_path is required"}
    if not os.path.isabs(file_path):
        return {"error": f"file_path must be absolute: {file_path!r}"}
    if not file_path.endswith(".go"):
        return {"error": f"go-edit only operates on .go files: {file_path!r}"}
    if not old_string:
        return {"error": "old_string is required"}
    if old_string == new_string:
        return {"error": "old_string and new_string are identical"}

    path = Path(file_path)
    if not path.exists():
        return {"error": f"file does not exist: {file_path}"}
    if not path.is_file():
        return {"error": f"not a regular file: {file_path}"}

    original = path.read_text()

    try:
        pattern = _build_pattern(old_string)
    except ValueError as exc:
        return {"error": str(exc)}

    matches = list(pattern.finditer(original))

    if len(matches) == 0:
        return {
            "error": (
                "old_string not found (whitespace-normalized). "
                "The text — ignoring whitespace shape — does not appear in the file."
            )
        }

    if len(matches) > 1 and not replace_all:
        # Show the first 3 line numbers to help the caller disambiguate.
        line_numbers = []
        for m in matches[:3]:
            line_numbers.append(original.count("\n", 0, m.start()) + 1)
        more = "" if len(matches) <= 3 else f" (and {len(matches) - 3} more)"
        return {
            "error": (
                f"old_string matched {len(matches)} locations "
                f"(lines {line_numbers}{more}). "
                "Add surrounding context to make it unique, or pass replace_all=true."
            )
        }

    # Perform replacement(s). pattern.sub handles backreferences in new_string,
    # which we DON'T want — callers expect literal replacement. Escape \ and
    # group refs in new_string by using a lambda.
    if replace_all:
        edited = pattern.sub(lambda _m: new_string, original)
        replaced = len(matches)
    else:
        m = matches[0]
        edited = original[: m.start()] + new_string + original[m.end():]
        replaced = 1

    # Atomic write: tempfile in same dir, then rename. On gofmt failure,
    # restore from `original`.
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".goedit",
    )
    try:
        tmp.write(edited)
        tmp.close()
        os.replace(tmp.name, file_path)
    except Exception as exc:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass
        return {"error": f"failed to write file: {exc}"}

    ok, stderr = _gofmt(file_path)
    if not ok:
        # Atomic semantics: revert and report.
        path.write_text(original)
        return {
            "error": (
                "gofmt rejected the post-edit file; reverted. "
                f"gofmt stderr: {stderr or '(empty)'}"
            )
        }

    final = path.read_text()
    return {
        "file_path": file_path,
        "matches_replaced": replaced,
        "bytes_before": len(original),
        "bytes_after": len(final),
        "gofmt_changed": final != edited,
    }


# ---------------------------------------------------------------------------
# Tool catalog
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "edit",
        "description": (
            "Whitespace-tolerant Edit for .go files. Same contract as the built-in "
            "Edit tool except `old_string` matches the file ignoring whitespace shape "
            "(every whitespace run in `old_string` matches `\\s+` in the file). "
            "After a successful replacement, runs `gofmt -w` on the file. "
            "Atomic: if gofmt rejects the post-edit file, the original is restored "
            "and the tool returns an error. Use this when you want to edit Go code "
            "without having to reproduce exact tabs/indentation. Same uniqueness "
            "rule as Edit: 1 match unless `replace_all=true`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the .go file to modify.",
                },
                "old_string": {
                    "type": "string",
                    "description": (
                        "Text to find. Whitespace shape is ignored — any run of "
                        "whitespace in this string matches any non-empty run of "
                        "whitespace in the file."
                    ),
                },
                "new_string": {
                    "type": "string",
                    "description": (
                        "Replacement text, inserted verbatim. gofmt will normalize "
                        "indentation/spacing afterward, so don't worry about exact "
                        "tabs."
                    ),
                },
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, replace every match. If false (default), "
                        "the tool errors when more than one match is found."
                    ),
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
]

HANDLERS = {
    "edit": _handle_edit,
}


# ---------------------------------------------------------------------------
# MCP JSON-RPC 2.0 transport (stdio)
# ---------------------------------------------------------------------------

def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _respond(id_, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": id_, "result": result})


def _error(id_, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


def main() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        id_ = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            _respond(id_, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "go-edit", "version": "1.0.0"},
            })

        elif method == "notifications/initialized":
            pass  # notification — no response

        elif method == "tools/list":
            _respond(id_, {"tools": TOOLS})

        elif method == "tools/call":
            name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            handler = HANDLERS.get(name)
            if handler is None:
                _error(id_, -32601, f"Unknown tool: {name}")
                continue
            try:
                result = handler(tool_args)
                _respond(id_, {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": "error" in result,
                })
            except Exception as exc:
                _respond(id_, {
                    "content": [{"type": "text", "text": f"Internal error: {exc}"}],
                    "isError": True,
                })

        elif id_ is not None:
            _error(id_, -32601, f"Unknown method: {method}")


if __name__ == "__main__":
    main()
