"""The queue's SLA filter and column, and the configuration admins (SLA targets, response templates). Tickets have no
owner (I2G-HELPDESK-01): there is no group filter or column, and assignment groups have no admin page."""

from datetime import timedelta

from django.contrib import admin
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ....admin.intake.sla_targets import _duration
from ....admin.tickets.filters import _DefaultChoiceFilter
from ....models import ResponseTemplate, SLATarget, Ticket
from ...helpers import helpdesk_staff
from ...helpers.service import Status, clocked_ticket, new_ticket

HOUR = timedelta(hours=1)


class QueueFilterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        now = timezone.now()
        new_ticket(subject="one")
        new_ticket(subject="two")
        new_ticket(subject="three")
        new_ticket(subject="breached", sla_started_at=now - 3 * HOUR, response_due_at=now - HOUR)
        clocked_ticket(subject="at risk", started=now - 20 * HOUR)  # 20 h of a 24 h first-response target
        clocked_ticket(subject="on track", priority=Ticket.Priority.LOW)

    def listed(self, query):
        response = self.client.get(f"{reverse('admin:helpdesk_ticket_changelist')}?{query}")
        self.assertEqual(response.status_code, 200)
        return {ticket.subject for ticket in response.context["cl"].result_list}

    def test_sla_filter(self):
        self.assertEqual(self.listed("sla=breached"), {"breached"})
        self.assertEqual(self.listed("sla=at_risk"), {"at risk"})
        self.assertEqual(self.listed("sla=none"), {"one", "two", "three"})
        self.assertEqual(len(self.listed("")), 6)  # no SLA choice: every open ticket

    def test_a_default_choice_filter_must_name_its_default(self):
        with self.assertRaises(NotImplementedError):
            _DefaultChoiceFilter.default_value(None)

    def test_the_sla_column(self):
        response = self.client.get(reverse("admin:helpdesk_ticket_changelist"))

        self.assertContains(response, "Response breached")
        self.assertContains(response, "At risk · Response due ")
        self.assertContains(response, "Response due ", count=2)  # at risk, and on track


class SLAColumnTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = admin.site._registry[Ticket]

    def test_the_states_the_column_shows(self):
        now = timezone.now()
        self.assertEqual(self.admin.sla_column(new_ticket()), ("none", "—"))
        self.assertEqual(self.admin.sla_column(clocked_ticket(started=now - 30 * HOUR))[0], "breached")
        state, text = self.admin.sla_column(clocked_ticket(started=now - 20 * HOUR))
        self.assertEqual(state, "at_risk")
        self.assertTrue(text.startswith("At risk · Response due "))
        resolved = clocked_ticket(status=Status.RESOLVED, first_responded_at=now)
        self.assertEqual(self.admin.sla_column(resolved), ("met", "Resolution: Met"))
        self.assertEqual(self.admin.last_reply_column(new_ticket()), "—")  # nobody replied yet


class ConfigAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def test_sla_targets_list_change_and_cannot_be_deleted(self):
        target = SLATarget.objects.get(priority="urgent")

        listing = self.client.get(reverse("admin:helpdesk_slatarget_changelist"))
        change = self.client.get(reverse("admin:helpdesk_slatarget_change", args=[target.pk]))
        delete = self.client.get(reverse("admin:helpdesk_slatarget_delete", args=[target.pk]))

        self.assertContains(listing, "1 – Critical")
        self.assertContains(listing, "8 h")
        self.assertEqual(change.status_code, 200)
        self.assertNotIn("priority", change.context["adminform"].form.fields)  # read-only once saved
        self.assertEqual(delete.status_code, 403)
        self.assertTrue(SLATarget.objects.filter(pk=target.pk).exists())
        self.assertEqual(str(target), "SLA for 1 – Critical")

    def test_a_new_sla_target_picks_its_priority_from_the_list(self):
        SLATarget.objects.filter(priority="low").delete()

        add = self.client.get(reverse("admin:helpdesk_slatarget_add"))
        response = self.client.post(
            reverse("admin:helpdesk_slatarget_add"),
            {"priority": "low", "response_minutes": "90", "resolution_minutes": "1500", "is_active": "on"},
        )

        # Only the priority that has no target yet.
        self.assertEqual(add.context["adminform"].form.fields["priority"].choices, [("low", "4 – Low")])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SLATarget.objects.get(priority="low").response_minutes, 90)

    def test_response_templates_list_and_add(self):
        template = ResponseTemplate.objects.create(name="Showcase time", body="It starts at 10.")
        self.assertEqual(str(template), "Showcase time")

        self.assertContains(self.client.get(reverse("admin:helpdesk_responsetemplate_changelist")), "Showcase time")
        self.assertEqual(self.client.get(reverse("admin:helpdesk_responsetemplate_add")).status_code, 200)

    def test_durations_read_in_days_hours_and_minutes(self):
        cases = {0: "0 min", 45: "45 min", 60: "1 h", 90: "1 h 30 min", 1440: "1 d", 1500: "1 d 1 h", 4321: "3 d 1 min"}
        for minutes, label in cases.items():
            with self.subTest(minutes):
                self.assertEqual(_duration(minutes), label)
