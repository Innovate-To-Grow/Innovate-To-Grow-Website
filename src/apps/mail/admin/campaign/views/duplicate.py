"""Duplicate a campaign into a new editable draft, and keep draft-only actions off locked campaigns."""

from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.duplicate import NAME_MAX_LENGTH, copy_name, duplicate_campaign

# Detail actions that only make sense while a campaign is still a draft; a locked campaign does not show them.
DRAFT_ONLY_DETAIL_ACTIONS = ("_send_campaign_action", "_import_gmail_html_action")
# ...and those that only make sense once it has been sent: a draft does not show them.
SENT_ONLY_DETAIL_ACTIONS = ("_delivery_monitoring_action",)
AUDIENCE_CHOICES = ("same", "manual")


def _is_draft(object_id) -> bool:
    try:
        return EmailCampaign.objects.filter(pk=unquote(str(object_id)), status="draft").exists()
    except (ValueError, ValidationError):
        return False


class CampaignDuplicateMixin:
    # The list action only creates drafts, so it skips the type-to-confirm step bulk actions get by default.
    actions_no_confirmation = ["duplicate_campaigns_action"]

    def get_actions_detail(self, request, object_id=None):
        actions = super().get_actions_detail(request, object_id)
        if object_id is not None:
            hidden = SENT_ONLY_DETAIL_ACTIONS if _is_draft(object_id) else DRAFT_ONLY_DETAIL_ACTIONS
            actions = [item for item in actions if not item.action_name.endswith(hidden)]
        return actions

    @action(description="Duplicate campaign", url_path="duplicate", icon="content_copy", permissions=["change"])
    def duplicate_campaign_action(self, request, object_id):
        """A confirmation page (GET), then the copy (POST): a new draft the user is taken to."""
        # Creating a campaign needs add access, which Unfold's per-action permissions cannot express.
        if not self.has_add_permission(request):
            raise PermissionDenied("You do not have permission to create campaigns.")
        campaign = self.get_object(request, unquote(str(object_id)))
        if campaign is None:
            raise Http404("Campaign not found.")

        if request.method == "POST":
            audience = request.POST.get("audience", "same")
            copy = duplicate_campaign(
                campaign,
                name=request.POST.get("name", ""),
                new_manual_audience=audience == "manual" and audience in AUDIENCE_CHOICES,
            )
            what = "an empty Manual Emails list" if audience == "manual" else "the same audience"
            messages.success(
                request,
                f"Created the draft “{copy.name}” from “{campaign.name}” with {what}. "
                "Check its content and audience, then Preview and Send it.",
            )
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_change", args=[copy.pk]))

        context = {
            **self.admin_site.each_context(request),
            "title": f"Duplicate - {campaign.name}",
            "campaign": campaign,
            "suggested_name": copy_name(campaign.name),
            "name_max_length": NAME_MAX_LENGTH,
            "cancel_url": reverse("admin:mail_emailcampaign_change", args=[campaign.pk]),
        }
        return TemplateResponse(request, "admin/mail/duplicate_campaign.html", context)

    @admin.action(description="Duplicate as new draft", permissions=["add"])
    def duplicate_campaigns_action(self, request, queryset):
        copies = [duplicate_campaign(campaign) for campaign in queryset.order_by("created_at")]
        if len(copies) == 1:
            messages.success(request, f"Created the draft “{copies[0].name}”. Check it, then Preview and Send it.")
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_change", args=[copies[0].pk]))
        messages.success(request, f"Created {len(copies)} draft copies.")
        return None
