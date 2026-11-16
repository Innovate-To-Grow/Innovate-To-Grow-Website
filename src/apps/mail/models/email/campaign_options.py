"""What an email campaign may target: its audiences, member email choices and statuses."""

SUBSCRIBERS_LABEL = "All subscribers (subscribed email addresses only)"
ALL_MEMBERS_LABEL = "All active members (subscribed or not)"

ALL_AUDIENCE_CHOICES = [
    ("subscribers", SUBSCRIBERS_LABEL),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", ALL_MEMBERS_LABEL),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
    ("manual", "Manual Emails"),
]

_ALL_AUDIENCE_LABELS = dict(ALL_AUDIENCE_CHOICES)

# Subset of audience types that can be used as an exclusion group (no "Manual Emails").
EXCLUDE_AUDIENCE_CHOICES = [
    ("", "No exclusion"),
    ("subscribers", SUBSCRIBERS_LABEL),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", ALL_MEMBERS_LABEL),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
]

AUDIENCE_HELP_TEXT = (
    "Who gets the email. All subscribers: active members who have an email address with its subscription on, at "
    "those subscribed addresses only (with Send to: primary email only, the primary address, and only while it is "
    "subscribed). All active members: every active member, including people who unsubscribed, at the primary "
    "address or, with Send to: all emails, at every saved address. Staff Members: the active members marked as "
    "staff, addressed the same way. Inactive members are never included. Event audiences use each registration's "
    "attendee email, or the member's primary email when there is none."
)

MEMBER_EMAIL_CHOICES = [
    ("primary", "Primary email only"),
    ("all", "All emails (primary + secondary + other)"),
]

STATUS_CHOICES = [
    ("draft", "Draft"),
    ("queued", "Queued"),
    ("sending", "Sending"),
    ("partial", "Partially sent"),
    ("sent", "Sent"),
    ("failed", "Failed"),
]
