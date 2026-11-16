from apps.mail.admin.campaign.forms import EmailCampaignForm
from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.preview import HTML_MARKER
from apps.mail.tests.admin.campaign.forms.test_campaign_forms import _EmailCampaignFormCase


class EmailCampaignFormTests(_EmailCampaignFormCase):
    def test_save_plain_format_drops_a_pasted_marker(self):
        form = self._form(data=self._base_data(body_format="plain", body=f"{HTML_MARKER.strip()}\r\nHello"))
        self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(form.save(commit=True).body, "Hello")

    def test_body_format_is_required(self):
        data = self._base_data(body="<p>Hi</p>")
        del data["body_format"]

        form = self._form(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("body_format", form.errors)

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
        # Validity is frozen onto tokens at send time, so it locks after send...
        self.assertTrue(form.fields["login_link_validity_days"].disabled)
        # ...but the reusable flag stays editable: it is read at login time and
        # unticking it is the kill switch for already-sent links.
        self.assertFalse(form.fields["login_link_reusable"].disabled)

    def test_login_link_validity_bounds(self):
        from django.core.exceptions import ValidationError

        for value, valid in ((0, False), (1, True), (90, True), (91, False)):
            campaign = EmailCampaign(
                subject="Bounds",
                body="Hi",
                login_redirect_path="/account",
                login_link_validity_days=value,
            )
            if valid:
                campaign.full_clean()
            else:
                with self.assertRaises(ValidationError):
                    campaign.full_clean()

    def test_init_splits_html_marker_into_format_and_body(self):
        campaign = EmailCampaign.objects.create(
            subject="HTML",
            body=HTML_MARKER + "<p>Rich</p>",
            login_redirect_path="/account",
        )

        form = self._form(instance=campaign)

        self.assertEqual(form.initial["body_format"], "html")
        self.assertEqual(form.initial["body"], "<p>Rich</p>")

    def test_init_strips_every_leading_marker_whatever_follows_it(self):
        marker = HTML_MARKER.strip()
        campaign = EmailCampaign.objects.create(
            subject="HTML",
            body=f"{marker}\n{marker}\r\n{marker}\r\n{marker} <div>Rich</div>",
            login_redirect_path="/account",
        )

        form = self._form(instance=campaign)

        self.assertEqual(form.initial["body_format"], "html")
        self.assertEqual(form.initial["body"], "<div>Rich</div>")

    def test_init_selects_plain_text_for_an_unmarked_body(self):
        campaign = EmailCampaign.objects.create(subject="Plain", body="Hello", login_redirect_path="/account")

        form = self._form(instance=campaign)

        self.assertEqual(form.initial["body_format"], "plain")
        self.assertEqual(form.initial["body"], "Hello")
        self.assertIn('value="plain"', str(form["body_format"]))
        self.assertIn("checked", str(form["body_format"]).split('value="plain"')[1].split(">")[0])
