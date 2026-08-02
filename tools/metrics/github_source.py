"""GitHub-derived timing: coarse span and PR sub-phases (BILL-385).

Populates `record["timing"]` from the issue object, its events, and its
timeline's cross-referenced PRs. No other module reads GitHub timing data.
"""

import datetime


def _parse_iso(value):
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seconds_between(start, end):
    if start is None or end is None:
        return None
    return int((_parse_iso(end) - _parse_iso(start)).total_seconds())


def _issue_number(record):
    return record["ticket"].split("-", 1)[1]


def _resolve_started_at(issue, events, in_progress_label):
    for event in events:
        if event["event"] == "labeled" and event["label"]["name"] == in_progress_label:
            return event["created_at"], "label"
    return issue["created_at"], "issue_created"


def _resolve_pr(repo, ticket, timeline, gh_api):
    candidates = dict.fromkeys(
        entry["source"]["issue"]["number"]
        for entry in timeline
        if entry.get("event") == "cross-referenced"
        and entry["source"]["issue"].get("pull_request") is not None
    )

    matches = []
    for number in candidates:
        pr = gh_api(f"repos/{repo}/pulls/{number}")
        head_ticket = pr["head"]["ref"].rsplit("/", 1)[-1]
        if head_ticket == ticket:
            matches.append(pr)

    if not matches:
        return None, "unresolved", []

    matches.sort(key=lambda pr: (pr["merged_at"] is None, pr["merged_at"] or ""))
    primary, *rest = matches
    ambiguous = [pr["number"] for pr in rest]
    return primary, "head_branch", ambiguous


def collect(record, ctx):
    conv = ctx["conventions"]
    gh_api = ctx["gh_api"]
    repo = record["repo"]
    ticket = record["ticket"]
    number = _issue_number(record)

    issue = gh_api(f"repos/{repo}/issues/{number}")
    events = gh_api(f"repos/{repo}/issues/{number}/events")
    timeline = gh_api(f"repos/{repo}/issues/{number}/timeline")

    started_at, started_at_source = _resolve_started_at(
        issue, events, conv.status_labels["in_progress"]
    )
    completed_at = issue["closed_at"]
    span_seconds = _seconds_between(started_at, completed_at)

    pr, pr_source, pr_ambiguous = _resolve_pr(repo, ticket, timeline, gh_api)

    timing_pr = None
    start_to_pr_seconds = None
    pr_to_merge_seconds = None
    if pr is not None:
        timing_pr = {
            "number": pr["number"],
            "opened_at": pr["created_at"],
            "merged_at": pr["merged_at"],
        }
        start_to_pr_seconds = _seconds_between(started_at, pr["created_at"])
        pr_to_merge_seconds = _seconds_between(pr["created_at"], pr["merged_at"])

    record["timing"] = {
        "started_at": started_at,
        "started_at_source": started_at_source,
        "completed_at": completed_at,
        "span_seconds": span_seconds,
        "pr": timing_pr,
        "pr_source": pr_source,
        "pr_ambiguous": pr_ambiguous,
        "sub_phases": {
            "start_to_pr_seconds": start_to_pr_seconds,
            "pr_to_merge_seconds": pr_to_merge_seconds,
        },
    }
