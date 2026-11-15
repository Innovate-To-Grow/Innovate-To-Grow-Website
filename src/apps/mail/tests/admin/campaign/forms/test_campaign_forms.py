"""Coverage for EmailCampaign admin form clean/save/init helpers and display mixin."""

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from apps.event.tests.helpers import make_event, make_superuser, make_ticket
from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.content.preview import HTML_MARKER


class _EmailCampaignFormCase(TestCase):
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
            "login_link_validity_days": "7",
            "manual_emails": "",
            "exclude_audience_type": "",
            "exclude_member_email_scope": "primary",
            "include_unsubscribe_header": "on",
        }
        data.update(overrides)
        return data


class EmailCampaignFormTests(_EmailCampaignFormCase):
    """Drive the admin form through EmailCampaignAdmin.get_form (as the admin does)."""

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

    def test_save_stores_exactly_one_marker_however_many_the_editor_posts(self):
        # A browser posts the textarea with CRLF line endings; a body copied from another campaign with the old
        # "Copy HTML" button carried the marker. Both used to add one more marker on every save.
        posted = f"{HTML_MARKER.strip()}\r\n{HTML_MARKER.strip()}\r\n<p>Hi</p>\r\n<p>Bye</p>"
        form = self._form(data=self._base_data(body_format="html", body=posted))
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertEqual(instance.body, HTML_MARKER + "<p>Hi</p>\n<p>Bye</p>")

        # Round trip: what the editor shows is saved back unchanged.
        again = self._form(instance=instance)
        self.assertEqual(again.initial["body_format"], "html")
        self.assertEqual(again.initial["body"], "<p>Hi</p>\n<p>Bye</p>")
        again = self._form(data=self._base_data(body_format="html", body="<p>Hi</p>\r\n<p>Bye</p>"), instance=instance)
        self.assertTrue(again.is_valid(), again.errors)
        self.assertEqual(again.save(commit=True).body, HTML_MARKER + "<p>Hi</p>\n<p>Bye</p>")
