"""Turning inbound mail into tickets.

``jobs`` runs the ingest in the background worker; ``runner`` drains ``core``'s inbound queue; ``parse`` reads the
raw MIME; ``replies`` finds the email the site sent that a message answers; ``classify`` decides automated or human;
``matching`` finds the ticket a message threads to; ``store`` saves it (with ``sanitize`` for HTML and
``attachments`` for files).
"""
