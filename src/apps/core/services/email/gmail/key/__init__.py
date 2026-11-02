"""The Gmail API service-account key (a Google JSON key file; the site never makes or keeps any other secret).

- ``stored_key``: the key in the credential store, read only by its pinned version and checked against the facts
  the config records.
- ``parsing``: read and check the key file an admin pastes or uploads, in memory.
- ``install``: test the key with Google, store it and pin it; ``removal``: unpin it in an emergency.

The submodules are imported directly: ``auth`` depends on ``stored_key``, and ``install`` on ``auth``.
"""
