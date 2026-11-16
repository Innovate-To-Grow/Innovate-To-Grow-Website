"""Scanning the sending mailbox for bounce reports: the worker job that runs each scan (``jobs``), the incremental
scan itself (``scanner``), which mailbox and messages it reads (``source``), and its durable per-mailbox state
(``state``: checkpoint, lease, health, staff controls).
"""
