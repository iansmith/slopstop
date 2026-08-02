"""Signal fields -- the four non-derivable safety/override markers, posted as
`## slopstop signals` comments on the ticket and its PR rather than tracked in
a local file (#388).
"""

import json
import re

SIGNAL_KEYS = (
    "phase0_tests_red",
    "phase0_tests_pass_unexpected",
    "simplify_line_delta",
    "benchmark_overrides",
)

_HEADER = "## slopstop signals"
_FENCE_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)
_PR_LINKBACK_RE = re.compile(r"PR:\s*#(\d+)")


def _extract_fence(body):
    if _HEADER not in body:
        return None
    after = body.split(_HEADER, 1)[1]
    match = _FENCE_RE.search(after)
    return match.group(1) if match else None


def merge_signals(comments):
    """Merge every `## slopstop signals` block across `comments`, newest wins per key.

    `comments` is an iterable of dicts with `id`, `body`, and `created_at`
    (ISO 8601, lexically sortable). A comment with no `## slopstop signals`
    header, or a header not followed by a ```json fence, is skipped. A fence
    that fails to parse as JSON is also skipped, and its comment id is
    recorded in the result's `unparsed` list -- this never raises, so a
    malformed post never crashes the collector.
    """
    result = {key: None for key in SIGNAL_KEYS}
    unparsed = []
    for comment in sorted(comments, key=lambda c: c.get("created_at") or ""):
        fence = _extract_fence(comment.get("body") or "")
        if fence is None:
            continue
        try:
            data = json.loads(fence)
        except json.JSONDecodeError:
            unparsed.append(comment.get("id"))
            continue
        for key in SIGNAL_KEYS:
            if key in data:
                result[key] = data[key]
    result["unparsed"] = unparsed
    return result


def _linked_pr_number(comments):
    for comment in comments:
        match = _PR_LINKBACK_RE.search(comment.get("body") or "")
        if match:
            return int(match.group(1))
    return None


def collect(record, ctx):
    conv = ctx["conventions"]
    gh_api = ctx["gh_api"]
    ticket_number = record["ticket"].rsplit("-", 1)[-1]

    comments = list(gh_api(f"repos/{conv.repo}/issues/{ticket_number}/comments"))
    pr_number = _linked_pr_number(comments)
    if pr_number is not None:
        comments += gh_api(f"repos/{conv.repo}/issues/{pr_number}/comments")

    record["signals"] = merge_signals(comments)
