"""The Duplicate campaign flow and the locked state of a campaign that is no longer a draft."""

from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign


def make_campaign(status="sent", **overrides):
    values = {
        "name": "Spring invitation",
        "subject": "You're invited",
        "body": "Hello",
        "audience_type": "manual",
        "manual_emails": "one@example.com\ntwo@example.com",
        "status": status,
        "sent_at": timezone.now() if status != "draft" else None,
        "sent_count": 2 if status != "draft" else 0,
    }
    values.update(overrides)
    return EmailCampaign.objects.create(**values)


class CampaignDuplicateViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.client.force_login(self.admin_user)

    def duplicate_url(self, campaign):
        return reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[campaign.pk])

    def test_page_shows_the_original_and_a_suggested_name(self):
        campaign = make_campaign()

        response = self.client.get(self.duplicate_url(campaign))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Copy of Spring invitation"')
        self.assertContains(response, "record of what went out (sent on")
        self.assertContains(response, "Manual Emails")

    def test_post_creates_a_draft_with_the_same_audience_and_opens_it(self):
        campaign = make_campaign()

        response = self.client.post(self.duplicate_url(campaign), {"name": "Spring invitation 2", "audience": "same"})

        copy = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertRedirects(response, reverse("admin:mail_emailcampaign_change", args=[copy.pk]))
        self.assertEqual((copy.name, copy.status, copy.sent_count), ("Spring invitation 2", "draft", 0))
        self.assertEqual((copy.audience_type, copy.manual_emails), ("manual", campaign.manual_emails))
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("Created the draft “Spring invitation 2”" in message for message in messages), messages)

    def test_post_with_a_new_manual_list_starts_an_empty_manual_audience(self):
        campaign = make_campaign(audience_type="all_members", manual_emails="")

        response = self.client.post(self.duplicate_url(campaign), {"name": "", "audience": "manual"})

        copy = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(copy.name, "Copy of Spring invitation")
        self.assertEqual((copy.audience_type, copy.manual_emails), ("manual", ""))

    def test_unknown_audience_choice_keeps_the_same_audience(self):
        campaign = make_campaign(audience_type="all_members", manual_emails="")

        self.client.post(self.duplicate_url(campaign), {"name": "", "audience": "everyone"})

        copy = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertEqual(copy.audience_type, "all_members")

    def test_unknown_campaign_is_404(self):
        response = self.client.get(reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=["nope"]))

        self.assertEqual(response.status_code, 404)

    def test_list_action_duplicates_the_selected_campaigns(self):
        first, second = make_campaign(name="First"), make_campaign(name="Second", status="draft")

        response = self.client.post(
            reverse("admin:mail_emailcampaign_changelist"),
            {"action": "duplicate_campaigns_action", "_selected_action": [str(first.pk), str(second.pk)]},
        )

        self.assertEqual(response.status_code, 302)
        names = set(EmailCampaign.objects.filter(status="draft").values_list("name", flat=True))
        self.assertEqual(names, {"Second", "Copy of First", "Copy of Second"})

    def test_list_action_opens_the_copy_when_one_campaign_is_selected(self):
        campaign = make_campaign()

        response = self.client.post(
            reverse("admin:mail_emailcampaign_changelist"),
            {"action": "duplicate_campaigns_action", "_selected_action": [str(campaign.pk)]},
        )

        copy = EmailCampaign.objects.exclude(pk=campaign.pk).get()
        self.assertRedirects(response, reverse("admin:mail_emailcampaign_change", args=[copy.pk]))


class LockedCampaignTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.client.force_login(self.admin_user)
        self.model_admin = EmailCampaignAdmin(EmailCampaign, AdminSite())

    def detail_action_names(self, campaign):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        actions = self.model_admin.get_actions_detail(request, str(campaign.pk))
        return [action.action_name.removeprefix("mail_emailcampaign_").removesuffix("_action") for action in actions]

    def test_draft_offers_every_detail_action(self):
        names = self.detail_action_names(make_campaign(status="draft"))

        self.assertEqual(
            names, ["preview_email", "preview_recipients", "duplicate_campaign", "import_gmail_html", "send_campaign"]
        )

    def test_locked_campaign_hides_send_and_import_but_offers_duplicate(self):
        for status in ("queued", "sending", "partial", "sent", "failed"):
            with self.subTest(status=status):
                names = self.detail_action_names(make_campaign(status=status))

                self.assertEqual(names, ["preview_email", "preview_recipients", "duplicate_campaign"])

    def test_change_page_of_a_locked_campaign_explains_the_lock_and_links_to_duplicate(self):
        campaign = make_campaign(status="partial")

        response = self.client.get(reverse("admin:mail_emailcampaign_change", args=[campaign.pk]))

        self.assertContains(response, 'id="campaign-locked-banner"')
        self.assertContains(response, "This campaign is partially sent and locked.")
        self.assertContains(response, "Reusable login links")
        self.assertContains(response, reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[campaign.pk]))

    def test_change_page_of_a_draft_has_no_lock_banner(self):
        campaign = make_campaign(status="draft")

        response = self.client.get(reverse("admin:mail_emailcampaign_change", args=[campaign.pk]))

        self.assertNotContains(response, 'id="campaign-locked-banner"')
