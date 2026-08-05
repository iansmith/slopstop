"""Agent-active time: human idle, tool execution, model inference (BILL-452).

Stub: the record key exists and is wired; the derivation is #452's.

Note for the implementer: #410 AMENDMENT 1 makes agent-active binding, having measured
one interactive ticket at 550.9 min wall-clock against 45.5 min agent-active -- 92% human
idle. Report the three components separately; agent-active alone still merges a test-suite
run with model reasoning.
"""


def collect(record, ctx):
    record["active"] = None
