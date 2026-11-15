"""What an SMS campaign may target and contain: audiences, phone policies, recipient statuses, link placeholders,
and the parser for manually entered numbers."""

import re

SMS_AUDIENCE_CHOICES = [
    ("subscribers", "SMS Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", "All Active Members"),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
    ("manual", "Manual Phones"),
]

SMS_EXCLUDE_AUDIENCE_CHOICES = [
    ("", "No exclusion"),
    ("subscribers", "SMS Subscribers"),
    ("event_registrants", "Event Registrants"),
    ("ticket_type", "Event Ticket Type"),
    ("checked_in", "Checked-In Attendees"),
    ("not_checked_in", "No-Shows (Not Checked In)"),
    ("all_members", "All Active Members"),
    ("staff", "Staff Members"),
    ("selected_members", "Selected Members"),
]

SMS_PHONE_POLICY_CHOICES = [
    ("verified_opt_in", "Verified opt-ins"),
    ("any_verified", "Any verified phone"),
]

SMS_LOG_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("retry", "Retry scheduled"),
    # Held back by a delivery limit (a provider pause or a daily budget); "Resume paused recipients" sends them.
    ("paused", "Paused by delivery limits"),
    ("sent", "Sent"),
    ("failed", "Failed"),
    ("uncertain", "Uncertain delivery"),
    # Not sent: the number is on the SMS opt-out list (it replied STOP), or AWS refused it as opted out.
    ("opted_out", "Opted out"),
]

# The short-link placeholders (``services.sms.compose``): usable only while links in SMS are allowed.
SMS_LINK_PLACEHOLDERS = ("login_link", "ticket_link", "event_link")

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")

LINKS_OFF_MESSAGE = (
    "Links in SMS are turned off (Mail → SMS Settings). They stay off until the sending number's 10DLC or toll-free "
    "registration is confirmed to allow embedded links."
)


def parse_manual_sms_phones(body: str) -> list[str]:
    phones = []
    seen = set()
    for line in (body or "").strip().splitlines():
        phone = line.strip()
        if not phone or phone in seen:
            continue
        seen.add(phone)
        phones.append(phone)
    return phones
