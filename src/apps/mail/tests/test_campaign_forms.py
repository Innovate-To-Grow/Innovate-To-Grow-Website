"""Coverage for EmailCampaign admin form clean/save/init helpers and display mixin."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_event, make_superuser, make_ticket
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.admin.campaign.forms import EmailCampaignForm
from apps.mail.models import EmailCampaign
from apps.mail.services.preview import HTML_MARKER


class EmailCampaignFormTests(TestCase):
    """Drive the admin form through EmailCampaignAdmin.get_form (as the admin does)."""

    def setUp(self):
        self.admin_user = make_superuser()
        self.factory = RequestFactory()
        self.model_admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.event = make_event(name="Form Event")
        self.ticket = make_ticket(self.event, name="GA", order=1)
        self.other_event = make_event(name="Other Event")

    def _request(self):
        request = self.factory.get("/admin/mail/emailcampaign/")
        request.user = self.admin_user
        return request

    def _form(self, *, data=None, instance=None):
        form_class = self.model_admin.get_form(self._request(), obj=instance)
        return form_class(data=data, instance=instance)

    def _base_data(self, **overrides):
        data = {
            "subject": "Spring update",
            "body": "Hello",
            "body_format": "plain",
            "login_redirect_path": "/account",
            "audience_type": "subscribers",
            "member_email_scope": "primary",
            "manual_emails": "",
            "exclude_audience_type": "",
            "exclude_member_email_scope": "primary",
            "include_unsubscribe_header": "on",
        }
        data.update(overrides)
        return data

    def test_clean_ticket_type_requires_ticket(self):
        form = self._form(data=self._base_data(audience_type="ticket_type", event=str(self.event.pk)))

        self.assertFalse(form.is_valid())
        self.assertIn("A ticket type must be selected.", form.errors["ticket"])

    def test_clean_ticket_type_rejects_mismatched_event(self):
        form = self._form(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.other_event.pk),
                ticket=str(self.ticket.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong to the selected event", form.errors["ticket"][0])

    def test_clean_ticket_type_sets_manual_emails_to_ticket_id(self):
        form = self._form(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.event.pk),
                ticket=str(self.ticket.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["manual_emails"], str(self.ticket.pk))

    def test_clean_exclude_ticket_type_requires_ticket(self):
        form = self._form(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("A ticket type must be selected for ticket exclusion.", form.errors["exclude_ticket"])

    def test_clean_exclude_ticket_type_rejects_mismatched_event(self):
        form = self._form(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.other_event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong to the exclusion event", form.errors["exclude_ticket"][0])

    def test_clean_exclude_ticket_type_sets_exclude_ticket_id(self):
        form = self._form(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exclude_ticket_id"], str(self.ticket.pk))

    def test_save_sets_manual_emails_from_ticket(self):
        form = self._form(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.event.pk),
                ticket=str(self.ticket.pk),
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertEqual(instance.manual_emails, str(self.ticket.pk))

    def test_save_clears_exclusion_fields_when_no_exclusion(self):
        form = self._form(data=self._base_data(exclude_audience_type=""))
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertIsNone(instance.exclude_event_id)
        self.assertEqual(instance.exclude_ticket_id, "")

    def test_save_persists_exclude_ticket_id_when_ticket_exclusion(self):
        form = self._form(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertEqual(instance.exclude_ticket_id, str(self.ticket.pk))

    def test_save_prepends_html_marker_for_html_format(self):
        form = self._form(data=self._base_data(body_format="html", body="<p>Hi</p>"))
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertTrue(instance.body.startswith(HTML_MARKER))
        self.assertIn("<p>Hi</p>", instance.body)

    def test_init_restores_ticket_initial(self):
        campaign = EmailCampaign.objects.create(
            subject="Existing",
            body="Hi",
            login_redirect_path="/account",
            audience_type="ticket_type",
            event=self.event,
            manual_emails=str(self.ticket.pk),
        )

        form = self._form(instance=campaign)

        self.assertEqual(form.initial["ticket"], self.ticket.pk)

    def test_init_restores_ticket_initial_ignores_missing(self):
        campaign = EmailCampaign.objects.create(
            subject="Existing",
            body="Hi",
            login_redirect_path="/account",
            audience_type="ticket_type",
            event=self.event,
            manual_emails="00000000-0000-0000-0000-000000000000",
        )

        form = self._form(instance=campaign)

        self.assertNotIn("ticket", form.initial)

    def test_init_restores_exclude_ticket_initial(self):
        campaign = EmailCampaign.objects.create(
            subject="Existing",
            body="Hi",
            login_redirect_path="/account",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=self.event,
            exclude_ticket_id=str(self.ticket.pk),
        )

        form = self._form(instance=campaign)

        self.assertEqual(form.initial["exclude_ticket"], self.ticket.pk)

    def test_init_restores_exclude_ticket_initial_ignores_missing(self):
        campaign = EmailCampaign.objects.create(
            subject="Existing",
            body="Hi",
            login_redirect_path="/account",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=self.event,
            exclude_ticket_id="00000000-0000-0000-0000-000000000000",
        )

        form = self._form(instance=campaign)

        self.assertNotIn("exclude_ticket", form.initial)

    def test_init_disables_fields_for_sent_campaign(self):
        campaign = EmailCampaign.objects.create(
            subject="Sent",
            body="Hi",
            login_redirect_path="/account",
            status="sent",
        )

        # Instantiate the raw form (no admin field exclusion) so the disable
        # branch in __init__ runs against the full field set.
        form = EmailCampaignForm(instance=campaign)

        self.assertTrue(form.fields["subject"].disabled)
        self.assertTrue(form.fields["body"].disabled)
        self.assertTrue(form.fields["audience_type"].disabled)

    def test_init_splits_html_marker_into_format_and_body(self):
        campaign = EmailCampaign.objects.create(
            subject="HTML",
            body=HTML_MARKER + "<p>Rich</p>",
            login_redirect_path="/account",
        )

        form = self._form(instance=campaign)

        self.assertEqual(form.initial["body_format"], "html")
        self.assertEqual(form.initial["body"], "<p>Rich</p>")


class CampaignDisplayMixinTests(TestCase):
    def setUp(self):
        self.admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.factory = RequestFactory()

    def test_subject_preview_truncates(self):
        long_campaign = EmailCampaign(subject="s" * 80)
        self.assertEqual(self.admin.subject_preview(long_campaign), "s" * 60 + "...")

    def test_body_readonly_returns_dash_without_object(self):
        self.assertEqual(self.admin.body_readonly(None), "-")

    def test_body_readonly_escapes_and_embeds_base64(self):
        import base64

        campaign = EmailCampaign(subject="X", body="<b>Hi</b>")
        html = self.admin.body_readonly(campaign)

        self.assertIn("&lt;b&gt;Hi&lt;/b&gt;", html)
        self.assertIn(base64.b64encode(b"<b>Hi</b>").decode("ascii"), html)

    def test_get_fieldsets_swaps_body_for_readonly_on_sent(self):
        campaign = EmailCampaign.objects.create(
            subject="Sent", body="Hi", login_redirect_path="/account", status="sent"
        )
        request = self.factory.get("/")

        fieldsets = self.admin.get_fieldsets(request, obj=campaign)
        all_fields = [f for _, opts in fieldsets for f in opts.get("fields", ())]

        self.assertIn("body_readonly", all_fields)
        self.assertNotIn("body", all_fields)

    def test_get_fieldsets_appends_error_details(self):
        campaign = EmailCampaign.objects.create(
            subject="Failed",
            body="Hi",
            login_redirect_path="/account",
            status="failed",
            error_message="boom",
        )
        request = self.factory.get("/")

        titles = [title for title, _ in self.admin.get_fieldsets(request, obj=campaign)]

        self.assertIn("Error Details", titles)

    def test_get_readonly_fields_includes_error_message(self):
        campaign = EmailCampaign.objects.create(
            subject="Failed",
            body="Hi",
            login_redirect_path="/account",
            status="failed",
            error_message="boom",
        )
        request = self.factory.get("/")

        readonly = self.admin.get_readonly_fields(request, obj=campaign)

        self.assertIn("error_message", readonly)
        self.assertIn("body_readonly", readonly)


class CampaignChangelistFallbackTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_changelist_uses_fallback_context_when_config_load_raises(self):
        with patch(
            "apps.core.models.EmailServiceConfig.load",
            side_effect=RuntimeError("config unavailable"),
        ):
            response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["email_config"])
        self.assertIsNone(response.context["aws_config"])
        self.assertIsNone(response.context["gmail_import_config"])
        self.assertEqual(response.context["gmail_mailbox"], "")
