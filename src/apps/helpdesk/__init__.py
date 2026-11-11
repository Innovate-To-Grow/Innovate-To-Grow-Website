"""Helpdesk for the site's Microsoft Graph mailbox (i2g@): every message that reaches its Inbox becomes a ticket.

Mail arrives through ``core``'s inbound queue (the bounce processor's scan records every listed message); the
``helpdesk.ingest_inbound`` job reads each message's MIME, classifies it, threads it onto an existing ticket or opens
a new one, and stores its sanitized bodies and attachments in PostgreSQL. Automated mail (out-of-office replies,
bounce reports, receipts, list mail, spam) becomes a closed ticket hidden from the default queue that never
reopens. The helpdesk ships in shadow mode: it only reads the mailbox and writes tickets; it sends nothing.
"""
