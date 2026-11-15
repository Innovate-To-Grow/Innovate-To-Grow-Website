"""Keeping the channels' state in step with the site outside the request path: which channel and identity each
delivery family uses now (``families``: the worker's claim-time gates and inline batch sizes), the worker's
periodic limit reads and purges (``maintenance``), and configuration saves half-opening breakers (``receivers``).
"""
