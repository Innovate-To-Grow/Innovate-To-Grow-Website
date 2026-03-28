from django.contrib import messages
from django.utils.html import format_html

from mail.models import EmailLog, GoogleAccount


def get_gmail_service(request, gmail_service_cls):
    account = GoogleAccount.get_active()
    if not account:
        messages.error(request, "No active Gmail API account configured. Add one first.")
        return None, None
    return gmail_service_cls(account), account


def log_action(account, action, status, request, message_id="", subject="", recipients="", error=""):
    EmailLog.objects.create(
        account=account,
        action=action,
        status=status,
        gmail_message_id=message_id,
        subject=subject[:500] if subject else "",
        recipients=recipients,
        error_message=error,
        performed_by=request.user if request.user.is_authenticated else None,
    )


def test_connection(admin_obj, request, queryset, gmail_service_cls, error_cls):
    for account in queryset:
        try:
            profile = gmail_service_cls(account).test_connection()
            admin_obj.message_user(
                request,
                format_html(
                    "<strong>{}</strong>: Connection successful! ({} messages, {} threads)",
                    account.email,
                    profile["messages_total"],
                    profile["threads_total"],
                ),
                messages.SUCCESS,
            )
            account.mark_used()
        except error_cls as exc:
            admin_obj.message_user(
                request,
                format_html("<strong>{}</strong>: Connection FAILED - {}", account.email, exc),
                messages.ERROR,
            )
            account.mark_used(error=str(exc))


def set_as_active(admin_obj, request, queryset):
    if queryset.count() != 1:
        admin_obj.message_user(request, "Please select exactly one account to set as active.", messages.WARNING)
        return
    account = queryset.first()
    account.is_active = True
    account.save()
    admin_obj.message_user(request, f"{account.email} is now the active Gmail API account.", messages.SUCCESS)
