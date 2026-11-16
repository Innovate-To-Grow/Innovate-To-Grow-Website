"""What staff do to tickets, each step recorded in the ticket's audit trail (``TicketEvent``).

Every change is a targeted update of the fields it concerns, so it never overwrites what the ingest wrote meanwhile
(a new participant, the unread mark). Nothing here sends anything: shadow mode (``shadow``) has no sending code.
Merging moves the messages of every selected ticket to the oldest one and marks the others merged (nothing is
deleted); marking spam closes a ticket as spam; "move to the queue" turns an automated ticket into a normal open one
when the classifier was wrong.

A merge never goes into automated mail or spam (Hongzhe's decision of 2026-11-12: people's messages would be hidden
in it), and spam is never merged at all: ``merge`` raises ``MergeRefused`` before it changes anything. Automated mail
merged into a person's ticket changes nothing on it but its timeline, like automated mail that threads there by
itself (``ingest.pipeline.store``), and stays hidden: still automated, now merged. A merge is final: no status change, spam
mark or move to the queue un-merges a ticket, and only ``merge`` makes one merged.

The steps live in ``changes`` (status, assignee, notes, read state, spam, back to the queue) and ``merging``, and
are re-exported here. Beside them: ``events`` (the audit trail), ``numbering`` (ticket numbers and the subject
token), ``shadow`` (shadow mode) and ``retention`` (the hourly clean-up).
"""

from .changes import (
    NOTE_MAX_CHARS,
    Kind,
    Status,
    add_note,
    assign,
    helpdesk_staff,
    mark_read,
    mark_spam,
    move_to_queue,
    set_status,
    update_ticket,
)
from .merging import MOVE_TO_QUEUE, MergeRefused, merge, merge_refusal

__all__ = [
    "NOTE_MAX_CHARS",
    "MOVE_TO_QUEUE",
    "Kind",
    "Status",
    "MergeRefused",
    "add_note",
    "assign",
    "helpdesk_staff",
    "mark_read",
    "mark_spam",
    "merge",
    "merge_refusal",
    "move_to_queue",
    "set_status",
    "update_ticket",
]
