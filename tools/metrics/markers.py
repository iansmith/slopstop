"""Fleet marker-derived phase timing -- derives `phases` from the ticket's own comments.

Reads what `:run` already posts; imposes no new marker wording on skills/run/ (out of
scope per the ticket) and does not compute or clamp `timing` (owned by #385).
"""

FLEET_BRIEFING_MARKER = "🤖 **Fleet agent briefed**"


def collect(record, ctx):
    issue_number = record["ticket"].rsplit("-", 1)[1]
    comments = ctx["gh_api"](f"repos/{record['repo']}/issues/{issue_number}/comments")
    comments = sorted(comments, key=lambda c: c["created_at"])

    markers = [
        {"at": c["created_at"], "body_first_line": c["body"].split("\n", 1)[0]}
        for c in comments
    ]
    briefing = next(
        (c for c in comments if c["body"].startswith(FLEET_BRIEFING_MARKER)), None
    )

    record["phases"] = {
        "markers": markers,
        "fleet": briefing is not None,
        "briefed_at": briefing["created_at"] if briefing else None,
    }
