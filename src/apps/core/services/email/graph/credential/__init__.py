"""The Microsoft Graph certificate credential (certificate authentication only; there is no client secret).

- ``parsing``: read the certificate and private key an admin enters (PEM, DER, .p12/.pfx, encrypted PEM).
- ``stored_key``: the private key in the credential store, read only by its pinned version.
- ``entra_check``: one token request that tests a certificate against Microsoft Entra.
- ``lifecycle``: install a certificate; ``recovery``: roll back to the previous one, or remove both in an emergency.

The submodules are imported directly: ``auth`` depends on ``stored_key``, and ``entra_check`` on ``auth``.
"""
