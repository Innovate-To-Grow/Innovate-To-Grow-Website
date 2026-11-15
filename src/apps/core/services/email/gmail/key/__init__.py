"""Changing the Gmail API service-account key (a Google JSON key file; the site never makes or keeps any other secret).

- ``install``: test the key with Google, store it and pin it; ``removal``: unpin it in an emergency.

The key itself, as stored and as pasted, is in ``service_account``; ``install`` tests a key through ``client.auth``.
"""
