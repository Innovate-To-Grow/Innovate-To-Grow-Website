"""Keeping the inbox current without anyone watching it: the background new-mail poll (``poller``), each account's
recorded state and snapshot (``health`` to read it, ``records`` to write it), and dropping cached account and sender
lists when a mail configuration changes (``invalidation``)."""
