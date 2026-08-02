"""Stub for BILL-382 Phase 0 -- conventions decoder not yet implemented."""


class Conventions:
    def __init__(self):
        self.system = None
        self.repo = None
        self.prefix = None
        self.status_labels = {}


def load(conf_path):
    return Conventions()
