def registrations_to_recipients(registrations):
    seen = set()
    recipients = []
    for registration in registrations:
        email = registration.attendee_email or registration.member.get_primary_email()
        if not email or email in seen:
            continue
        seen.add(email)
        first = registration.attendee_first_name or registration.member.first_name or ""
        last = registration.attendee_last_name or registration.member.last_name or ""
        recipients.append(
            {
                "member_id": registration.member_id,
                "email": email,
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}".strip(),
            }
        )
    return recipients


def members_to_recipients(members, *, send_all=False):
    seen = set()
    recipients = []
    for member in members:
        emails = _member_emails(member, send_all=send_all)
        for email in emails:
            if not email or email in seen:
                continue
            seen.add(email)
            recipients.append(
                {
                    "member_id": member.id,
                    "email": email,
                    "first_name": member.first_name or "",
                    "last_name": member.last_name or "",
                    "full_name": member.get_full_name(),
                }
            )
    return recipients


def manual_emails_from_body(body: str):
    recipients = []
    seen = set()
    for line in (body or "").strip().splitlines():
        email = line.strip()
        if not email or email in seen:
            continue
        seen.add(email)
        recipients.append(
            {
                "member_id": None,
                "email": email,
                "first_name": "",
                "last_name": "",
                "full_name": "",
            }
        )
    return recipients


def _member_emails(member, *, send_all: bool):
    if send_all:
        return [
            contact_email.email_address for contact_email in member.contact_emails.all() if contact_email.email_address
        ]
    primary = member.get_primary_email()
    return [primary] if primary else []
