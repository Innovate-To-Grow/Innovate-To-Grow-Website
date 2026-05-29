"""Broadcast SMS campaign admin."""

import logging
import threading

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect, JsonResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import escape, format_html
from unfold.admin import TabularInline
from unfold.decorators import action, display
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget

from apps.mail.admin.campaign.views.status import _short_error
from apps.mail.admin.campaign.widgets import TicketSelectWidget
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.models.sms_campaign import SMS_AUDIENCE_CHOICES, SMS_EXCLUDE_AUDIENCE_CHOICES
from apps.mail.services.personalize import personalize
from apps.mail.services.sms_audience import get_sms_recipients
from core.admin import BaseModelAdmin, ReadOnlyModelAdmin
from event.models import Ticket


class SmsCampaignForm(forms.ModelForm):
    ticket = forms.ModelChoiceField(
        queryset=Ticket.objects.select_related("event").order_by("event__name", "order", "name"),
        required=False,
        label="Ticket type",
        widget=TicketSelectWidget,
    )
    exclude_ticket = forms.ModelChoiceField(
        queryset=Ticket.objects.select_related("event").order_by("event__name", "order", "name"),
        required=False,
        label="Exclude ticket type",
        widget=TicketSelectWidget,
    )

    class Meta:
        model = SmsCampaign
        fields = "__all__"
        widgets = {
            "name": forms.TextInput,
            "message": UnfoldAdminTextareaWidget,
            "phone_policy": UnfoldAdminSelectWidget,
            "audience_type": UnfoldAdminSelectWidget,
            "event": UnfoldAdminSelectWidget,
            "ticket_id": forms.HiddenInput,
            "manual_phones": UnfoldAdminTextareaWidget,
            "exclude_audience_type": UnfoldAdminSelectWidget,
            "exclude_event": UnfoldAdminSelectWidget,
            "exclude_ticket_id": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "audience_type" in self.fields:
            self.fields["audience_type"].choices = SMS_AUDIENCE_CHOICES
        if "exclude_audience_type" in self.fields:
            self.fields["exclude_audience_type"].choices = SMS_EXCLUDE_AUDIENCE_CHOICES

        if self.instance and self.instance.pk and self.instance.status != "draft":
            self._disable_sent_campaign_fields()
        if self.instance and self.instance.pk and self.instance.audience_type == "ticket_type":
            self._restore_ticket_initial()
        if self.instance and self.instance.pk and self.instance.exclude_audience_type == "ticket_type":
            self._restore_exclude_ticket_initial()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience_type") == "ticket_type":
            self._clean_ticket_type(cleaned)
        else:
            cleaned["ticket_id"] = ""

        exclude_type = (cleaned.get("exclude_audience_type") or "").strip()
        if exclude_type == "ticket_type":
            self._clean_exclude_ticket_type(cleaned)
        else:
            cleaned["exclude_ticket_id"] = ""
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.audience_type != "ticket_type":
            instance.ticket_id = ""
        if not (instance.exclude_audience_type or "").strip():
            instance.exclude_event_id = None
            instance.exclude_ticket_id = ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def _disable_sent_campaign_fields(self):
        for field_name in (
            "name",
            "message",
            "phone_policy",
            "audience_type",
            "event",
            "ticket",
            "ticket_id",
            "selected_members",
            "manual_phones",
            "exclude_audience_type",
            "exclude_event",
            "exclude_ticket",
            "exclude_ticket_id",
            "exclude_members",
        ):
            if field_name in self.fields:
                self.fields[field_name].disabled = True

    def _restore_ticket_initial(self):
        ticket_id = self.instance.ticket_id.strip()
        if ticket_id:
            try:
                self.initial["ticket"] = Ticket.objects.get(pk=ticket_id).pk
            except Ticket.DoesNotExist:
                pass

    def _restore_exclude_ticket_initial(self):
        ticket_id = self.instance.exclude_ticket_id.strip()
        if ticket_id:
            try:
                self.initial["exclude_ticket"] = Ticket.objects.get(pk=ticket_id).pk
            except Ticket.DoesNotExist:
                pass

    def _clean_ticket_type(self, cleaned):
        ticket = cleaned.get("ticket")
        if not ticket:
            self.add_error("ticket", "A ticket type must be selected.")
            return
        event = cleaned.get("event")
        if event and ticket.event_id != event.pk:
            self.add_error("ticket", "Selected ticket does not belong to the selected event.")
        cleaned["ticket_id"] = str(ticket.pk)

    def _clean_exclude_ticket_type(self, cleaned):
        exclude_ticket = cleaned.get("exclude_ticket")
        if not exclude_ticket:
            self.add_error("exclude_ticket", "A ticket type must be selected for ticket exclusion.")
            return
        exclude_event = cleaned.get("exclude_event")
        if exclude_event and exclude_ticket.event_id != exclude_event.pk:
            self.add_error("exclude_ticket", "Selected ticket does not belong to the exclusion event.")
        cleaned["exclude_ticket_id"] = str(exclude_ticket.pk)


class SmsRecipientLogInline(TabularInline):
    model = SmsRecipientLog
    fields = ("phone_number", "recipient_name", "status", "error_message", "provider", "sent_at")
    readonly_fields = fields
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class SmsAudienceTypeFilter(admin.SimpleListFilter):
    title = "audience type"
    parameter_name = "audience_type"

    def lookups(self, request, model_admin):
        return SMS_AUDIENCE_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(audience_type=self.value())
        return queryset


@admin.register(SmsCampaign)
class SmsCampaignAdmin(BaseModelAdmin):
    form = SmsCampaignForm
    change_form_template = "admin/mail/smscampaign/change_form.html"
    change_list_template = "admin/mail/smscampaign/change_list.html"
    inlines = (SmsRecipientLogInline,)

    list_display = (
        "name_preview",
        "audience_badge",
        "phone_policy_badge",
        "status_badge",
        "sent_count",
        "failed_count",
        "sent_at",
    )
    list_filter = ("status", "phone_policy", SmsAudienceTypeFilter)
    search_fields = ("name", "message")
    ordering = ("-created_at",)
    actions_detail = [
        "preview_sms_action",
        "preview_recipients_action",
        "send_sms_campaign_action",
    ]

    fieldsets = (
        (
            "Audience",
            {
                "fields": (
                    "phone_policy",
                    "audience_type",
                    "event",
                    "ticket",
                    "ticket_id",
                    "selected_members",
                    "manual_phones",
                    "exclude_audience_type",
                    "exclude_event",
                    "exclude_ticket",
                    "exclude_ticket_id",
                    "exclude_members",
                ),
            },
        ),
        ("Campaign", {"fields": ("name", "message")}),
    )
    filter_horizontal = ("selected_members", "exclude_members")
    conditional_fields = {
        "event": (
            "audience_type === 'event_registrants' || audience_type === 'ticket_type'"
            " || audience_type === 'checked_in' || audience_type === 'not_checked_in'"
        ),
        "ticket": "audience_type === 'ticket_type'",
        "selected_members": "audience_type === 'selected_members'",
        "manual_phones": "audience_type === 'manual'",
        "exclude_event": (
            "exclude_audience_type === 'event_registrants' || exclude_audience_type === 'ticket_type'"
            " || exclude_audience_type === 'checked_in' || exclude_audience_type === 'not_checked_in'"
        ),
        "exclude_ticket": "exclude_audience_type === 'ticket_type'",
        "exclude_members": "exclude_audience_type === 'selected_members'",
    }

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/preview-recipients/",
                self.admin_site.admin_view(self.preview_recipients_view),
                name="mail_smscampaign_preview_recipients",
            ),
            path(
                "<path:object_id>/send-sms/",
                self.admin_site.admin_view(self.send_sms_preview_view),
                name="mail_smscampaign_send_preview",
            ),
            path(
                "<path:object_id>/send-sms/confirm/",
                self.admin_site.admin_view(self.send_sms_confirm_view),
                name="mail_smscampaign_send_confirm",
            ),
            path(
                "<path:object_id>/send-sms/status/",
                self.admin_site.admin_view(self.send_sms_status_view),
                name="mail_smscampaign_send_status",
            ),
            path(
                "<path:object_id>/send-sms/status.json",
                self.admin_site.admin_view(self.send_sms_status_json),
                name="mail_smscampaign_send_status_json",
            ),
        ]
        return custom_urls + super().get_urls()

    @action(description="Preview SMS", url_path="preview-sms", icon="visibility")
    def preview_sms_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_preview", args=[object_id]))

    @action(description="Preview Recipients", url_path="preview-recipients", icon="group")
    def preview_recipients_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_preview_recipients", args=[object_id]))

    @action(description="Send SMS Campaign", url_path="send-sms", icon="send")
    def send_sms_campaign_action(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        if obj.status != "draft":
            messages.warning(request, "This SMS campaign has already been sent.")
            return HttpResponseRedirect(reverse("admin:mail_smscampaign_change", args=[object_id]))
        return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_preview", args=[object_id]))

    def preview_recipients_view(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        recipients = get_sms_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview SMS Recipients - {obj.name}",
            "campaign": obj,
            "recipients": recipients,
            "back_url": reverse("admin:mail_smscampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/smscampaign/preview_recipients.html", context)

    def send_sms_preview_view(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_smscampaign_change", args=[object_id])
        recipients = get_sms_recipients(obj)
        preview = personalize(
            obj.message,
            {
                "first_name": "Hongzhe",
                "last_name": "Xie",
                "full_name": "Hongzhe Xie",
            },
        )
        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview SMS - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_message": preview,
            "confirm_url": reverse("admin:mail_smscampaign_send_confirm", args=[object_id])
            if obj.status == "draft"
            else None,
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/mail/smscampaign/send_preview.html", context)

    def send_sms_confirm_view(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_smscampaign_change", args=[object_id])
        if obj.status != "draft":
            messages.warning(request, "This SMS campaign has already been sent.")
            return HttpResponseRedirect(change_url)

        if request.method == "POST":
            from django.conf import settings as django_settings

            if getattr(django_settings, "ADMIN_REQUIRE_CONFIRMATION", True):
                confirmation_text = request.POST.get("confirmation_text", "").strip()
                if confirmation_text != obj.name:
                    messages.error(request, "Confirmation text does not match campaign name. Please try again.")
                    return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_confirm", args=[object_id]))

            updated = SmsCampaign.objects.filter(pk=obj.pk, status="draft").update(status="sending")
            if not updated:
                messages.warning(request, "This SMS campaign has already been sent.")
                return HttpResponseRedirect(change_url)

            thread = threading.Thread(
                target=self._background_send,
                args=(obj.pk, request.user.pk),
                daemon=False,
            )
            thread.start()

            return HttpResponseRedirect(reverse("admin:mail_smscampaign_send_status", args=[object_id]))

        recipients = get_sms_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Confirm SMS Send - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_url": reverse("admin:mail_smscampaign_send_preview", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/smscampaign/confirm_send.html", context)

    def send_sms_status_view(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Sending SMS - {obj.name}",
            "campaign": obj,
            "status_json_url": reverse("admin:mail_smscampaign_send_status_json", args=[object_id]),
            "back_url": reverse("admin:mail_smscampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/smscampaign/send_status.html", context)

    def send_sms_status_json(self, request, object_id):
        obj = SmsCampaign.objects.get(pk=object_id)
        recent_logs = [
            {
                "phone": log.phone_number,
                "name": log.recipient_name,
                "status": log.status,
                "error": _short_error(log.error_message),
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            }
            for log in SmsRecipientLog.objects.filter(campaign=obj)
            .exclude(status="pending")
            .order_by("-updated_at")[:20]
        ]
        failed_logs = [
            {
                "phone": log.phone_number,
                "name": log.recipient_name,
                "error": _short_error(log.error_message),
            }
            for log in SmsRecipientLog.objects.filter(campaign=obj, status="failed").order_by("-updated_at")
        ]
        first_sent_at = (
            SmsRecipientLog.objects.filter(campaign=obj, sent_at__isnull=False)
            .order_by("sent_at")
            .values_list("sent_at", flat=True)
            .first()
        )
        return JsonResponse(
            {
                "status": obj.status,
                "total": obj.total_recipients,
                "sent": obj.sent_count,
                "failed": obj.failed_count,
                "error_message": _short_error(obj.error_message),
                "started_at": first_sent_at.isoformat() if first_sent_at else None,
                "recent_logs": recent_logs,
                "failed_logs": failed_logs,
            }
        )

    @staticmethod
    def _background_send(campaign_pk, user_pk):
        import django

        django.db.connections.close_all()
        from apps.mail.models import SmsCampaign as CampaignModel
        from apps.mail.services.send_sms_campaign import send_sms_campaign

        User = get_user_model()
        campaign = CampaignModel.objects.get(pk=campaign_pk)
        user = User.objects.get(pk=user_pk)
        try:
            send_sms_campaign(campaign, sent_by=user)
        except Exception:
            logging.getLogger(__name__).exception("Background SMS send failed for campaign %s", campaign_pk)
            campaign.refresh_from_db()
            if campaign.status in ("draft", "sending"):
                campaign.status = "failed"
            campaign.error_message = "SMS campaign send failed. Check server logs for details."
            campaign.save(update_fields=["status", "error_message"])
        finally:
            django.db.connections.close_all()

    @display(description="Campaign")
    def name_preview(self, obj):
        return obj.name[:60] + "..." if len(obj.name) > 60 else obj.name

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

    @display(description="Phone Eligibility", label=True)
    def phone_policy_badge(self, obj):
        if obj.phone_policy == "verified_opt_in":
            return "Verified opt-ins", "success"
        return "Any verified", "warning"

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"draft": "info", "sending": "warning", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="SMS Message")
    def message_readonly(self, obj):
        if not obj:
            return "-"
        return format_html(
            '<pre class="max-h-[70vh] max-w-2xl overflow-auto whitespace-pre-wrap break-words '
            "rounded-default border border-base-200 bg-base-50 px-3 py-2 font-mono text-sm font-medium "
            'text-font-default-light shadow-xs dark:border-base-700 dark:bg-base-800 dark:text-font-default-dark">'
            "{message}</pre>",
            message=escape(obj.message or ""),
        )

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if obj and obj.status != "draft":
            for i, (title, options) in enumerate(fieldsets):
                fields = list(options.get("fields", ()))
                if "message" in fields:
                    fields[fields.index("message")] = "message_readonly"
                    fieldsets[i] = (title, {**options, "fields": tuple(fields)})
        if obj and obj.error_message:
            fieldsets.append(("Error Details", {"fields": ("error_message",), "classes": ("collapse",)}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and obj.error_message:
            readonly.append("error_message")
        if obj and obj.status != "draft":
            readonly.extend(
                [
                    "name",
                    "message_readonly",
                    "phone_policy",
                    "audience_type",
                    "event",
                    "ticket_id",
                    "selected_members",
                    "manual_phones",
                    "exclude_audience_type",
                    "exclude_event",
                    "exclude_ticket_id",
                    "exclude_members",
                ]
            )
        return readonly

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            from core.models import AWSCredentialConfig

            extra_context["aws_config"] = AWSCredentialConfig.load()
        except Exception:
            extra_context.setdefault("aws_config", None)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(SmsRecipientLog)
class SmsRecipientLogAdmin(ReadOnlyModelAdmin):
    list_display = (
        "campaign",
        "recipient_name",
        "phone_number",
        "status_badge",
        "error_preview",
        "provider",
        "sent_at",
    )
    list_filter = ("status", "provider", "campaign")
    search_fields = ("phone_number", "recipient_name", "sns_message_id")
    list_select_related = ("campaign",)
    ordering = ("-updated_at",)

    fieldsets = (
        (None, {"fields": ("campaign", "member", "phone_number", "recipient_name")}),
        ("Delivery", {"fields": ("status", "provider", "error_message", "sns_message_id", "sent_at")}),
    )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff

    @display(description="Status", label=True)
    def status_badge(self, obj):
        colors = {"pending": "info", "sent": "success", "failed": "danger"}
        return obj.get_status_display(), colors.get(obj.status, "info")

    @display(description="Error")
    def error_preview(self, obj):
        if not obj.error_message:
            return "-"
        return obj.error_message[:120] + "..." if len(obj.error_message) > 120 else obj.error_message
