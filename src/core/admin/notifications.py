import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def notify_staff_of_action(*, actor, action, summary, admin_url=None, exclude_actor=True):
    """Send notification email to all active staff members about an admin action.

    Args:
        actor: The user who performed the action.
        action: Short description (e.g. "Sent Campaign: Spring Newsletter").
        summary: List of dicts with 'label' and 'value' keys for the detail table.
        admin_url: Optional link to the relevant admin page.
        exclude_actor: If True, don't notify the person who performed the action.
    """
    from authn.models import Member
    from authn.services.email.send_email.senders import send_notification_email

    recipients = Member.objects.filter(is_staff=True, is_active=True)
    if exclude_actor:
        recipients = recipients.exclude(pk=actor.pk)

    recipient_emails = [m.get_primary_email() for m in recipients if m.get_primary_email()]
    if not recipient_emails:
        logger.info("No staff recipients for admin action notification")
        return

    subject = f"[I2G Admin] {action}"
    actor_name = actor.get_full_name() or str(actor)
    context = {
        "action": action,
        "actor_name": actor_name,
        "summary": summary,
        "admin_url": admin_url,
        "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    for email in recipient_emails:
        try:
            send_notification_email(
                recipient=email,
                subject=subject,
                template="core/email/admin_action_notification.html",
                context=context,
            )
        except Exception:
            logger.exception("Failed to send admin action notification to %s", email)
