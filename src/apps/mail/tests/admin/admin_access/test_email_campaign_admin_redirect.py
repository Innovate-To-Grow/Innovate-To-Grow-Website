from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.cms.models import CMSPage
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign


class EmailCampaignAdminRedirectTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.request_factory = RequestFactory()
        self.model_admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.published_page = CMSPage.objects.create(
            slug="campaign-destination",
            route="/campaign-destination",
            title="Campaign Destination",
            status="published",
        )
        self.archived_page = CMSPage.objects.create(
            slug="old-campaign-destination",
            route="/old-campaign-destination",
            title="Old Campaign Destination",
            status="archived",
        )

    def test_new_campaign_form_requires_redirect_destination(self):
        form = self._get_form(
            data={
                "audience_type": "subscribers",
                "member_email_scope": "primary",
                "subject": "Spring Update",
                "body_format": "plain",
                "body": "Draft body",
                "login_redirect_path": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("login_redirect_path", form.errors)

    def test_redirect_choices_include_account_app_routes_and_published_cms_pages(self):
        form = self._get_form()
        choices = dict(form.fields["login_redirect_path"].choices)

        self.assertIn("/account", choices)
        self.assertIn("/schedule", choices)
        self.assertIn("/campaign-destination", choices)
        self.assertNotIn("/old-campaign-destination", choices)

    def test_sent_campaign_marks_redirect_destination_read_only(self):
        campaign = EmailCampaign.objects.create(
            subject="Sent Update",
            body="Sent body",
            login_redirect_path="/campaign-destination",
            status="sent",
        )

        readonly_fields = self.model_admin.get_readonly_fields(self._build_request(), obj=campaign)

        self.assertIn("login_redirect_path", readonly_fields)

    def _get_form(self, *, data=None, instance=None):
        form_class = self.model_admin.get_form(self._build_request(), obj=instance)
        return form_class(data=data, instance=instance)

    def _build_request(self):
        request = self.request_factory.get("/admin/mail/emailcampaign/")
        request.user = self.admin_user
        return request
