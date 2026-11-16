"""What the database holds for the addresses, numbers and Member UUIDs a sheet names.

The lookups run a fixed number of queries per chunk of the sheet, whatever its size. Addresses are matched ignoring
case through ``UPPER()``, the comparison Django's ``iexact`` makes on PostgreSQL, and are keyed in memory by
``upper().lower()`` as ``login_guard.normalize_identifier`` does, so the database and this code agree on which
addresses are the same. The unique constraint on ``ContactEmail.email_address`` is case-sensitive, so one key can hold
several records: legacy duplicates that differ only in letter case.

A row's analysis reads only its own part of the snapshot (``row_slice``). That part is stored on the row, so the review
page can show it, and its SHA-256 (``fingerprint``) is what the apply compares to find records that changed after the
review. The fingerprint hashes values, not ``updated_at``: queryset ``.update()`` calls such as the Contact Emails
"Mark verified" action don't touch ``auto_now``.
"""

from .load import CHUNK, load_snapshot, row_slice, snapshot_from_slice
from .records import EmailRecord, MemberRecord, PhoneRecord, Snapshot, address_key, fingerprint, us_phone
