"""Turning inbound mail into tickets.

``pipeline``: ``jobs`` runs the ingest in the background worker, ``runner`` drains ``core``'s inbound queue, and
``store`` saves each message (``messages`` adds it to its ticket). ``reading``: ``parse`` reads the raw MIME (``mime``
walks its parts into a ``message``), ``sanitize`` cleans HTML and ``attachments`` decides which files are kept.
``routing``: ``replies`` finds the email the site sent that a message answers, ``classify`` decides automated or
human, and ``matching`` finds the ticket a message threads to.
"""
