import json
import threading

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import TabularInline
from unfold.decorators import action, display
from unfold.widgets import (
    UnfoldAdminRadioSelectWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextareaWidget,
    UnfoldAdminTextInputWidget,
)

from core.admin import BaseModelAdmin
from core.models import EmailServiceConfig, GmailImportConfig
from event.models import Ticket

from ..login_redirects import DEFAULT_LOGIN_REDIRECT_PATH, get_login_redirect_choices
from ..models import EmailCampaign, RecipientLog
from ..models.campaign import ALL_AUDIENCE_CHOICES
from ..services.audience import get_recipients
from ..services.gmail_import import (
    GMAIL_FOLDER_DISPLAY,
    GmailImportError,
    import_message_into_campaign,
    list_recent_sent_messages,
    resolve_gmail_mailbox,
)
from ..services.preview import HTML_MARKER, render_preview


class PersonalizationTextInput(UnfoldAdminTextInputWidget):
    """Unfold text input with clickable personalization tag buttons."""

    template_name = "admin/mail/widgets/personalization_input.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["tags"] = [
            ("{{first_name}}", "First Name"),
            ("{{last_name}}", "Last Name"),
            ("{{full_name}}", "Full Name"),
            ("{{login_link}}", "Login Link"),
        ]
        return context


class ManualEmailsWidget(forms.Textarea):
    """Textarea with email count, validation hints, and paste support."""

    template_name = "admin/mail/widgets/manual_emails.html"

    def __init__(self, attrs=None):
        defaults = {"rows": 6, "placeholder": "one@example.com\ntwo@example.com\nthree@example.com"}
        if attrs:
            defaults.update(attrs)
        super().__init__(attrs=defaults)


