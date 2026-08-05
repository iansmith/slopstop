"""Agent-spawn attribution -- identity, tier, effort, duration (BILL-445).

Stub: the record key exists and is wired; the derivation is #445's.

Note for the implementer: a spawn's duration is NOT its `tool_use` -> `tool_result`
interval. Subagents run in the background, so that pair measures launch latency
(measured: 2.7s against a real adversary that ran 82.1s). The duration comes from the
child transcript at `<session-uuid>/subagents/agent-<agentId>.jsonl`, located by the
agentId in the spawn's tool_result.
"""


def collect(record, ctx):
    record["spawns"] = None
