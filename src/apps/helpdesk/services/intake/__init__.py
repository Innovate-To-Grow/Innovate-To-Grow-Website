"""The helpdesk's intake: its own scan of the mailbox's Inbox, which fills ``core``'s inbound queue.

``scanner`` lists the Inbox from the helpdesk's own checkpoint and records every message (metadata only); ``jobs``
runs the scans in the background worker and wakes the ingest when new mail was recorded; ``state`` holds the
checkpoint, lease and health per mailbox and the staff controls (pause, "Rescan since", first-scan lookback);
``status`` is what the intake card and the Email Monitoring card show. Bounce processing reads the same Inbox on its
own schedule and checkpoint: neither one's pause or rescan moves the other.
"""
