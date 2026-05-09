"""Gmail import views for campaign admin."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

import mail.admin.campaign as campaign_api
from core.models import GmailImportConfig
from mail.models import EmailCampaign


class CampaignGmailMixin:
    @action(description="Import Gmail HTML", url_path="import-gmail-html", icon="download")
    def import_gmail_html_action(self, request, object_id):
        return HttpResponseRedirect(reverse("admin:mail_emailcampaign_import_gmail_html", args=[object_id]))

    def import_gmail_html_view(self, request, object_id):
        obj = EmailCampaign.objects.get(pk=object_id)
        change_url = reverse("admin:mail_emailcampaign_change", args=[object_id])
        if obj.status != "draft":
            messages.warning(request, "Only draft campaigns can import Gmail HTML.")
            return HttpResponseRedirect(change_url)

        force_refresh = request.GET.get("refresh") == "1"
        try:
            mailbox = campaign_api.resolve_gmail_mailbox()
            gmail_messages = campaign_api.list_recent_sent_messages(
                limit=5,
                mailbox=mailbox,
                force_refresh=force_refresh,
            )
            gmail_import_config = GmailImportConfig.load()
        except campaign_api.GmailImportError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Import Gmail HTML - {obj.name}",
            "campaign": obj,
            "gmail_messages": gmail_messages,
            "gmail_import_config": gmail_import_config,
            "mailbox": mailbox,
            "gmail_folder": campaign_api.GMAIL_FOLDER_DISPLAY,
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
            mailbox = campaign_api.resolve_gmail_mailbox()
            campaign_api.import_message_into_campaign(obj, message_id, mailbox=mailbox)
        except campaign_api.GmailImportError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(selection_url)

        messages.success(
            request,
            "Imported Gmail HTML into the campaign body. Use Preview Email to verify the result before sending.",
        )
        return HttpResponseRedirect(change_url)
