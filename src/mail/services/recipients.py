"""
Recipient resolution and email body personalization for SES compose.
"""

from authn.models import ContactEmail, Member
from event.models import EventRegistration


def resolve_recipients(source, event=None):
    """
    Return a list of recipient dicts based on the source type.

    Each dict has: {"email", "first_name", "full_name", "member_id"}
    """
    if source == "subscribers":
        members = Member.objects.filter(email_subscribe=True, is_active=True)
        member_emails = set()
        recipients = []
        for m in members:
            member_emails.add(m.email.lower())
            recipients.append(
                {
                    "email": m.email,
                    "first_name": m.first_name,
                    "full_name": m.get_full_name() or m.username,
                    "member_id": str(m.pk),
                }
            )

        # Include anonymous subscribed contact emails (no linked member)
        anonymous_contacts = ContactEmail.objects.filter(
            subscribe=True,
            member__isnull=True,
        )
        for contact in anonymous_contacts:
            if contact.email_address.lower() not in member_emails:
                recipients.append(
                    {
                        "email": contact.email_address,
                        "first_name": "",
                        "full_name": "",
                        "member_id": None,
                    }
                )

        return recipients

    if source == "event":
        if not event:
            return []
        registrations = EventRegistration.objects.filter(event=event).select_related("member")
        return [
            {
                "email": reg.member.email or reg.attendee_email,
                "first_name": reg.member.first_name or reg.attendee_first_name,
                "full_name": reg.member.get_full_name() or reg.attendee_name,
                "member_id": str(reg.member.pk),
            }
            for reg in registrations
        ]

    return []


def personalize_body(body_html, recipient):
    """Replace {name} with the recipient's first name (or full name as fallback)."""
    name = recipient.get("first_name") or recipient.get("full_name") or ""
    return body_html.replace("{name}", name)
