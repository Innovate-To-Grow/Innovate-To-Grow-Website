from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.models import SmsCampaign


class SmsRecipientLogInlinePermissionTests(TestCase):
    def test_inline_has_no_add_permission(self):
        from apps.mail.admin.sms_campaign import SmsRecipientLogInline

        inline = SmsRecipientLogInline(SmsCampaign, AdminSite())
        request = RequestFactory().get("/")

        self.assertFalse(inline.has_add_permission(request))


class SmsAudienceTypeFilterTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_filter_lookups_match_choices(self):
        from apps.mail.admin.sms_campaign import SmsAudienceTypeFilter
        from apps.mail.models.sms.campaign_options import SMS_AUDIENCE_CHOICES

        instance = SmsAudienceTypeFilter.__new__(SmsAudienceTypeFilter)
        self.assertEqual(instance.lookups(request=None, model_admin=None), SMS_AUDIENCE_CHOICES)

    def test_changelist_filter_narrows_by_audience_type(self):
        SmsCampaign.objects.create(name="Subs", message="Hi", audience_type="subscribers")
        SmsCampaign.objects.create(name="Staff", message="Hi", audience_type="staff")

        filtered = self.client.get(
            reverse("admin:mail_smscampaign_changelist"),
            {"audience_type": "subscribers"},
        )
        self.assertEqual(filtered.status_code, 200)
        names = {c.name for c in filtered.context["cl"].queryset}
        self.assertEqual(names, {"Subs"})

        unfiltered = self.client.get(reverse("admin:mail_smscampaign_changelist"))
        self.assertEqual({c.name for c in unfiltered.context["cl"].queryset}, {"Subs", "Staff"})
