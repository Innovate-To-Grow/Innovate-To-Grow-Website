"""Campaign preview views."""

import json

from django.http import HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

import mail.admin.campaign as campaign_api
from mail.models import EmailCampaign
from mail.services.personalize import personalize
from mail.services.preview import HTML_MARKER, SAMPLE_CONTEXT, render_email_html


class CampaignPreviewMixin:
    @action(description="Preview Email", url_path="preview-email", icon="visibility")
    def preview_email_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_send_preview", args=[object_id]))

    @action(description="Preview Recipients", url_path="preview-recipients", icon="group")
    def preview_recipients_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_preview_recipients", args=[object_id]))

    def preview_recipients_view(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        recipients = campaign_api.get_recipients(obj)
        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview Recipients - {obj.name}",
            "campaign": obj,
            "recipients": recipients,
            "back_url": reverse("admin:mail_emailcampaign_change", args=[object_id]),
        }
        return TemplateResponse(request, "admin/mail/preview_recipients.html", context)

    def send_campaign_preview_view(self, request, object_id):
        """Show email preview and step 1 of send flow for drafts."""
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])

        recipients = campaign_api.get_recipients(obj)
        preview = campaign_api.render_preview(obj)
        is_draft = obj.status == "draft"

        context = {
            **self.admin_site.each_context(request),
            "title": f"Preview Email - {obj.name}",
            "campaign": obj,
            "recipient_count": len(recipients),
            "preview_html_json": json.dumps(preview["html"]),
            "confirm_url": reverse("admin:mail_emailcampaign_send_confirm", args=[object_id]) if is_draft else None,
            "cancel_url": change_url,
        }
        return TemplateResponse(request, "admin/mail/send_preview.html", context)

    def inline_preview_view(self, request):
        """Render email preview from POST data."""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_changelist"))

        body = request.POST.get("body", "")
        body_format = request.POST.get("body_format", "plain")
        include_unsubscribe = request.POST.get("include_unsubscribe_header") == "on"
        if body_format == "html":
            body = HTML_MARKER + body
        body_html = personalize(body, SAMPLE_CONTEXT)
        unsubscribe_url = "#unsubscribe-preview" if include_unsubscribe else ""
        html = render_email_html(body_html, unsubscribe_url=unsubscribe_url)
        return HttpResponse(html)
