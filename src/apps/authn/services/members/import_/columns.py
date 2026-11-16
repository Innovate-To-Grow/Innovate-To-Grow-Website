"""The import spreadsheet's columns: header names and the fields they fill, the ignored, informational and flag columns,
and the texts flags and dates are read from."""

from __future__ import annotations

HEADER_MAP = {
    "member uuid": "member_uuid",
    "member_uuid": "member_uuid",
    "uuid": "member_uuid",
    "first name": "first_name",
    "first_name": "first_name",
    "firstname": "first_name",
    "last name": "last_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "middle name": "middle_name",
    "middle_name": "middle_name",
    "title": "title",
    "title - role": "title",
    "title - role (optional)": "title",
    "when started": "when_started",
    "when_started": "when_started",
    "date joined": "when_started",
    "date_joined": "when_started",
    "last updated": "last_updated",
    "last_updated": "last_updated",
    "active": "is_active",
    "staff": "is_staff",
    "primary expired": "primary_expired",
    "primary_expired": "primary_expired",
    "primary email": "primary_email",
    "primary_email": "primary_email",
    "email": "primary_email",
    "primary verified": "primary_verified",
    "primary_verified": "primary_verified",
    "primary subscribed": "primary_subscribed",
    "primary_subscribed": "primary_subscribed",
    "secondary email": "secondary_email",
    "secondary_email": "secondary_email",
    "secondary verified": "secondary_verified",
    "secondary_verified": "secondary_verified",
    "secondary subscribed": "secondary_subscribed",
    "secondary_subscribed": "secondary_subscribed",
    "secondary expired": "secondary_expired",
    "secondary_expired": "secondary_expired",
    "secondary bounced": "secondary_bounced",
    "secondary_bounced": "secondary_bounced",
    "phone number": "phone_number",
    "phone_number": "phone_number",
    "phone": "phone_number",
    "phone number subscribed": "phone_subscribed",
    "phone_number_subscribed": "phone_subscribed",
    "phone subscribed": "phone_subscribed",
    "phone_subscribed": "phone_subscribed",
    "phone number verified": "phone_verified",
    "phone_number_verified": "phone_verified",
    "phone verified": "phone_verified",
    "phone_verified": "phone_verified",
    "organization": "organization",
    "organization (optional)": "organization",
    "company": "organization",
    "org": "organization",
}
PHONE_VERIFIED_IGNORED = (
    "Phone Verified column ignored: an import never verifies or un-verifies a phone number. New numbers are saved "
    "unverified and stored numbers keep their status; members verify their own numbers with a one-time code sent by "
    "SMS."
)
# Columns a sheet may have (Export to Excel writes them) that the import recognises but never reads, by key, with
# the note shown once per file. A verified phone number is a sign-in factor, so only the member's own one-time code
# may produce one: a sheet cell is no proof that the number is theirs.
IGNORED_COLUMNS = {"phone_verified": PHONE_VERIFIED_IGNORED}
# Columns that old sheets and the template carry for information only, and the ignored ones: recognised, listed,
# never imported.
INFORMATIONAL_KEYS = frozenset(
    {"last_updated", "primary_expired", "secondary_expired", "secondary_bounced", *IGNORED_COLUMNS}
)
# Every column the import reads.
IMPORTED_KEYS = frozenset(HEADER_MAP.values()) - INFORMATIONAL_KEYS
# The TRUE/FALSE columns, by the key ``normalize_header`` maps them to, with the header an admin sees.
FLAG_COLUMNS = {
    "is_active": "Active",
    "is_staff": "Staff",
    "primary_verified": "Primary Verified",
    "primary_subscribed": "Primary Subscribed",
    "secondary_verified": "Secondary Verified",
    "secondary_subscribed": "Secondary Subscribed",
    "phone_subscribed": "Phone Subscribed",
}
TRUE_TEXT = frozenset({"true", "yes", "y", "1", "active"})
FALSE_TEXT = frozenset({"false", "no", "n", "0", "inactive"})
DATE_FORMATS = [
    "%Y-%m-%d %I:%M %p",
    "%Y-%m-%d %I:%M:%S %p",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%y",
]
# The member export prefixes these with an apostrophe so a spreadsheet never runs them as a formula
# (``apps.core.services.helpers.sheets_safety``); the import takes the apostrophe off again.
_EXPORT_ESCAPED = ("=", "+", "-", "@")
_TEXT_KEYS = ("first_name", "last_name", "middle_name", "title", "organization")