class TicketSelectWidget(UnfoldAdminSelectWidget):
    """Select widget that carries ``data-event`` on each option for JS filtering."""

    template_name = "admin/mail/widgets/ticket_select.html"

    def _get_event_map(self):
        """Build ticket-pk → event-id mapping (single query, fresh per render)."""
        try:
            return {str(pk): str(eid) for pk, eid in self.choices.queryset.values_list("pk", "event_id")}
        except AttributeError:
            return {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            if not hasattr(self, "_event_map"):
                self._event_map = self._get_event_map()
            event_id = self._event_map.get(str(value))
            if event_id:
                option["attrs"]["data-event"] = event_id
        return option


BODY_FORMAT_CHOICES = [("plain", "Plain Text"), ("html", "HTML")]


class EmailCampaignForm(forms.ModelForm):
    ticket = forms.ModelChoiceField(
        queryset=Ticket.objects.select_related("event").order_by("event__name", "order", "name"),
        required=False,
        label="Ticket type",
        widget=TicketSelectWidget,
    )
    body_format = forms.ChoiceField(
        choices=BODY_FORMAT_CHOICES,
        initial="plain",
        required=False,
        label="Email format",
        widget=UnfoldAdminRadioSelectWidget,
    )
    login_redirect_path = forms.ChoiceField(
        choices=(),
        initial=DEFAULT_LOGIN_REDIRECT_PATH,
        label="Post-login destination",
        help_text="Choose the internal page recipients should see after using {{login_link}}.",
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = EmailCampaign
        fields = "__all__"
        widgets = {
            "subject": PersonalizationTextInput,
            "manual_emails": ManualEmailsWidget,
            "body": UnfoldAdminTextareaWidget,
            "audience_type": UnfoldAdminSelectWidget,
            "event": UnfoldAdminSelectWidget,
            "member_email_scope": UnfoldAdminSelectWidget,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Override choices to include all audience types (model field keeps the
        # original 4 to avoid a migration; extended list is form-only).
        if "audience_type" in self.fields:
            self.fields["audience_type"].choices = ALL_AUDIENCE_CHOICES
        current_path = self.initial.get("login_redirect_path") or getattr(self.instance, "login_redirect_path", None)
        if "login_redirect_path" in self.fields:
            self.fields["login_redirect_path"].choices = get_login_redirect_choices(current_path=current_path)

        # When a campaign is no longer a draft, keep form-only fields rendered
        # but locked so the admin change page still opens safely.
        if self.instance and self.instance.pk and self.instance.status != "draft":
            for field_name in (
                "subject",
                "login_redirect_path",
                "include_unsubscribe_header",
                "body_format",
                "body",
                "audience_type",
                "event",
                "ticket",
                "selected_members",
                "member_email_scope",
                "manual_emails",
            ):
                if field_name in self.fields:
                    self.fields[field_name].disabled = True

        # Restore ticket selection from manual_emails for ticket_type campaigns
        if self.instance and self.instance.pk and self.instance.audience_type == "ticket_type":
            ticket_id = self.instance.manual_emails.strip()
            if ticket_id:
                try:
                    self.initial["ticket"] = Ticket.objects.get(pk=ticket_id).pk
                except Ticket.DoesNotExist:
                    pass

        # Detect raw-html marker in body and set body_format accordingly
        body_val = self.initial.get("body") or (self.instance.body if self.instance and self.instance.pk else "")
        if body_val.startswith(HTML_MARKER):
            self.initial["body_format"] = "html"
            self.initial["body"] = body_val[len(HTML_MARKER) :]

    def clean(self):
        cleaned = super().clean()
        # For ticket_type: store ticket UUID in manual_emails so the model's
        # clean() sees it, and validate that the ticket belongs to the event.
        if cleaned.get("audience_type") == "ticket_type":
            ticket = cleaned.get("ticket")
            if not ticket:
                self.add_error("ticket", "A ticket type must be selected.")
            else:
                event = cleaned.get("event")
                if event and ticket.event_id != event.pk:
                    self.add_error("ticket", "Selected ticket does not belong to the selected event.")
                cleaned["manual_emails"] = str(ticket.pk)
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Safety net: ensure ticket UUID is in manual_emails
        if instance.audience_type == "ticket_type":
            ticket = self.cleaned_data.get("ticket")
            if ticket:
                instance.manual_emails = str(ticket.pk)

        # Prepend raw-html marker when HTML format is selected
        if self.cleaned_data.get("body_format") == "html" and not instance.body.startswith(HTML_MARKER):
            instance.body = HTML_MARKER + instance.body

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RecipientLogInline(TabularInline):
    model = RecipientLog
    fields = ("email_address", "recipient_name", "status", "error_message", "provider", "sent_at")
    readonly_fields = ("email_address", "recipient_name", "status", "error_message", "provider", "sent_at")
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class AudienceTypeFilter(admin.SimpleListFilter):
    title = "audience type"
    parameter_name = "audience_type"

    def lookups(self, request, model_admin):
        return ALL_AUDIENCE_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(audience_type=self.value())
        return queryset


@admin.register(EmailCampaign)
class EmailCampaignAdmin(BaseModelAdmin):
    form = EmailCampaignForm

    class Media:
        js = ("mail/js/body_format_toggle.js", "mail/js/body_html_editor.js")

    list_display = (
        "subject_preview",
        "audience_badge",
        "status_badge",
        "sent_count",
        "failed_count",
        "sent_at",
    )
    list_filter = ("status", AudienceTypeFilter)
    search_fields = ("subject",)
    ordering = ("-created_at",)
    actions_detail = [
        "preview_email_action",
        "preview_recipients_action",
        "import_gmail_html_action",
        "send_campaign_action",
    ]

    fieldsets = (
        (
            "Audience",
            {
                "fields": (
                    "audience_type",
                    "event",
                    "ticket",
                    "selected_members",
                    "member_email_scope",
                    "manual_emails",
                ),
            },
        ),
        (
            "Campaign",
            {"fields": ("subject", "login_redirect_path", "include_unsubscribe_header", "body_format", "body")},
        ),
    )
    filter_horizontal = ("selected_members",)
    conditional_fields = {
        "event": (
            "audience_type === 'event_registrants' || audience_type === 'ticket_type'"
            " || audience_type === 'checked_in' || audience_type === 'not_checked_in'"
        ),
        "ticket": "audience_type === 'ticket_type'",
        "selected_members": "audience_type === 'selected_members'",
        "member_email_scope": "audience_type === 'selected_members'",
        "manual_emails": "audience_type === 'manual'",
    }

    @display(description="Subject")
    def subject_preview(self, obj):
        return obj.subject[:60] + "..." if len(obj.subject) > 60 else obj.subject

    @display(description="Audience", label=True)
    def audience_badge(self, obj):
        badge_colors = {
            "subscribers": ("Subscribers", "info"),
            "event_registrants": ("Event", "warning"),
            "ticket_type": ("Ticket Type", "warning"),
            "checked_in": ("Checked In", "success"),
            "not_checked_in": ("No-Shows", "danger"),
            "all_members": ("All Members", "info"),
            "staff": ("Staff", "info"),
            "selected_members": ("Selected", "info"),
            "manual": ("Manual", "info"),
        }
        return badge_colors.get(obj.audience_type, (obj.get_audience_type_display(), "info"))

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"draft": "info", "sending": "warning", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and obj.error_message:
            fieldsets.append(
                ("Error Details", {"fields": ("error_message",), "classes": ("collapse",)}),
            )
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.error_message:
            readonly.append("error_message")
        if obj and obj.status != "draft":
            readonly.extend(
                [
                    "name",
                    "subject",
                    "login_redirect_path",
                    "include_unsubscribe_header",
                    "body",
                    "audience_type",
                    "event",
                ]
            )
        return readonly

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            extra_context["email_config"] = EmailServiceConfig.load()
            extra_context["gmail_import_config"] = GmailImportConfig.load()
            extra_context["gmail_mailbox"] = resolve_gmail_mailbox()
            extra_context["gmail_folder"] = GMAIL_FOLDER_DISPLAY
        except Exception:
            extra_context.setdefault("email_config", None)
            extra_context.setdefault("gmail_import_config", None)
            extra_context.setdefault("gmail_mailbox", "")
            extra_context.setdefault("gmail_folder", GMAIL_FOLDER_DISPLAY)
        return super().changelist_view(request, extra_context=extra_context)

    # -- Custom URLs -----------------------------------------------------------

    def get_urls(self):
        custom_urls = [
            path(
                "inline-preview/",
                self.admin_site.admin_view(self.inline_preview_view),
                name="mail_emailcampaign_inline_preview",
            ),
            path(
                "<path:object_id>/import-gmail-html/",
                self.admin_site.admin_view(self.import_gmail_html_view),
                name="mail_emailcampaign_import_gmail_html",
            ),
            path(
                "<path:object_id>/import-gmail-html/confirm/",
                self.admin_site.admin_view(self.import_gmail_html_confirm_view),
                name="mail_emailcampaign_import_gmail_html_confirm",
            ),
            path(
                "<path:object_id>/preview-recipients/",
                self.admin_site.admin_view(self.preview_recipients_view),
                name="mail_emailcampaign_preview_recipients",
            ),
            path(
                "<path:object_id>/send-campaign/",
                self.admin_site.admin_view(self.send_campaign_preview_view),
                name="mail_emailcampaign_send_preview",
            ),
            path(
                "<path:object_id>/send-campaign/confirm/",
                self.admin_site.admin_view(self.send_campaign_confirm_view),
                name="mail_emailcampaign_send_confirm",
            ),
            path(
                "<path:object_id>/send-campaign/status/",
                self.admin_site.admin_view(self.send_campaign_status_view),
                name="mail_emailcampaign_send_status",
            ),
            path(
                "<path:object_id>/send-campaign/status.json",
                self.admin_site.admin_view(self.send_campaign_status_json),
                name="mail_emailcampaign_send_status_json",
            ),
        ]
        return custom_urls + super().get_urls()

    # -- Detail actions --------------------------------------------------------

    @action(description="Preview Email", url_path="preview-email", icon="visibility")
    def preview_email_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_preview", args=[object_id]))

    @action(description="Preview Recipients", url_path="preview-recipients", icon="group")
    def preview_recipients_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_preview_recipients", args=[object_id]))

    @action(description="Import Gmail HTML", url_path="import-gmail-html", icon="download")
    def import_gmail_html_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_import_gmail_html", args=[object_id]))

    @action(description="Send Campaign", url_path="send-campaign", icon="send")
    def send_campaign_action(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        if obj.status != "draft":
            messages.warning(request, "This campaign has already been sent.")
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_change", args=[object_id]))
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_preview", args=[object_id]))

    # -- Custom views ----------------------------------------------------------

    def preview_recipients_view(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        recipients = get_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview Recipients — {obj.name}",
            "campaign": obj,
            "recipients": recipients,
            "back_url": reverse("admin:mail_emailcampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/preview_recipients.html", context)

    def import_gmail_html_view(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])
        if obj.status != "draft":
            messages.warning(request, "Only draft campaigns can import Gmail HTML.")
            return HttpResponseRedirect(change_url)

        force_refresh = request.GET.get("refresh") == "1"

        try:
            mailbox = resolve_gmail_mailbox()
            gmail_messages = list_recent_sent_messages(limit=5, mailbox=mailbox, force_refresh=force_refresh)
            gmail_import_config = GmailImportConfig.load()
        except GmailImportError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Import Gmail HTML — {obj.name}",
            "campaign": obj,
            "gmail_messages": gmail_messages,
            "gmail_import_config": gmail_import_config,
            "mailbox": mailbox,
            "gmail_folder": GMAIL_FOLDER_DISPLAY,
            "confirm_url": reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[object_id]),
            "refresh_url": request.path + "?refresh=1",
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/mail/import_gmail_html.html", context)

    def import_gmail_html_confirm_view(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])
        selection_url = reverse("admin:mail_emailcampaign_import_gmail_html", args=[object_id])

        if obj.status != "draft":
            messages.warning(request, "Only draft campaigns can import Gmail HTML.")
            return HttpResponseRedirect(change_url)
        if request.method != "POST":
            return HttpResponseRedirect(selection_url)

        message_id = request.POST.get("message_id", "").strip()
        if not message_id:
            messages.error(request, "Please choose a Gmail message to import.")
            return HttpResponseRedirect(selection_url)

        try:
            mailbox = resolve_gmail_mailbox()
            import_message_into_campaign(obj, message_id, mailbox=mailbox)
        except GmailImportError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(selection_url)

        messages.success(
            request,
            "Imported Gmail HTML into the campaign body. Use Preview Email to verify the result before sending.",
        )
        return HttpResponseRedirect(change_url)

    def send_campaign_preview_view(self, request, object_id):
        """Show email preview with rendered layout. Also serves as Step 1 of send flow for drafts."""
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])

        recipients = get_recipients(obj)
        preview = render_preview(obj)
        is_draft = obj.status == "draft"

        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview Email — {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_html_json": json.dumps(preview["html"]),
            "confirm_url": reverse("admin:mail_emailcampaign_send_confirm", args=[object_id]) if is_draft else None,
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/mail/send_preview.html", context)

    def send_campaign_confirm_view(self, request, object_id):
        """Step 2: Final confirmation before sending."""
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])

        if obj.status != "draft":
            messages.warning(request, "This campaign has already been sent.")
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            sent_by = request.user
            thread = threading.Thread(target=self._background_send, args=(obj.pk, sent_by.pk), daemon=True)
            thread.start()
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_status", args=[object_id]))

        recipients = get_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm Send — {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_url": reverse("admin:mail_emailcampaign_send_preview", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/confirm_send.html", context)

    def send_campaign_status_view(self, request, object_id):
        """Step 3: Live send progress page."""
        obj = EmailCampaign.objects.get(pk=object_id)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Sending — {obj.name}",
            "campaign": obj,
            "status_json_url": reverse("admin:mail_emailcampaign_send_status_json", args=[object_id]),
            "back_url": reverse("admin:mail_emailcampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/send_status.html", context)

    def send_campaign_status_json(self, request, object_id):
        """JSON endpoint for polling send progress. Short cache reduces per-poll DB load."""
        from django.core.cache import cache

        status_cache_key = f"mail:campaign_status:{object_id}"
        cached = cache.get(status_cache_key)
        if cached is not None:
            return JsonResponse(cached)

        obj = EmailCampaign.objects.get(pk=object_id)

        recent_qs = RecipientLog.objects.filter(campaign=obj).exclude(status="pending").order_by("-updated_at")[:20]
        recent_logs = [
            {
                "email": log.email_address,
                "name": log.recipient_name,
                "status": log.status,
                "error": log.error_message,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            }
            for log in recent_qs
        ]

        failed_qs = RecipientLog.objects.filter(campaign=obj, status="failed").order_by("-updated_at")
        failed_logs = [
            {"email": log.email_address, "name": log.recipient_name, "error": log.error_message} for log in failed_qs
        ]

        first_sent_at = (
            RecipientLog.objects.filter(campaign=obj, sent_at__isnull=False)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
            .first()
        )

        payload = {
            "status": obj.status,
            "total": obj.total_recipients,
            "sent": obj.sent_count,
            "failed": obj.failed_count,
            "error_message": obj.error_message,
            "started_at": first_sent_at.isoformat() if first_sent_at else None,
            "recent_logs": recent_logs,
            "failed_logs": failed_logs,
        }
        # Cache for 2s: tight enough to keep the UI feeling live, wide enough to
        # absorb burst polling during a send.
        cache.set(status_cache_key, payload, 2)
        return JsonResponse(payload)

    def inline_preview_view(self, request):
        """Render email preview from POST data (subject + body). Opens in a new tab."""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_changelist"))
        from django.http import HttpResponse

        from ..services.personalize import personalize
        from ..services.preview import SAMPLE_CONTEXT, render_email_html

        body = request.POST.get("body", "")
        body_format = request.POST.get("body_format", "plain")
        include_unsubscribe = request.POST.get("include_unsubscribe_header") == "on"
        if body_format == "html":
            body = HTML_MARKER + body
        body_html = personalize(body, SAMPLE_CONTEXT)
        unsubscribe_url = "#unsubscribe-preview" if include_unsubscribe else ""
        html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
        return HttpResponse(html)

    @staticmethod
    def _background_send(campaign_pk, user_pk):
        """Run send_campaign in a background thread."""
        import django

        django.db.connections.close_all()

        from django.contrib.auth import get_user_model

        from mail.models import EmailCampaign as EC
        from mail.services.send_campaign import send_campaign

        User = get_user_model()
        campaign = EC.objects.get(pk=campaign_pk)
        user = User.objects.get(pk=user_pk)
        try:
            send_campaign(campaign, sent_by=user)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("Background send failed for campaign %s", campaign_pk)
            campaign.refresh_from_db()
            if campaign.status in ("draft", "sending"):
                campaign.status = "failed"
            campaign.error_message = str(exc)
            campaign.save(update_fields=["status", "error_message"])
