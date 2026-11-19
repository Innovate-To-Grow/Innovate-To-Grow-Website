"""Duplicate a campaign into a new editable draft, and keep draft-only actions off locked campaigns."""

from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseBadRequest, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from unfold.decorators import action

from apps.core.models import EmailServiceConfig
from apps.mail.models import EmailCampaign
from apps.mail.services.audience.suppression import normalize_address
from apps.mail.services.campaign.content.duplicate import (
    NAME_MAX_LENGTH,
    copy_name,
    create_retry_campaign,
    duplicate_campaign,
)
from apps.mail.services.campaign.content.retry import (
    RetryRefused,
    retry_eligibility_for,
)
from apps.mail.services.campaign.content.retry_delivery import retry_delivery_snapshot_token
from apps.mail.services.campaign.content.retry_route import assert_alternate_retry_route

# Detail actions that only make sense while a campaign is still a draft; a locked campaign does not show them.
DRAFT_ONLY_DETAIL_ACTIONS = ("_send_campaign_action", "_import_gmail_html_action")
# ...and those that only make sense once it has been sent: a draft does not show them.
SENT_ONLY_DETAIL_ACTIONS = ("_delivery_monitoring_action",)
AUDIENCE_CHOICES = ("same", "manual", "retry")


def _is_draft(object_id) -> bool:
    try:
        return EmailCampaign.objects.filter(pk=unquote(str(object_id)), status="draft").exists()
    except (ValueError, ValidationError):
        return False


def _is_retry(object_id) -> bool:
    try:
        return EmailCampaign.objects.filter(pk=unquote(str(object_id)), retry_source_campaign__isnull=False).exists()
    except (ValueError, ValidationError):
        return False


def _retry_sending_context(eligibility, existing_retry) -> dict:
    """Describe the reviewed transport and refuse to offer an unchanged rejected route."""
    retry_config = EmailServiceConfig.load() if eligibility and existing_retry is None else None
    if existing_retry is not None:
        retry_sending_method = dict(EmailServiceConfig.Provider.choices).get(
            existing_retry.retry_sending_provider, existing_retry.retry_sending_provider
        )
        retry_from_email = existing_retry.retry_from_email
    else:
        retry_sending_method = (
            retry_config.get_provider_display() if retry_config is not None and retry_config.pk else ""
        )
        retry_from_email = retry_config.from_email if retry_config is not None and retry_config.pk else ""
    route_problem = ""
    if eligibility:
        provider = (
            existing_retry.retry_sending_provider
            if existing_retry is not None
            else getattr(retry_config, "provider", "")
        )
        try:
            assert_alternate_retry_route(eligibility.rejected_sender_provider, provider)
        except RetryRefused as exc:
            route_problem = str(exc)
    return {
        "route_problem": route_problem,
        "sender_rejection": eligibility and eligibility.rejected_sender_provider is not None,
        "original_provider": dict(EmailServiceConfig.Provider.choices).get(
            eligibility.rejected_sender_provider if eligibility else None, "Unverified"
        ),
        "retry_sending_method": retry_sending_method,
        "retry_from_email": retry_from_email,
        "retry_delivery_snapshot": retry_delivery_snapshot_token(retry_config) if retry_config is not None else "",
    }


class CampaignDuplicateMixin:
    # The list action only creates drafts, so it skips the type-to-confirm step bulk actions get by default.
    actions_no_confirmation = ["duplicate_campaigns_action"]

    def get_actions_detail(self, request, object_id=None):
        actions = super().get_actions_detail(request, object_id)
        if object_id is not None:
            hidden = SENT_ONLY_DETAIL_ACTIONS if _is_draft(object_id) else DRAFT_ONLY_DETAIL_ACTIONS
            actions = [item for item in actions if not item.action_name.endswith(hidden)]
            if _is_retry(object_id):
                actions = [item for item in actions if not item.action_name.endswith("duplicate_campaign_action")]
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
        if campaign.retry_source_campaign_id:
            return HttpResponseBadRequest("A one-address retry draft cannot be duplicated.")

        if request.method == "POST":
            audience = request.POST.get("audience", "same")
            retry_fields = ("retry_address", "retry_delivery_snapshot")
            if "retry_address" in request.GET or any(field in request.POST for field in retry_fields):
                if audience != "retry":
                    return HttpResponseBadRequest("This review can only prepare a one-address retry.")
                if "retry_address" in request.GET and normalize_address(
                    request.GET["retry_address"]
                ) != normalize_address(request.POST.get("retry_address")):
                    return HttpResponseBadRequest("The submitted retry address differs from the review link.")
            retry_address = ""
            created = True
            if audience == "retry":
                try:
                    copy, created = create_retry_campaign(
                        campaign,
                        request.POST.get("retry_address", ""),
                        name=request.POST.get("name", ""),
                        expected_delivery_snapshot=request.POST.get("retry_delivery_snapshot", ""),
                    )
                except RetryRefused as exc:
                    return HttpResponseBadRequest(str(exc))
                retry_address = copy.retry_address
            else:
                copy = duplicate_campaign(
                    campaign,
                    name=request.POST.get("name", ""),
                    new_manual_audience=audience == "manual",
                )
            what = (
                f"only {retry_address} as its Manual Emails audience"
                if retry_address
                else "an empty Manual Emails list"
                if audience == "manual"
                else "the same audience"
            )
            messages.success(
                request,
                f"{'Created' if created else 'Reused'} the draft “{copy.name}” from “{campaign.name}” with {what}. "
                "Check its content and audience, then Preview and Send it.",
            )
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_change", args=[copy.pk]))

        eligibility = retry_eligibility_for(campaign, request.GET.get("retry_address", ""))
        retry_address = eligibility.address if eligibility else ""
        if "retry_address" in request.GET and not retry_address:
            return HttpResponseBadRequest(
                "This address is no longer eligible for a retry. Return to Bounced addresses."
            )
        existing_retry = (
            EmailCampaign.objects.filter(retry_source_campaign=campaign, retry_address=retry_address).first()
            if retry_address
            else None
        )
        context = {
            **self.admin_site.each_context(request),
            "title": f"Duplicate - {campaign.name}",
            "campaign": campaign,
            "suggested_name": copy_name(campaign.name),
            "name_max_length": NAME_MAX_LENGTH,
            "cancel_url": reverse("admin:mail_emailcampaign_change", args=[campaign.pk]),
            "retry_address": retry_address,
            "existing_retry": existing_retry,
            **_retry_sending_context(eligibility, existing_retry),
        }
        return TemplateResponse(request, "admin/mail/emailcampaign/duplicate_campaign.html", context)

    @admin.action(description="Duplicate as new draft", permissions=["add"])
    def duplicate_campaigns_action(self, request, queryset):
        if queryset.filter(retry_source_campaign__isnull=False).exists():
            messages.error(request, "One-address retry drafts cannot be duplicated into ordinary campaigns.")
            return None
        copies = [duplicate_campaign(campaign) for campaign in queryset.order_by("created_at")]
        if len(copies) == 1:
            messages.success(request, f"Created the draft “{copies[0].name}”. Check it, then Preview and Send it.")
            return HttpResponseRedirect(reverse("admin:mail_emailcampaign_change", args=[copies[0].pk]))
        messages.success(request, f"Created {len(copies)} draft copies.")
        return None
