import json
import threading

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from unfold.admin import TabularInline
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminTextInputWidget

from core.admin import BaseModelAdmin
from core.models import EmailServiceConfig

from ..models import EmailCampaign, RecipientLog
from ..services.audience import get_recipients
from ..services.preview import render_preview


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


class EmailCampaignForm(forms.ModelForm):
    class Meta:
        model = EmailCampaign
        fields = "__all__"
        widgets = {
            "subject": PersonalizationTextInput,
            "manual_emails": ManualEmailsWidget,
        }


class RecipientLogInline(TabularInline):
    model = RecipientLog
    fields = ("email_address", "recipient_name", "status", "provider", "sent_at")
    readonly_fields = ("email_address", "recipient_name", "status", "provider", "sent_at")
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EmailCampaign)
class EmailCampaignAdmin(BaseModelAdmin):
    form = EmailCampaignForm
    list_display = (
        "subject_preview",
        "audience_badge",
        "status_badge",
        "sent_count",
        "failed_count",
        "sent_at",
    )
    list_filter = ("status", "audience_type")
    search_fields = ("subject",)
    ordering = ("-created_at",)
    actions_detail = ["preview_email_action", "preview_recipients_action", "send_campaign_action"]

    fieldsets = (
        (
            "Audience",
            {
                "fields": ("audience_type", "event", "selected_members", "member_email_scope", "manual_emails"),
            },
        ),
        (
            "Campaign",
            {"fields": ("subject", "body")},
        ),
    )
    filter_horizontal = ("selected_members",)
    conditional_fields = {
        "event": "audience_type === 'event_registrants'",
        "selected_members": "audience_type === 'selected_members'",
        "member_email_scope": "audience_type === 'selected_members'",
        "manual_emails": "audience_type === 'manual'",
    }

    @display(description="Subject")
    def subject_preview(self, obj):
        return obj.subject[:60] + "..." if len(obj.subject) > 60 else obj.subject

    @display(description="Audience", label=True)
    def audience_badge(self, obj):
        if obj.audience_type == "subscribers":
            return "Subscribers", "info"
        return "Event", "warning"

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"draft": "info", "sending": "warning", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.status != "draft":
            readonly.extend(["name", "subject", "body", "audience_type", "event"])
        return readonly

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["email_config"] = EmailServiceConfig.load()
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
        """JSON endpoint for polling send progress."""
        obj = EmailCampaign.objects.get(pk=object_id)
        return JsonResponse({
            "status": obj.status,
            "total": obj.total_recipients,
            "sent": obj.sent_count,
            "failed": obj.failed_count,
        })

    def inline_preview_view(self, request):
        """Render email preview from POST data (subject + body). Opens in a new tab."""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_changelist"))
        from django.http import HttpResponse

        from ..services.personalize import personalize
        from ..services.preview import SAMPLE_CONTEXT, render_email_html

        body_html = personalize(request.POST.get("body", ""), SAMPLE_CONTEXT)
        html = render_email_html(body_html)
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
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Background send failed for campaign %s", campaign_pk)
            campaign.refresh_from_db()
            if campaign.status == "sending":
                campaign.status = "failed"
                campaign.save(update_fields=["status"])
