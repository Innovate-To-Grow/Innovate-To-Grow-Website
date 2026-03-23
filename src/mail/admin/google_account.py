"""
Admin configuration for GoogleAccount with custom inbox/compose/reply views.
"""

import logging
import re

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from core.admin.base import BaseModelAdmin
from mail.forms import ComposeForm, GoogleAccountForm
from mail.models import EmailLog, GoogleAccount
from mail.services.gmail import GmailService, GmailServiceError

logger = logging.getLogger(__name__)


@admin.register(GoogleAccount)
class GoogleAccountAdmin(BaseModelAdmin):
    """Admin for Gmail API accounts with inbox, compose, reply, and forward views."""

    form = GoogleAccountForm

    list_display = (
        "email",
        "display_name",
        "is_active_badge",
        "last_used_at",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("email", "display_name")
    readonly_fields = ("id", "last_used_at", "last_error", "created_at", "updated_at")
    actions = ["test_connection", "set_as_active"]

    fieldsets = (
        (
            None,
            {
                "fields": ("email", "display_name", "is_active"),
            },
        ),
        (
            "Credentials",
            {
                "fields": ("service_account_json",),
                "classes": ("collapse",),
                "description": "Service account JSON key from Google Cloud Console.",
            },
        ),
        (
            "Operational Info",
            {
                "fields": ("last_used_at", "last_error"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("id", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description="Active", boolean=True, ordering="is_active")
    def is_active_badge(self, obj):
        return obj.is_active

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    @admin.action(description="Test Gmail API connection for selected accounts")
    def test_connection(self, request, queryset):
        for account in queryset:
            try:
                service = GmailService(account)
                profile = service.test_connection()
                self.message_user(
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
            except GmailServiceError as exc:
                error_msg = str(exc)
                self.message_user(
                    request,
                    format_html(
                        "<strong>{}</strong>: Connection FAILED - {}",
                        account.email,
                        error_msg,
                    ),
                    messages.ERROR,
                )
                account.mark_used(error=error_msg)

    @admin.action(description="Set selected account as active")
    def set_as_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one account to set as active.",
                messages.WARNING,
            )
            return
        account = queryset.first()
        account.is_active = True
        account.save()
        self.message_user(
            request,
            f"{account.email} is now the active Gmail API account.",
            messages.SUCCESS,
        )

    # ------------------------------------------------------------------
    # Custom URLs
    # ------------------------------------------------------------------

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("inbox/", self.admin_site.admin_view(self.inbox_view), name="mail_inbox"),
            path(
                "inbox/<str:message_id>/",
                self.admin_site.admin_view(self.message_detail_view),
                name="mail_message_detail",
            ),
            path("compose/", self.admin_site.admin_view(self.compose_view), name="mail_compose"),
            path("reply/<str:message_id>/", self.admin_site.admin_view(self.reply_view), name="mail_reply"),
            path("forward/<str:message_id>/", self.admin_site.admin_view(self.forward_view), name="mail_forward"),
            path("sent/", self.admin_site.admin_view(self.sent_view), name="mail_sent"),
            path("send/", self.admin_site.admin_view(self.send_action), name="mail_send"),
            path("trash/<str:message_id>/", self.admin_site.admin_view(self.trash_action), name="mail_trash"),
            path("labels/<str:message_id>/", self.admin_site.admin_view(self.labels_action), name="mail_labels"),
            path(
                "attachment/<str:message_id>/<str:attachment_id>/",
                self.admin_site.admin_view(self.attachment_view),
                name="mail_attachment",
            ),
        ]
        return custom_urls + urls

    # ------------------------------------------------------------------
    # Helper: get active account + service
    # ------------------------------------------------------------------

    # noinspection PyMethodMayBeStatic
    def _get_gmail_service(self, request):
        """Return (GmailService, GoogleAccount) or redirect with error."""
        account = GoogleAccount.get_active()
        if not account:
            messages.error(request, "No active Gmail API account configured. Add one first.")
            return None, None
        return GmailService(account), account

    # noinspection PyMethodMayBeStatic
    def _log_action(self, account, action, status, request, message_id="", subject="", recipients="", error=""):
        """Create an EmailLog entry."""
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

    # ------------------------------------------------------------------
    # Inbox / Sent views
    # ------------------------------------------------------------------

    # noinspection PyProtectedMember,DuplicatedCode
    def inbox_view(self, request):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        q = request.GET.get("q", "")
        page_token = request.GET.get("page_token", "")

        try:
            result = service.list_messages(
                q=q,
                label_ids=["INBOX"],
                max_results=25,
                page_token=page_token or None,
            )
        except GmailServiceError as exc:
            messages.error(request, f"Failed to load inbox: {exc}")
            account.mark_used(error=str(exc))
            result = {"messages": [], "next_page_token": None}

        context = {
            **self.admin_site.each_context(request),
            "title": "Inbox",
            "opts": self.model._meta,
            "messages_list": result["messages"],
            "next_page_token": result["next_page_token"],
            "search_query": q,
            "current_view": "inbox",
            "account_email": account.email,
        }
        return render(request, "admin/mail/inbox.html", context)

    # noinspection PyProtectedMember,DuplicatedCode
    def sent_view(self, request):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        q = request.GET.get("q", "")
        page_token = request.GET.get("page_token", "")

        try:
            result = service.list_messages(
                q=q,
                label_ids=["SENT"],
                max_results=25,
                page_token=page_token or None,
            )
        except GmailServiceError as exc:
            messages.error(request, f"Failed to load sent mail: {exc}")
            account.mark_used(error=str(exc))
            result = {"messages": [], "next_page_token": None}

        context = {
            **self.admin_site.each_context(request),
            "title": "Sent Mail",
            "opts": self.model._meta,
            "messages_list": result["messages"],
            "next_page_token": result["next_page_token"],
            "search_query": q,
            "current_view": "sent",
            "account_email": account.email,
        }
        return render(request, "admin/mail/inbox.html", context)

    # ------------------------------------------------------------------
    # Message detail
    # ------------------------------------------------------------------

    # noinspection PyProtectedMember
    def message_detail_view(self, request, message_id):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        try:
            msg = service.get_message(message_id)

            # Auto-mark as read
            if msg["is_unread"]:
                service.modify_labels(message_id, remove_labels=["UNREAD"])

            self._log_action(
                account,
                EmailLog.Action.READ,
                EmailLog.Status.SUCCESS,
                request,
                message_id=message_id,
                subject=msg["subject"],
            )
        except GmailServiceError as exc:
            messages.error(request, f"Failed to load message: {exc}")
            account.mark_used(error=str(exc))
            return redirect(reverse("admin:mail_inbox"))

        context = {
            **self.admin_site.each_context(request),
            "title": msg["subject"] or "(no subject)",
            "opts": self.model._meta,
            "msg": msg,
        }
        return render(request, "admin/mail/message_detail.html", context)

    # ------------------------------------------------------------------
    # Compose / Reply / Forward
    # ------------------------------------------------------------------

    # noinspection PyProtectedMember,DuplicatedCode
    def compose_view(self, request):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        form = ComposeForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Compose Email",
            "opts": self.model._meta,
            "form": form,
            "compose_mode": "compose",
            "account_email": account.email,
            "send_url": reverse("admin:mail_send"),
            "cancel_url": reverse("admin:mail_inbox"),
            "parent_label": "Inbox",
            "parent_url": reverse("admin:mail_inbox"),
        }
        return render(request, "admin/mail/compose.html", context)

    # noinspection PyProtectedMember,DuplicatedCode
    def reply_view(self, request, message_id):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        try:
            msg = service.get_message(message_id)
        except GmailServiceError as exc:
            messages.error(request, f"Failed to load message for reply: {exc}")
            return redirect(reverse("admin:mail_inbox"))

        # Pre-fill reply form
        subject = msg["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        quoted_body = f'<br><br><div style="border-left: 2px solid #ccc; padding-left: 10px; margin-left: 5px; color: #666;">On {msg["date"]}, {msg["from"]} wrote:<br>{msg["body_html"] or msg["body_plain"]}</div>'

        form = ComposeForm(
            initial={
                "to": msg["from"],
                "subject": subject,
                "body": quoted_body,
                "thread_id": msg["thread_id"],
                "in_reply_to": msg["message_id"],
                "references": f"{msg.get('references', '')} {msg['message_id']}".strip(),
            }
        )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Reply: {msg['subject']}",
            "opts": self.model._meta,
            "form": form,
            "compose_mode": "reply",
            "original_message_id": message_id,
            "account_email": account.email,
            "send_url": reverse("admin:mail_send"),
            "cancel_url": reverse("admin:mail_inbox"),
            "parent_label": "Inbox",
            "parent_url": reverse("admin:mail_inbox"),
        }
        return render(request, "admin/mail/compose.html", context)

    # noinspection PyProtectedMember,DuplicatedCode
    def forward_view(self, request, message_id):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        try:
            msg = service.get_message(message_id)
        except GmailServiceError as exc:
            messages.error(request, f"Failed to load message for forward: {exc}")
            return redirect(reverse("admin:mail_inbox"))

        subject = msg["subject"]
        if not subject.lower().startswith("fwd:"):
            subject = f"Fwd: {subject}"

        forwarded_body = (
            f"<br><br>---------- Forwarded message ----------<br>"
            f"From: {msg['from']}<br>"
            f"Date: {msg['date']}<br>"
            f"Subject: {msg['subject']}<br>"
            f"To: {msg['to']}<br><br>"
            f"{msg['body_html'] or msg['body_plain']}"
        )

        form = ComposeForm(
            initial={
                "subject": subject,
                "body": forwarded_body,
                "thread_id": msg["thread_id"],
            }
        )

        context = {
            **self.admin_site.each_context(request),
            "title": f"Forward: {msg['subject']}",
            "opts": self.model._meta,
            "form": form,
            "compose_mode": "forward",
            "original_message_id": message_id,
            "account_email": account.email,
            "send_url": reverse("admin:mail_send"),
            "cancel_url": reverse("admin:mail_inbox"),
            "parent_label": "Inbox",
            "parent_url": reverse("admin:mail_inbox"),
        }
        return render(request, "admin/mail/compose.html", context)

    # ------------------------------------------------------------------
    # Send action (POST)
    # ------------------------------------------------------------------

    # noinspection PyProtectedMember,DuplicatedCode
    def send_action(self, request):
        if request.method != "POST":
            return redirect(reverse("admin:mail_compose"))

        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        form = ComposeForm(request.POST, request.FILES)
        if not form.is_valid():
            context = {
                **self.admin_site.each_context(request),
                "title": "Compose Email",
                "opts": self.model._meta,
                "form": form,
                "compose_mode": "compose",
                "account_email": account.email,
                "send_url": reverse("admin:mail_send"),
                "cancel_url": reverse("admin:mail_inbox"),
                "parent_label": "Inbox",
                "parent_url": reverse("admin:mail_inbox"),
            }
            return render(request, "admin/mail/compose.html", context)

        data = form.cleaned_data

        # Collect attachments
        attachments = []
        files = request.FILES.getlist("attachments")
        for f in files:
            attachments.append((f.name, f.read()))

        # Determine action type
        action = EmailLog.Action.SEND
        if data.get("in_reply_to"):
            action = EmailLog.Action.REPLY
        elif data.get("thread_id") and not data.get("in_reply_to"):
            action = EmailLog.Action.FORWARD

        try:
            result = service.send_message(
                to=data["to"],
                subject=data["subject"],
                body_html=data["body"],
                cc=data.get("cc", ""),
                bcc=data.get("bcc", ""),
                attachments=attachments or None,
                thread_id=data.get("thread_id") or None,
                in_reply_to=data.get("in_reply_to") or None,
                references=data.get("references") or None,
            )
            self._log_action(
                account,
                action,
                EmailLog.Status.SUCCESS,
                request,
                message_id=result["id"],
                subject=data["subject"],
                recipients=data["to"],
            )
            account.mark_used()
            messages.success(request, f"Email sent successfully to {data['to']}")
        except GmailServiceError as exc:
            error_msg = str(exc)
            self._log_action(
                account,
                action,
                EmailLog.Status.FAILED,
                request,
                subject=data["subject"],
                recipients=data["to"],
                error=error_msg,
            )
            account.mark_used(error=error_msg)
            messages.error(request, f"Failed to send email: {error_msg}")

        return redirect(reverse("admin:mail_inbox"))

    # ------------------------------------------------------------------
    # Trash action (POST)
    # ------------------------------------------------------------------

    def trash_action(self, request, message_id):
        if request.method != "POST":
            return redirect(reverse("admin:mail_inbox"))

        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        try:
            service.trash_message(message_id)
            self._log_action(
                account,
                EmailLog.Action.DELETE,
                EmailLog.Status.SUCCESS,
                request,
                message_id=message_id,
            )
            messages.success(request, "Message moved to trash.")
        except GmailServiceError as exc:
            error_msg = str(exc)
            self._log_action(
                account,
                EmailLog.Action.DELETE,
                EmailLog.Status.FAILED,
                request,
                message_id=message_id,
                error=error_msg,
            )
            messages.error(request, f"Failed to trash message: {error_msg}")

        return redirect(reverse("admin:mail_inbox"))

    # ------------------------------------------------------------------
    # Labels action (POST)
    # ------------------------------------------------------------------

    def labels_action(self, request, message_id):
        if request.method != "POST":
            return redirect(reverse("admin:mail_inbox"))

        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        add_labels = request.POST.getlist("add_labels")
        remove_labels = request.POST.getlist("remove_labels")

        try:
            service.modify_labels(message_id, add_labels=add_labels or None, remove_labels=remove_labels or None)
            self._log_action(
                account,
                EmailLog.Action.LABEL,
                EmailLog.Status.SUCCESS,
                request,
                message_id=message_id,
            )
            messages.success(request, "Labels updated.")
        except GmailServiceError as exc:
            error_msg = str(exc)
            self._log_action(
                account,
                EmailLog.Action.LABEL,
                EmailLog.Status.FAILED,
                request,
                message_id=message_id,
                error=error_msg,
            )
            messages.error(request, f"Failed to update labels: {error_msg}")

        return redirect(reverse("admin:mail_message_detail", args=[message_id]))

    # ------------------------------------------------------------------
    # Attachment download
    # ------------------------------------------------------------------

    def attachment_view(self, request, message_id, attachment_id):
        service, account = self._get_gmail_service(request)
        if not service:
            return redirect(reverse("admin:mail_googleaccount_changelist"))

        try:
            filename, data = service.get_attachment(message_id, attachment_id)
            import mimetypes

            # Sanitize filename: strip quotes, newlines, and path separators to
            # prevent header injection and path traversal in Content-Disposition.
            safe_filename = re.sub(r'["\r\n/\\]', "_", filename)
            content_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
            response = HttpResponse(data, content_type=content_type)
            response["Content-Disposition"] = f'attachment; filename="{safe_filename}"'
            return response
        except GmailServiceError as exc:
            messages.error(request, f"Failed to download attachment: {exc}")
            return redirect(reverse("admin:mail_message_detail", args=[message_id]))
