"""The slopstop version in effect when a ticket ran (BILL-453).

Stub: the record key exists and is wired; the derivation is #453's.

Note for the implementer: derived from slopstop's git tag history (a durable source,
charter R2), never emitted by a skill (R1). `ctx["slopstop_root"]` is how to find that
history when the collected project is a different repository.
"""


def collect(record, ctx):
    record["version"] = None
