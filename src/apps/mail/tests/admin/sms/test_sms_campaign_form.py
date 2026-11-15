from django.test import TestCase

from apps.event.tests.helpers import make_event, make_ticket
from apps.mail.admin.sms_campaign import (
    SmsCampaignForm,
)
from apps.mail.models import SmsCampaign


class SmsCampaignFormTests(TestCase):
    """Unit-level coverage for SmsCampaignForm clean/save/init helpers."""

    def setUp(self):
        self.event = make_event(name="SMS Event")
        self.ticket = make_ticket(self.event, name="VIP", order=1)
        self.other_event = make_event(name="Other Event")

    def _base_data(self, **overrides):
        data = {
            "name": "Form Campaign",
            "message": "Hi {{first_name}}",
            "phone_policy": "verified_opt_in",
            "audience_type": "subscribers",
            "ticket_id": "",
            "manual_phones": "",
            "exclude_audience_type": "",
            "exclude_ticket_id": "",
            "status": "draft",
            "total_recipients": "0",
            "sent_count": "0",
            "failed_count": "0",
        }
        data.update(overrides)
        return data

    def test_clean_clears_ticket_id_for_non_ticket_audience(self):
        form = SmsCampaignForm(data=self._base_data(audience_type="subscribers", ticket_id="leftover"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ticket_id"], "")

    def test_clean_ticket_type_requires_ticket(self):
        form = SmsCampaignForm(data=self._base_data(audience_type="ticket_type", event=str(self.event.pk)))

        self.assertFalse(form.is_valid())
        self.assertIn("ticket", form.errors)
        self.assertIn("A ticket type must be selected.", form.errors["ticket"])

    def test_clean_ticket_type_rejects_ticket_from_other_event(self):
        form = SmsCampaignForm(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.other_event.pk),
                ticket=str(self.ticket.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong to the selected event", form.errors["ticket"][0])

    def test_clean_ticket_type_accepts_matching_ticket_and_sets_ticket_id(self):
        form = SmsCampaignForm(
            data=self._base_data(
                audience_type="ticket_type",
                event=str(self.event.pk),
                ticket=str(self.ticket.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["ticket_id"], str(self.ticket.pk))

    def test_clean_exclude_ticket_type_requires_ticket(self):
        form = SmsCampaignForm(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("A ticket type must be selected for ticket exclusion.", form.errors["exclude_ticket"])

    def test_clean_exclude_ticket_type_rejects_mismatched_event(self):
        form = SmsCampaignForm(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.other_event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn("does not belong to the exclusion event", form.errors["exclude_ticket"][0])

    def test_clean_exclude_ticket_type_accepts_matching_ticket(self):
        form = SmsCampaignForm(
            data=self._base_data(
                exclude_audience_type="ticket_type",
                exclude_event=str(self.event.pk),
                exclude_ticket=str(self.ticket.pk),
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exclude_ticket_id"], str(self.ticket.pk))

    def test_save_clears_ticket_and_exclusion_fields(self):
        form = SmsCampaignForm(
            data=self._base_data(
                audience_type="subscribers",
                ticket_id="stale",
                exclude_audience_type="",
                exclude_ticket_id="stale-exclude",
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

        instance = form.save(commit=True)

        self.assertEqual(instance.ticket_id, "")
        self.assertEqual(instance.exclude_ticket_id, "")
        self.assertIsNone(instance.exclude_event_id)

    def test_init_restores_ticket_initial_for_ticket_audience(self):
        campaign = SmsCampaign.objects.create(
            name="Existing",
            message="Hi",
            audience_type="ticket_type",
            event=self.event,
            ticket_id=str(self.ticket.pk),
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertEqual(form.initial["ticket"], self.ticket.pk)

    def test_init_restores_ticket_initial_ignores_missing_ticket(self):
        campaign = SmsCampaign.objects.create(
            name="Existing",
            message="Hi",
            audience_type="ticket_type",
            event=self.event,
            ticket_id="00000000-0000-0000-0000-000000000000",
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertNotIn("ticket", form.initial)

    def test_init_restores_exclude_ticket_initial(self):
        campaign = SmsCampaign.objects.create(
            name="Existing",
            message="Hi",
            audience_type="subscribers",
            exclude_audience_type="ticket_type",
            exclude_event=self.event,
            exclude_ticket_id=str(self.ticket.pk),
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertEqual(form.initial["exclude_ticket"], self.ticket.pk)

    def test_init_disables_fields_for_sent_campaign(self):
        campaign = SmsCampaign.objects.create(
            name="Sent",
            message="Hi",
            audience_type="subscribers",
            status="sent",
        )

        form = SmsCampaignForm(instance=campaign)

        self.assertTrue(form.fields["name"].disabled)
        self.assertTrue(form.fields["message"].disabled)
        self.assertTrue(form.fields["audience_type"].disabled)
