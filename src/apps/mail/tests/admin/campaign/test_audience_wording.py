"""The audience labels and help texts say in plain words who each audience reaches, and the resolvers agree."""

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.admin.campaign.forms import EmailCampaignForm
from apps.mail.models import EmailCampaign
from apps.mail.models.campaign import ALL_MEMBERS_LABEL, EXCLUDE_AUDIENCE_CHOICES, SUBSCRIBERS_LABEL
from apps.mail.services.audience.resolvers import recipients_for_audience


def emails_for(audience_type, *, send_all):
    recipients = recipients_for_audience(
        audience_type, send_all=send_all, event=None, ticket_uuid_str="", selected_members=None, manual_emails_body=""
    )
    return sorted(recipient["email"] for recipient in recipients)


class AudienceLabelTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_labels_name_the_subscription_difference(self):
        self.assertEqual(SUBSCRIBERS_LABEL, "All subscribers (subscribed email addresses only)")
        self.assertEqual(ALL_MEMBERS_LABEL, "All active members (subscribed or not)")
        self.assertEqual(EmailCampaign(audience_type="subscribers").get_audience_type_display(), SUBSCRIBERS_LABEL)
        self.assertEqual(EmailCampaign(audience_type="all_members").get_audience_type_display(), ALL_MEMBERS_LABEL)
        self.assertIn(("subscribers", SUBSCRIBERS_LABEL), EXCLUDE_AUDIENCE_CHOICES)
        self.assertIn(("all_members", ALL_MEMBERS_LABEL), EXCLUDE_AUDIENCE_CHOICES)

    def test_form_offers_the_labels_and_explains_them(self):
        form = EmailCampaignForm()

        self.assertIn(("subscribers", SUBSCRIBERS_LABEL), list(form.fields["audience_type"].choices))
        self.assertIn(("all_members", ALL_MEMBERS_LABEL), list(form.fields["audience_type"].choices))
        help_text = form.fields["audience_type"].help_text
        self.assertIn("All subscribers: active members who have an email address with its subscription on", help_text)
        self.assertIn("All active members: every active member, including people who unsubscribed", help_text)
        self.assertIn("Inactive members are never included", help_text)

    def test_change_page_and_list_show_the_wording(self):
        self.client.force_login(make_superuser())
        campaign = EmailCampaign.objects.create(name="Newsletter", subject="s", body="b", audience_type="all_members")

        response = self.client.get(reverse("admin:mail_emailcampaign_change", args=[campaign.pk]))
        self.assertContains(response, ALL_MEMBERS_LABEL)
        self.assertContains(response, "including people who unsubscribed")

        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))
        self.assertContains(response, "All active members")

    def test_badges_use_the_same_words(self):
        model_admin = EmailCampaignAdmin(EmailCampaign, AdminSite())

        self.assertEqual(
            model_admin.audience_badge(EmailCampaign(audience_type="subscribers")), ("All subscribers", "info")
        )
        self.assertEqual(
            model_admin.audience_badge(EmailCampaign(audience_type="all_members")), ("All active members", "info")
        )


class AudienceLabelsMatchBehaviourTests(TestCase):
    """What the labels and help texts promise is what the resolvers do."""

    def setUp(self):
        cache.clear()
        # Subscribed primary, unsubscribed secondary.
        subscribed = make_member(email="subscribed@example.com")
        ContactEmail.objects.create(
            member=subscribed, email_address="subscribed-2@example.com", email_type="secondary", subscribe=False
        )
        # Unsubscribed primary, subscribed secondary.
        opted_out = make_member(email="opted-out@example.com")
        opted_out.contact_emails.update(subscribe=False)
        ContactEmail.objects.create(
            member=opted_out, email_address="opted-out-2@example.com", email_type="secondary", subscribe=True
        )
        # Inactive, every address subscribed.
        make_member(email="inactive@example.com", is_active=False)

    def test_all_subscribers_is_subscribed_addresses_of_active_members_only(self):
        # Primary email only: the primary address, and only while it is subscribed.
        self.assertEqual(emails_for("subscribers", send_all=False), ["subscribed@example.com"])
        # All emails: every subscribed address, whichever type it is.
        self.assertEqual(
            emails_for("subscribers", send_all=True), ["opted-out-2@example.com", "subscribed@example.com"]
        )

    def test_all_active_members_includes_people_who_unsubscribed_and_never_inactive_members(self):
        self.assertEqual(emails_for("all_members", send_all=False), ["opted-out@example.com", "subscribed@example.com"])
        self.assertEqual(
            emails_for("all_members", send_all=True),
            ["opted-out-2@example.com", "opted-out@example.com", "subscribed-2@example.com", "subscribed@example.com"],
        )
